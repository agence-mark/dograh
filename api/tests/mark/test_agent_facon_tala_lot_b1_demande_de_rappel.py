"""[.mark] agent-facon-tala, suite des résultats fermés, lot B1 : l'outil natif « demander un rappel ».

Un agent qui a recueilli une demande n'avait aucun acte pour la fermer. L'outil lit la fiche : sans nom ou sans numéro
(au téléphone, le numéro de l'appel compte) il rend « il manque : … » et n'écrit rien ; sinon il écrit UNE entrée de rappel
(origine ``agent``, la mécanique de ``rappels.py``) et rend « transmise ». Son issue vient de sa configuration et n'est posée
qu'à ce résultat réel (``issue_reservee.py``).

| Test | Ce qu'il prouve |
|---|---|
| pures | ce qui manque (nom, numéro, numéro de l'appel en repli, « refusé » = manquant) ; le résumé du rappel ; l'outil se reconnaît à sa configuration seule |
| numéro / nom | il manque le numéro ou le nom : « il manque », aucune entrée, aucune issue |
| transmise | l'entrée est écrite (objet, moment souhaité, numéro), la réponse est « transmise » |
| une entrée | deux appels dans le même appel : une seule entrée, la dernière demande |
| issue | l'issue de la configuration est posée à « transmise », jamais sans résultat, jamais si l'outil n'en règle pas |
| réservée | le classement final ne voit pas l'issue de l'outil et ne peut pas la rendre |
| manager | le schéma vient de la configuration ; le gestionnaire est monté par le gestionnaire d'outils ; un agent sans cet outil ne change pas |
| téléphone | le vrai moteur d'appel, le numéro de l'appel remplace le numéro dicté, un raccrochage garde l'issue de l'outil sans classement |
| clavier | vraies routes du clavier : l'outil appelé dans un tour, la fin de session garde l'issue de l'outil sans classement ; sans l'outil, rien ne change |
| schéma | l'API accepte la définition native et refuse une action inconnue |
"""

from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest
from pipecat.processors.aggregators.llm_context import LLMContext
from pipecat.utils.enums import EndTaskReason

from api.schemas.tool import CreateToolRequest
from api.services.apres_appel.demande_de_rappel import (
    ACTION,
    STATUT_IL_MANQUE,
    STATUT_TRANSMISE,
    ce_qui_manque,
    est_un_outil_de_rappel,
    traiter,
)
from api.services.apres_appel.rappels import (
    CLE_RAPPEL,
    ORIGINE_AGENT,
    origine,
    rappels_de,
    resume_du_rappel,
)
from api.services.workflow.disposition_extraction import DispositionExtractionService
from api.services.workflow.issue_reservee import codes_reserves
from api.services.workflow.pipecat_engine import PipecatEngine
from api.services.workflow.pipecat_engine_custom_tools import CustomToolManager
from api.tests.test_agent_transfer import build_agent_workflow
from pipecat.tests import MockLLMService

ISSUE = "demande_a_rappeler_agent"

CONFIG = {
    "action": ACTION,
    "parameters": [
        {"name": "objet", "type": "string", "description": "Ce que la personne demande.", "required": True},
        {"name": "moment_souhaite", "type": "string", "description": "Le moment souhaité.", "required": False},
    ],
    "champs_requis": [
        {"champ": "nom", "libelle": "le nom"},
        {"champ": "numero_dicte", "libelle": "le numéro", "repli_appel": "caller_number"},
    ],
    "call_disposition": ISSUE,
}


def _outil(config=None, nom="demander_un_rappel", uuid="uuid-rappel"):
    return SimpleNamespace(
        category="native",
        tool_uuid=uuid,
        name=nom,
        description="Transmet la demande de la personne pour qu'on la rappelle.",
        definition={"schema_version": 1, "type": "native", "config": CONFIG if config is None else config},
    )


async def _moteur(fiche=None, variables=None):
    graphe = build_agent_workflow(name="Accueil", greeting=None)
    moteur = PipecatEngine(
        llm=MockLLMService(mock_steps=[], chunk_delay=0),
        context=LLMContext(),
        workflow=graphe,
        call_context_vars=dict(variables or {}),
        workflow_run_id=1,
    )
    moteur._get_organization_id = AsyncMock(return_value=1)
    moteur._custom_tool_manager = CustomToolManager(moteur)
    moteur._gathered_context.update(fiche or {})
    return moteur


async def _appeler(moteur, outil, **arguments):
    """Le gestionnaire monté PAR le gestionnaire d'outils (la route de l'appel de fonction)."""
    gestionnaire, _delai = moteur._custom_tool_manager._create_handler(outil, "demander_un_rappel")
    rendu = AsyncMock()
    await gestionnaire(SimpleNamespace(arguments=arguments, result_callback=rendu, tool_call_id="t1"))
    rendu.assert_awaited_once()
    return rendu.await_args.args[0]


# --------------------------------------------------------------------------- #
# Les fonctions pures
# --------------------------------------------------------------------------- #


def test_ce_qui_manque_se_lit_dans_la_fiche_et_le_numero_de_l_appel_remplace_le_numero_dicte():
    assert ce_qui_manque({}, {}, CONFIG) == ["le nom", "le numéro"]
    assert ce_qui_manque({"nom": "Faucheux"}, {}, CONFIG) == ["le numéro"]
    assert ce_qui_manque({"numero_dicte": "0631524780"}, {}, CONFIG) == ["le nom"]
    assert ce_qui_manque({"nom": "Faucheux"}, {"caller_number": "+33631524780"}, CONFIG) == []
    assert ce_qui_manque({"nom": "Faucheux", "numero_dicte": "0631524780"}, {}, CONFIG) == []


def test_un_champ_refuse_ou_vide_manque_encore():
    assert ce_qui_manque({"nom": "refusé", "numero_dicte": "0631524780"}, {}, CONFIG) == ["le nom"]
    assert ce_qui_manque({"nom": "  ", "numero_dicte": "0631524780"}, {}, CONFIG) == ["le nom"]
    assert ce_qui_manque({"nom": "Faucheux", "numero_dicte": "0631524780"}, {"caller_number": ""}, CONFIG) == []


def test_sans_champ_requis_rien_ne_manque_et_un_libelle_absent_dit_le_champ():
    assert ce_qui_manque({}, {}, {"action": ACTION}) == []
    assert ce_qui_manque({}, {}, {"champs_requis": [{"champ": "motif"}]}) == ["motif"]


def test_l_outil_se_reconnait_a_sa_configuration_seule():
    assert est_un_outil_de_rappel(_outil())
    assert not est_un_outil_de_rappel(_outil({"action": "autre"}))
    assert not est_un_outil_de_rappel(SimpleNamespace(category="http_api", definition={"config": CONFIG}))
    assert not est_un_outil_de_rappel(SimpleNamespace(category="native", definition=None))
    assert not est_un_outil_de_rappel(None)


def test_le_resume_d_un_rappel_de_l_agent_dit_ce_qu_il_y_a_a_faire():
    entree = {"origine": ORIGINE_AGENT, "numero": "0631524780", "objet": "un devis", "souhait": "demain matin"}
    assert origine(entree) == ORIGINE_AGENT
    resume = resume_du_rappel(entree)
    assert "demande de rappel" in resume and "0631524780" in resume and "un devis" in resume and "demain matin" in resume
    assert resume_du_rappel({"origine": ORIGINE_AGENT}) == "Rappel à faire : demande de rappel de l'appelant."


# --------------------------------------------------------------------------- #
# Le gestionnaire (la route de l'appel de fonction du moteur)
# --------------------------------------------------------------------------- #


@pytest.mark.asyncio
async def test_il_manque_le_numero_rien_n_est_ecrit_et_aucune_issue_n_est_posee():
    moteur = await _moteur({"nom": "Faucheux"})
    resultat = await _appeler(moteur, _outil(), objet="un devis")
    assert resultat["statut"] == STATUT_IL_MANQUE
    assert resultat["il_manque"] == ["le numéro"]
    assert resultat["consigne"] == "il manque : le numéro"
    assert CLE_RAPPEL not in moteur._gathered_context
    assert "call_disposition" not in moteur._gathered_context


@pytest.mark.asyncio
async def test_il_manque_le_nom_rien_n_est_ecrit():
    moteur = await _moteur({"numero_dicte": "0631524780"})
    resultat = await _appeler(moteur, _outil(), objet="un devis")
    assert resultat["statut"] == STATUT_IL_MANQUE and resultat["il_manque"] == ["le nom"]
    assert CLE_RAPPEL not in moteur._gathered_context
    assert "call_disposition" not in moteur._gathered_context


@pytest.mark.asyncio
async def test_il_manque_les_deux_les_deux_sont_dits_dans_l_ordre_de_la_configuration():
    moteur = await _moteur({})
    resultat = await _appeler(moteur, _outil(), objet="un devis")
    assert resultat["il_manque"] == ["le nom", "le numéro"]
    assert resultat["consigne"] == "il manque : le nom, le numéro"


@pytest.mark.asyncio
async def test_transmise_ecrit_l_entree_avec_l_objet_le_moment_et_le_numero():
    moteur = await _moteur({"nom": "Faucheux", "numero_dicte": "0631524780"})
    resultat = await _appeler(moteur, _outil(), objet="un devis pour un poêle", moment_souhaite="mardi matin")
    assert resultat == {"statut": STATUT_TRANSMISE}
    [entree] = rappels_de(moteur._gathered_context)
    assert entree["origine"] == ORIGINE_AGENT and entree["mode"] == "rappel"
    assert entree["objet"] == "un devis pour un poêle" and entree["souhait"] == "mardi matin"
    assert entree["numero"] == "0631524780"
    assert entree["le"]


@pytest.mark.asyncio
async def test_sans_moment_souhaite_l_entree_n_en_invente_pas():
    moteur = await _moteur({"nom": "Faucheux", "numero_dicte": "0631524780"})
    await _appeler(moteur, _outil(), objet="une question")
    [entree] = rappels_de(moteur._gathered_context)
    assert entree["souhait"] is None


@pytest.mark.asyncio
async def test_une_seule_entree_par_appel_la_derniere_demande_la_remplace():
    moteur = await _moteur({"nom": "Faucheux", "numero_dicte": "0631524780"})
    await _appeler(moteur, _outil(), objet="un devis")
    await _appeler(moteur, _outil(), objet="une facture", moment_souhaite="jeudi")
    entrees = rappels_de(moteur._gathered_context)
    assert len(entrees) == 1
    assert entrees[0]["objet"] == "une facture" and entrees[0]["souhait"] == "jeudi"


@pytest.mark.asyncio
async def test_une_entree_d_une_autre_origine_est_gardee_et_celle_de_l_agent_s_ajoute():
    moteur = await _moteur({"nom": "Faucheux", "numero_dicte": "0631524780"})
    moteur._gathered_context[CLE_RAPPEL] = [{"origine": "transfert", "mode": "rappel"}]
    await _appeler(moteur, _outil(), objet="un devis")
    assert [origine(e) for e in rappels_de(moteur._gathered_context)] == ["transfert", ORIGINE_AGENT]


@pytest.mark.asyncio
async def test_l_issue_de_l_outil_est_posee_a_transmise_et_a_ce_moment_seulement():
    moteur = await _moteur({"nom": "Faucheux"})
    await _appeler(moteur, _outil(), objet="un devis")  # il manque le numéro
    assert "call_disposition" not in moteur._gathered_context
    moteur._gathered_context["numero_dicte"] = "0631524780"
    await _appeler(moteur, _outil(), objet="un devis")
    assert moteur._gathered_context["call_disposition"] == ISSUE


@pytest.mark.asyncio
async def test_un_outil_sans_issue_reglee_ne_pose_aucune_issue():
    sans_issue = {k: v for k, v in CONFIG.items() if k != "call_disposition"}
    moteur = await _moteur({"nom": "Faucheux", "numero_dicte": "0631524780"})
    resultat = await _appeler(moteur, _outil(sans_issue), objet="un devis")
    assert resultat["statut"] == STATUT_TRANSMISE
    assert "call_disposition" not in moteur._gathered_context


@pytest.mark.asyncio
async def test_une_fiche_illisible_ne_coute_pas_l_appel():
    moteur = await _moteur({"nom": "Faucheux", "numero_dicte": "0631524780"})
    moteur._gathered_context[CLE_RAPPEL] = "abîmé"
    resultat = await _appeler(moteur, _outil(), objet="un devis")
    assert resultat["statut"] == STATUT_TRANSMISE
    assert len(rappels_de(moteur._gathered_context)) == 1


@pytest.mark.asyncio
async def test_une_erreur_interne_rend_une_erreur_et_n_ecrit_rien():
    moteur = await _moteur({"nom": "Faucheux", "numero_dicte": "0631524780"})
    with patch(
        "api.services.apres_appel.demande_de_rappel.ecrire_la_demande", side_effect=RuntimeError("boum")
    ):
        resultat = await _appeler(moteur, _outil(), objet="un devis")
    assert resultat == {"statut": "erreur"}
    assert "call_disposition" not in moteur._gathered_context


def test_traiter_sans_fiche_rend_une_erreur_sans_lever():
    assert traiter(SimpleNamespace(_gathered_context=None), _outil(), {}) == {"statut": "erreur"}


# --------------------------------------------------------------------------- #
# L'issue réservée : le classement final ne la voit pas
# --------------------------------------------------------------------------- #


def test_l_issue_de_l_outil_est_reservee_comme_celle_du_transfert():
    assert codes_reserves([_outil()]) == {ISSUE}
    transfert = SimpleNamespace(category="transfer_call", definition={"config": {"call_disposition": "transfert_ok"}})
    assert codes_reserves([_outil(), transfert]) == {ISSUE, "transfert_ok"}
    assert codes_reserves([_outil({**CONFIG, "call_disposition": None})]) == set()
    http = SimpleNamespace(category="http_api", definition={"config": {"call_disposition": "autre"}})
    assert codes_reserves([http]) == set()


@pytest.mark.asyncio
async def test_le_classement_final_ne_rend_jamais_l_issue_de_l_outil_meme_si_le_modele_la_donne():
    from api.schemas.workflow_configurations import CallDispositionOption

    contexte = LLMContext()
    contexte.set_messages([{"role": "user", "content": "Rappelez-moi."}])

    async def reservees():
        return {ISSUE}

    service = DispositionExtractionService(
        llm=object(),
        context=contexte,
        options=[CallDispositionOption(code=c, description=f"Issue {c}.") for c in ("devis", ISSUE)],
        template_context={},
        reservees=reservees,
    )
    invites = []

    async def inference(_contexte, messages, *, parent_context):
        invites.append(messages[0]["content"])
        return '{"call_disposition": "%s"}' % ISSUE

    service._run_inference = inference
    assert await service.extract() is None
    assert ISSUE not in invites[0]


# --------------------------------------------------------------------------- #
# Le gestionnaire d'outils : schéma, montage, agent sans l'outil
# --------------------------------------------------------------------------- #


@pytest.mark.asyncio
async def test_le_schema_vient_de_la_configuration_de_l_outil():
    moteur = await _moteur()
    manager = moteur._custom_tool_manager
    with patch.object(manager, "_lire_outils", AsyncMock(return_value=[_outil()])):
        schemas = await manager.get_tool_schemas(["uuid-rappel"])
    [schema] = schemas
    assert schema.name == "demander_un_rappel"
    assert set(schema.properties) == {"objet", "moment_souhaite"}
    assert schema.required == ["objet"]


@pytest.mark.asyncio
async def test_le_gestionnaire_est_monte_aupres_du_modele_par_register_handlers():
    moteur = await _moteur()
    manager = moteur._custom_tool_manager
    with patch.object(manager, "_lire_outils", AsyncMock(return_value=[_outil()])):
        await manager.register_handlers(["uuid-rappel"])
    assert "demander_un_rappel" in moteur.active_agent.llm._functions


@pytest.mark.asyncio
async def test_un_agent_sans_cet_outil_ne_change_pas():
    http = SimpleNamespace(
        category="http_api",
        tool_uuid="u-http",
        name="annuaire",
        description="Cherche.",
        definition={"schema_version": 1, "type": "http_api", "config": {"url": "https://exemple.invalid", "parameters": []}},
    )
    moteur = await _moteur()
    manager = moteur._custom_tool_manager
    with patch.object(manager, "_lire_outils", AsyncMock(return_value=[http])):
        schemas = await manager.get_tool_schemas(["u-http"])
        await manager.register_handlers(["u-http"])
    assert [s.name for s in schemas] == ["annuaire"]
    assert "demander_un_rappel" not in moteur.active_agent.llm._functions
    assert CLE_RAPPEL not in moteur._gathered_context


# --------------------------------------------------------------------------- #
# Le téléphone : le vrai moteur d'appel et sa vraie fin
# --------------------------------------------------------------------------- #


async def _telephone(fiche, variables, *, retenue="autre_issue", arguments=None, outil=None):
    from api.schemas.workflow_configurations import CallDispositionOption
    from api.services.workflow.pipecat_engine_variable_extractor import (
        VariableExtractionManager,
    )
    from api.tests.pipecat_test_utils import run_engine_test_pipeline
    from api.tests.test_pipecat_engine_end_call import (
        EndCallTestHelper,
        create_engine_with_tracking,
    )

    graphe = build_agent_workflow(name="Accueil", greeting=None)
    llm = MockLLMService(mock_steps=[MockLLMService.create_text_chunks("Bonjour !")], chunk_delay=0.001)
    options = [CallDispositionOption(code=c, description=f"Issue {c}.") for c in ("autre_issue", ISSUE)]
    engine, _tts, transport, task = await create_engine_with_tracking(
        graphe, llm, EndCallTestHelper(), call_dispositions=options
    )
    engine._call_context_vars.update(variables)

    async def appeler_puis_raccrocher():
        await engine.set_node(engine.active_agent.workflow.start_node_id)
        engine.context.add_message({"role": "user", "content": "Rappelez-moi."})
        engine._gathered_context.update(fiche)
        engine._resultat_du_rappel = await _appeler(engine, outil or _outil(), **(arguments or {"objet": "un devis"}))
        await engine.end_call_with_reason(EndTaskReason.USER_HANGUP.value, abort_immediately=True)

    with (
        patch("api.db:db_client.get_organization_id_by_workflow_run_id", new_callable=AsyncMock, return_value=1),
        patch("api.db:db_client.update_workflow_run", new_callable=AsyncMock),
        patch.object(VariableExtractionManager, "_perform_extraction", new_callable=AsyncMock, return_value={}),
        patch.object(DispositionExtractionService, "extract", new_callable=AsyncMock, return_value=retenue) as classement,
    ):
        await run_engine_test_pipeline(task, engine, transport, on_ready=appeler_puis_raccrocher)
    return engine, await engine.get_gathered_context(), classement


@pytest.mark.asyncio
async def test_au_telephone_le_numero_de_l_appel_remplace_le_numero_dicte_et_l_issue_de_l_outil_survit_a_la_fin():
    engine, contexte, classement = await _telephone({"nom": "Faucheux"}, {"caller_number": "+33631524780"})
    assert engine._resultat_du_rappel == {"statut": STATUT_TRANSMISE}
    assert contexte["call_status"] == EndTaskReason.USER_HANGUP.value  # le mécanisme reste dit
    assert contexte["call_disposition"] == ISSUE
    classement.assert_not_awaited()  # l'issue posée par l'outil n'est pas reclassée
    [entree] = rappels_de(contexte)
    assert entree["numero"] == "+33631524780"


@pytest.mark.asyncio
async def test_au_telephone_sans_numero_ni_nom_il_manque_et_le_classement_final_reste_celui_d_avant():
    engine, contexte, classement = await _telephone({}, {})
    assert engine._resultat_du_rappel["statut"] == STATUT_IL_MANQUE
    assert CLE_RAPPEL not in contexte
    assert contexte["call_disposition"] == "autre_issue"  # rendue par le classement, jamais l'issue de l'outil
    classement.assert_awaited_once()


# --------------------------------------------------------------------------- #
# Le clavier : les vraies routes
# --------------------------------------------------------------------------- #

CLAVIER_CONFIG = {
    **CONFIG,
    "champs_requis": [{"champ": "nom", "libelle": "le nom"}, {"champ": "motif", "libelle": "le motif"}],
}
ISSUES = [
    {"code": "autre_issue", "description": "Autre issue."},
    {"code": ISSUE, "description": "La demande de rappel est transmise."},
]


async def _clavier(db_session, async_session, test_client_factory, *, avec_outil, appel_du_modele, version="les_deux", classement_reel=False):
    """``version`` : où l'outil est posé. ``les_deux`` : publiée et brouillon ; ``brouillon`` : brouillon seulement (R-12) ;
    ``publiee`` : publiée seulement, le brouillon (celui que joue le clavier) ne l'a pas (R-12)."""
    import copy

    from api.tests.mark.test_clavier_porte_la_fiche import DEFINITION, FICHE, _monter

    definition = copy.deepcopy(DEFINITION)
    reglages = {**FICHE, "call_dispositions": ISSUES}
    user, workflow = await _monter(db_session, async_session, reglages, definition)
    outil = None
    if avec_outil:
        outil = await db_session.create_tool(
            organization_id=workflow.organization_id,
            user_id=user.id,
            name="demander_un_rappel",
            description="Transmet la demande de la personne pour qu'on la rappelle.",
            category="native",
            definition={"schema_version": 1, "type": "native", "config": CLAVIER_CONFIG},
        )
        avec = copy.deepcopy(definition)
        avec["nodes"][0]["data"]["tool_uuids"] = [outil.tool_uuid]
        if version in ("les_deux", "publiee"):
            await db_session.save_workflow_draft(workflow.id, workflow_definition=avec, workflow_configurations=reglages)
            await db_session.publish_workflow_draft(workflow.id)
        if version == "publiee":  # le brouillon, joué par le clavier, n'a plus l'outil
            await db_session.save_workflow_draft(workflow.id, workflow_definition=definition, workflow_configurations=reglages)
        if version == "brouillon":  # la publiée n'a pas l'outil ; le brouillon l'a
            await db_session.save_workflow_draft(workflow.id, workflow_definition=avec, workflow_configurations=reglages)

    modeles = [
        MockLLMService(mock_steps=[], chunk_delay=0.001),
        MockLLMService(mock_steps=appel_du_modele, chunk_delay=0.001),
        MockLLMService(mock_steps=[], chunk_delay=0.001),
    ]
    async with test_client_factory(user) as client:
        with (
            patch("api.services.workflow.text_chat_runner.create_llm_service", side_effect=modeles),
            patch("api.services.workflow.text_chat_runner.db_client.has_active_recordings", new=AsyncMock(return_value=False)),
        ):
            creee = (await client.post(f"/api/v1/workflow/{workflow.id}/text-chat/sessions", json={})).json()
            tour = await client.post(
                f"/api/v1/workflow/{workflow.id}/text-chat/sessions/{creee['workflow_run_id']}/messages",
                json={"text": "je m'appelle Lemaire, je veux un devis", "expected_revision": creee["revision"]},
            )
            assert tour.status_code == 200, tour.text
        with (
            patch("api.services.workflow.text_chat_session_service.extract_text_chat_final_variables", new=AsyncMock(return_value={})),
            patch("api.services.workflow.text_chat_runner.create_llm_service"),
            patch.object(
                DispositionExtractionService,
                "extract" if not classement_reel else "_run_inference",
                new_callable=AsyncMock,
                return_value="autre_issue" if not classement_reel else '{"call_disposition": "autre_issue"}',
            ) as classement,
            patch("api.tasks.arq.enqueue_job", AsyncMock()),
        ):
            fin = await client.post(
                f"/api/v1/workflow/{workflow.id}/text-chat/sessions/{creee['workflow_run_id']}/end",
                json={"expected_revision": tour.json()["revision"]},
            )
    assert fin.status_code == 200, fin.text
    return tour.json(), fin.json()["gathered_context"], classement


def _appels_du_modele(*, noter_motif=True):
    noter = {"nom": "Lemaire"} | ({"motif": "un devis"} if noter_motif else {})
    return [
        MockLLMService.create_function_call_chunks("noter_information", noter, tool_call_id="n1"),
        MockLLMService.create_function_call_chunks(
            "demander_un_rappel", {"objet": "un devis", "moment_souhaite": "demain"}, tool_call_id="r1"
        ),
        MockLLMService.create_text_chunks("C'est noté."),
    ]


@pytest.mark.asyncio
async def test_au_clavier_l_outil_ecrit_la_demande_et_la_fin_de_session_garde_son_issue(
    db_session, async_session, test_client_factory
):
    tour, contexte, classement = await _clavier(
        db_session, async_session, test_client_factory, avec_outil=True, appel_du_modele=_appels_du_modele()
    )
    [entree] = rappels_de(tour["checkpoint"]["gathered_context"])
    assert entree["origine"] == ORIGINE_AGENT and entree["objet"] == "un devis" and entree["souhait"] == "demain"
    assert contexte["call_disposition"] == ISSUE
    assert contexte["call_status"] == EndTaskReason.USER_HANGUP.value
    classement.assert_not_awaited()


@pytest.mark.asyncio
async def test_au_clavier_il_manque_le_motif_aucune_entree_et_l_issue_vient_du_classement(
    db_session, async_session, test_client_factory
):
    tour, contexte, classement = await _clavier(
        db_session,
        async_session,
        test_client_factory,
        avec_outil=True,
        appel_du_modele=_appels_du_modele(noter_motif=False),
    )
    assert CLE_RAPPEL not in tour["checkpoint"]["gathered_context"]
    assert contexte["call_disposition"] == "autre_issue"  # jamais l'issue de l'outil sans son résultat
    classement.assert_awaited_once()


@pytest.mark.asyncio
async def test_au_clavier_un_agent_sans_l_outil_garde_le_classement_d_avant(
    db_session, async_session, test_client_factory
):
    tour, contexte, classement = await _clavier(
        db_session,
        async_session,
        test_client_factory,
        avec_outil=False,
        appel_du_modele=[MockLLMService.create_text_chunks("Très bien.")],
    )
    assert CLE_RAPPEL not in tour["checkpoint"]["gathered_context"]
    assert contexte["call_disposition"] == "autre_issue"
    classement.assert_awaited_once()


# --------------------------------------------------------------------------- #
# Le schéma de l'API
# --------------------------------------------------------------------------- #


def test_l_api_accepte_la_definition_native_et_refuse_une_action_inconnue():
    requete = CreateToolRequest.model_validate(
        {"name": "demander_un_rappel", "description": "d", "definition": {"schema_version": 1, "type": "native", "config": CONFIG}}
    )
    assert requete.category == "native"
    assert requete.definition.config.call_disposition == ISSUE
    assert [c.champ for c in requete.definition.config.champs_requis] == ["nom", "numero_dicte"]
    with pytest.raises(ValueError):
        CreateToolRequest.model_validate(
            {"name": "x", "definition": {"schema_version": 1, "type": "native", "config": {**CONFIG, "action": "inconnue"}}}
        )
