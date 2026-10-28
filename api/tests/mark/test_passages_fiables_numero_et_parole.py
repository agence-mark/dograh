"""[.mark] passages-fiables, lots C (numéro jamais dicté, relecture des numéros des nouveaux agents) et E (laisser la parole).

| Test | Ce qu'il prouve |
|---|---|
| C1 run 2146 / run 2121 | les deux répliques réelles « 06 06 06 06 06 » et « 51 42 36 78 » sont retenues, le modèle relancé UNE fois |
| C1 numéro d'appel | un numéro égal à celui de l'appel (entrant ou sortant) n'est pas retenu, quelle que soit sa mise en forme |
| C1 dicté | un numéro dicté (espaces, points, indicatif, en deux fois, par la fiche, par un outil) n'est pas retenu |
| C1 clavier | sans numéro d'appel (clavier), le numéro inconnu est retenu |
| C1 flux | le texte d'avant le premier chiffre part tout de suite ; case éteinte : flux identique à la base |
| C1 relance | « l'appelant a déjà entendu » pour la partie partie ; trace lisible dans la fiche de l'appel |
| C2 | un agent créé (définition ou gabarit) a la relecture des numéros allumée ; la valeur lue par défaut reste éteinte |
| E outil | outil offert seulement case allumée, résultat sans nouvelle parole de l'agent |
| E attente | délai de la phrase douce (45 s), phrase douce au lieu de la relance, jamais de raccrochage, parole = attente levée |
| E clavier | l'outil est offert au clavier comme au téléphone ; pas de silence au clavier : écart écrit dans le test de parité |
"""

import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from pipecat.processors.aggregators.llm_context import LLMContext
from pipecat.tests import MockLLMService

from api.routes.workflow import router
from api.schemas.workflow_configurations import WorkflowConfigurationDefaults
from api.services.auth.depends import get_user
from api.services.groupe.reglages import CONFIGURATION_DE_CREATION
from api.services.phrases.catalogue import ATTENTE_ACCORDEE, MOTIFS
from api.services.pipecat.call_monitor_processor import CallMonitorProcessor
from api.services.pipecat.reponse_avalee import ATTRIBUT_NUMERO
from api.services.workflow.laisser_la_parole import (
    CLE_TRACE as TRACE_PAROLE,
    NOM_OUTIL,
    brancher_laisser_la_parole,
)
from api.services.workflow.numero_jamais_dicte import (
    CLE_TRACE,
    CONSIGNE_NUMERO,
    VerificateurDeNumero,
    brancher_le_numero_jamais_dicte,
    suites_de_chiffres,
)
from api.services.workflow.pipecat_engine import PipecatEngine
from api.services.workflow.pipecat_engine_callbacks import delai_de_la_relance, handle_user_idle
from api.tests.mark.test_relance_par_la_voix import _Agregateur, _Moteur as _MoteurSilence
from api.tests.mark.test_verite_des_actions import _Service, _jouer, _morceau, _reponse, _texte


# --------------------------------------------------------------------------- #
# C1 : le numéro jamais dicté
# --------------------------------------------------------------------------- #


def _moteur(appel=None, fiche=None, champs=()):
    return SimpleNamespace(
        _gathered_context=dict(fiche or {}),
        _call_context_vars=appel,
        _fiche=SimpleNamespace(champs=list(champs)),
    )


def _service(moteur, reprise=None, morceaux=(), allume=True):
    service = _Service(list(morceaux), reprise=reprise)
    agent = SimpleNamespace(
        llm=service,
        reglages={"numero_jamais_dicte": allume},
        current_node=SimpleNamespace(name="Étape", is_end=False),
    )
    brancher_le_numero_jamais_dicte(moteur, agent, agent.current_node)
    return service


def _flux(texte):
    return [_morceau(texte), _morceau(fin="stop")]


PAROLES = [{"role": "user", "content": "Bonjour"}]


async def test_c1_run_2146_la_suite_de_zeros_est_retenue_et_le_modele_relance_une_fois():
    moteur = _moteur()
    service = _service(moteur, _reponse("Pouvez-vous me dicter votre numéro ?"), _flux("Je vous rappelle au 06 06 06 06 06."))
    assert _texte(await _jouer(service, PAROLES)) == "Pouvez-vous me dicter votre numéro ?"
    [requete] = service.requetes
    assert requete["stream"] is False
    assert any(CONSIGNE_NUMERO in (m.get("content") or "") for m in requete["messages"])


async def test_c1_run_2121_huit_chiffres_inventes_sont_retenus():
    moteur = _moteur()
    service = _service(moteur, _reponse("Quel est votre numéro ?"), _flux("C'est bien le 51 42 36 78 ?"))
    assert _texte(await _jouer(service, PAROLES)) == "Quel est votre numéro ?"
    assert len(service.requetes) == 1


async def test_c1_la_trace_est_lisible_dans_la_fiche_de_l_appel():
    moteur = _moteur()
    service = _service(moteur, _reponse("ok"), _flux("Le 06 06 06 06 06."))
    await _jouer(service, PAROLES)
    [trace] = moteur._gathered_context[CLE_TRACE]
    assert trace["numero"] == "0606060606" and trace["etape"] == "Étape"
    assert "06 06 06 06 06" in trace["replique"] and trace["raison"] == "numero_jamais_dicte"


@pytest.mark.parametrize("cle", ["caller_number", "called_number"])
@pytest.mark.parametrize("dit", ["06 12 34 56 78", "06.12.34.56.78", "0612345678", "+33 6 12 34 56 78"])
async def test_c1_le_numero_de_l_appel_n_est_pas_retenu(cle, dit):
    moteur = _moteur(appel={cle: "+33612345678"})
    service = _service(moteur, _reponse("jamais"), _flux(f"Je vous rappelle au {dit}."))
    assert _texte(await _jouer(service, PAROLES)).startswith("Je vous rappelle")
    assert service.requetes == []


@pytest.mark.parametrize("dit", ["06 12 34 56 78", "06.12.34.56.78", "0612345678"])
async def test_c1_un_numero_dicte_avec_espaces_ou_points_n_est_pas_retenu(dit):
    moteur = _moteur()
    service = _service(moteur, _reponse("jamais"), _flux(f"Je note le {dit}."))
    paroles = [{"role": "user", "content": "Mon numéro, c'est le 06.12.34.56.78"}]
    assert _texte(await _jouer(service, paroles)).startswith("Je note")
    assert service.requetes == []


async def test_c1_un_numero_dicte_en_deux_fois_n_est_pas_retenu():
    moteur = _moteur()
    service = _service(moteur, _reponse("jamais"), _flux("Donc le 06 12 34 56 78."))
    paroles = [{"role": "user", "content": "C'est le 06 12"}, {"role": "user", "content": "34 56 78"}]
    assert _texte(await _jouer(service, paroles)).startswith("Donc le")
    assert service.requetes == []


async def test_c1_un_numero_de_la_fiche_ou_d_un_resultat_d_outil_n_est_pas_retenu():
    champ = SimpleNamespace(nom="telephone", rempli_par_outil=None)
    moteur = _moteur(fiche={"telephone": "06 12 34 56 78"}, champs=[champ])
    service = _service(moteur, _reponse("jamais"), _flux("Je vous rappelle au 06 12 34 56 78."))
    assert _texte(await _jouer(service, PAROLES)).startswith("Je vous rappelle")
    assert service.requetes == []
    outil = [{"role": "tool", "content": '{"reference": "20261028441"}'}]
    service = _service(_moteur(), _reponse("jamais"), _flux("Votre référence est 20261028441."))
    assert _texte(await _jouer(service, outil)).startswith("Votre référence")
    assert service.requetes == []


async def test_c1_au_clavier_sans_numero_d_appel_le_numero_inconnu_est_retenu():
    moteur = _moteur(appel=None)  # le clavier n'a aucun numéro d'appel
    service = _service(moteur, _reponse("Quel est votre numéro ?"), _flux("Je vous rappelle au 06 12 34 56 78."))
    assert _texte(await _jouer(service, PAROLES)) == "Quel est votre numéro ?"


async def test_c1_sous_huit_chiffres_rien_n_est_retenu():
    moteur = _moteur()
    service = _service(moteur, _reponse("jamais"), _flux("Rendez-vous le 28 10 2026 à 14 h 30, code 4821."))
    assert _texte(await _jouer(service, PAROLES)).startswith("Rendez-vous")
    assert service.requetes == []
    assert suites_de_chiffres("le 06 06 06 06 06 et le 4821") == ["0606060606"]


async def test_c1_la_partie_deja_partie_est_dite_a_la_relance():
    moteur = _moteur()
    service = _service(
        moteur, _reponse("Pouvez-vous le dicter ?"), [_morceau("D'accord, je note. "), _morceau("Le 06 06 06 06 06."), _morceau(fin="stop")]
    )
    morceaux = await _jouer(service, PAROLES)
    # « D'accord, je note. » est parti avant le chiffre ; le reste est remplacé par la relance.
    assert _texte(morceaux) == "D'accord, je note. Pouvez-vous le dicter ?"
    [requete] = service.requetes
    consigne = next(m["content"] for m in requete["messages"] if CONSIGNE_NUMERO in (m.get("content") or ""))
    assert "L'appelant a déjà entendu : « D'accord, je note. »" in consigne


async def test_c1_le_flux_n_est_tenu_qu_a_partir_du_premier_chiffre():
    """Le texte d'avant part tout de suite : le premier morceau sort avant que le suivant ne soit lu."""
    lus: list[int] = []

    class _Progressif(_Service):
        async def get_chat_completions(self, context):
            async def flux():
                for i, m in enumerate(
                    [_morceau("Très bien, "), _morceau("votre numéro : "), _morceau("06 12 34 56 78"), _morceau(fin="stop")]
                ):
                    lus.append(i)
                    yield m

            return flux()

    service = _Progressif([], reprise=_reponse("x"))
    agent = SimpleNamespace(llm=service, reglages={"numero_jamais_dicte": True}, current_node=SimpleNamespace(name="E", is_end=False))
    brancher_le_numero_jamais_dicte(_moteur(), agent, agent.current_node)
    flux = (await service.get_chat_completions(SimpleNamespace(messages=PAROLES))).__aiter__()
    premier = await flux.__anext__()
    assert premier.choices[0].delta.content == "Très bien, "
    assert lus == [0]  # rien de plus n'a été lu : aucune latence ajoutée avant le chiffre
    await flux.__anext__()
    assert lus == [0, 1]


async def test_c1_case_eteinte_aucun_controle_et_flux_identique():
    moteur = _moteur()
    service = _service(moteur, _reponse("jamais"), _flux("Le 06 06 06 06 06."), allume=False)
    assert getattr(service, ATTRIBUT_NUMERO) is None
    assert _texte(await _jouer(service, PAROLES)) == "Le 06 06 06 06 06."
    assert service.requetes == [] and CLE_TRACE not in moteur._gathered_context


async def test_c1_une_etape_de_fin_ou_une_case_eteinte_ne_pose_rien():
    moteur = _moteur()
    agent = SimpleNamespace(llm=SimpleNamespace(), reglages={"numero_jamais_dicte": True})
    assert brancher_le_numero_jamais_dicte(moteur, agent, SimpleNamespace(is_end=True)) is False
    assert getattr(agent.llm, ATTRIBUT_NUMERO) is None
    assert brancher_le_numero_jamais_dicte(moteur, agent, SimpleNamespace(is_end=False)) is True
    assert isinstance(getattr(agent.llm, ATTRIBUT_NUMERO), VerificateurDeNumero)
    assert WorkflowConfigurationDefaults().numero_jamais_dicte is False


# --------------------------------------------------------------------------- #
# C2 : la relecture des numéros allumée à la création
# --------------------------------------------------------------------------- #


def _app():
    app = FastAPI()
    app.include_router(router)
    app.dependency_overrides[get_user] = lambda: SimpleNamespace(id=1, provider_id="p", selected_organization_id=11)
    return app


def _faux_client():
    from datetime import UTC, datetime

    creation = AsyncMock(
        return_value=SimpleNamespace(
            id=5, name="n", status="active", created_at=datetime.now(UTC), current_definition_id=1,
            template_context_variables={}, call_disposition_codes={}, workflow_configurations=dict(CONFIGURATION_DE_CREATION),
        )
    )
    return SimpleNamespace(
        create_workflow=creation,
        assert_trigger_paths_available=AsyncMock(),
        sync_triggers_for_workflow=AsyncMock(),
    )


def test_c2_un_agent_cree_par_la_definition_a_la_relecture_allumee():
    client = _faux_client()
    with patch("api.routes.workflow.db_client", client), patch(
        "api.routes.workflow.validate_workflow_tool_name_collisions", AsyncMock(return_value=[])
    ):
        reponse = TestClient(_app()).post(
            "/workflow/create/definition", json={"name": "Neuf", "workflow_definition": {"nodes": [], "edges": []}}
        )
    assert reponse.status_code == 200, reponse.text
    assert client.create_workflow.await_args.kwargs["workflow_configurations"] == {"relecture_des_numeros": True}


def test_c2_un_agent_cree_par_le_gabarit_a_la_relecture_allumee():
    client = _faux_client()
    appel = AsyncMock(return_value={"name": "Gabarit", "workflow_definition": {"nodes": [], "edges": []}})
    with patch("api.routes.workflow.db_client", client), patch(
        "api.routes.workflow.mps_service_key_client", SimpleNamespace(call_workflow_api=appel)
    ):
        reponse = TestClient(_app()).post(
            "/workflow/create/template", json={"call_type": "inbound", "use_case": "x", "activity_description": "y"}
        )
    assert reponse.status_code == 200, reponse.text
    assert client.create_workflow.await_args.kwargs["workflow_configurations"] == {"relecture_des_numeros": True}


def test_c2_la_valeur_lue_par_defaut_reste_eteinte_donc_aucun_agent_existant_ne_change():
    from api.services.pipecat.filtre_nom_civilite import creer_filtre_nom_civilite

    assert WorkflowConfigurationDefaults().relecture_des_numeros is False
    # un agent d'avant n'a pas la clé : le filtre de relecture n'est pas armé ; un agent neuf (clé écrite) l'est
    assert creer_filtre_nom_civilite({}, lambda: {}) is None
    assert creer_filtre_nom_civilite(dict(CONFIGURATION_DE_CREATION), lambda: {}) is not None


async def test_c2_la_base_ecrit_la_configuration_de_creation(db_session):
    """La configuration écrite à la création arrive dans l'agent ET dans sa première définition."""
    from api.db import db_client  # noqa: F401  (le fixture db_session est le même client)

    cree = await db_session.create_workflow(
        name="Création C2", workflow_definition={"nodes": [], "edges": []}, user_id=None,
        workflow_configurations=CONFIGURATION_DE_CREATION,
    )
    assert cree.workflow_configurations == {"relecture_des_numeros": True}
    ancien = await db_session.create_workflow(name="Ancien C2", workflow_definition={"nodes": [], "edges": []}, user_id=None)
    assert "relecture_des_numeros" not in (ancien.workflow_configurations or {})


# --------------------------------------------------------------------------- #
# E : laisser la parole
# --------------------------------------------------------------------------- #


class _Agent:
    def __init__(self, reglages):
        self.reglages = reglages
        self.current_node = SimpleNamespace(name="Étape", is_end=False)
        self.enregistres = {}
        self.llm = SimpleNamespace(register_function=lambda nom, f: self.enregistres.update({nom: f}))

    def bind_tool(self, moteur, f):
        return f


def _moniteur(**reglages):
    moniteur = CallMonitorProcessor(
        response_source=lambda: None, on_response_timeout=lambda _s: None, on_user_idle=None,
        conversation_enabled=lambda: True,
    )
    moniteur.user_idle_timeout = 10.0
    moniteur.user_aggregator = SimpleNamespace(user_turn_controller=SimpleNamespace(has_active_user_turn=False))
    moniteur._active = True
    moniteur._waiting_for_user = True
    for nom, valeur in reglages.items():
        setattr(moniteur, nom, valeur)
    return moniteur


def test_e_l_outil_n_est_offert_que_case_allumee():
    moteur = SimpleNamespace(call_monitor=_moniteur(), _gathered_context={})
    eteinte = _Agent({})
    assert brancher_laisser_la_parole(moteur, eteinte, eteinte.current_node) is None and eteinte.enregistres == {}
    allumee = _Agent({"laisser_la_parole": True})
    schema = brancher_laisser_la_parole(moteur, allumee, allumee.current_node)
    assert schema.name == NOM_OUTIL and NOM_OUTIL in allumee.enregistres
    fin = _Agent({"laisser_la_parole": True})
    fin.current_node = SimpleNamespace(name="Fin", is_end=True)
    assert brancher_laisser_la_parole(moteur, fin, fin.current_node) is None
    assert WorkflowConfigurationDefaults().laisser_la_parole is False


async def test_e_l_outil_accorde_l_attente_et_ne_fait_pas_reparler_l_agent():
    moteur = SimpleNamespace(call_monitor=_moniteur(), _gathered_context={})
    agent = _Agent({"laisser_la_parole": True})
    brancher_laisser_la_parole(moteur, agent, agent.current_node)
    rendu = {}

    async def result_callback(valeur, properties=None):
        rendu["valeur"], rendu["properties"] = valeur, properties

    await agent.enregistres[NOM_OUTIL](SimpleNamespace(result_callback=result_callback))
    assert moteur.call_monitor.attente_accordee is True
    assert rendu["properties"].run_llm is False
    assert moteur._gathered_context[TRACE_PAROLE][0]["evenement"] == "accordee"
    moteur.call_monitor._cancel_deadline()


async def test_e_le_delai_de_l_attente_est_celui_de_la_phrase_douce_45_s_par_defaut():
    moteur = _MoteurSilence()
    assert MOTIFS[ATTENTE_ACCORDEE].delai_defaut_s == 45.0
    assert delai_de_la_relance(moteur) is None  # pas d'attente : le délai de Rythme
    moteur.call_monitor.attente_accordee = True
    assert delai_de_la_relance(moteur) == 45.0
    moteur.active_agent.reglages = {
        "phrases_regles": [{"motif": ATTENTE_ACCORDEE, "portee": "agent", "variantes": ["Je reste là."], "delai_s": 20, "active": True}]
    }
    assert delai_de_la_relance(moteur) == 20


async def test_e_pas_de_relance_avant_le_delai_le_moniteur_arme_le_delai_de_l_attente():
    moniteur = _moniteur(delai_de_relance=lambda: 45.0 if moniteur.attente_accordee else None)
    moniteur._arm_idle()
    loop = asyncio.get_running_loop()
    assert 9 < moniteur._deadline.when() - loop.time() <= 10
    moniteur.accorder_l_attente()  # re-arme avec le délai de l'attente
    assert moniteur._deadline_kind == "idle" and 44 < moniteur._deadline.when() - loop.time() <= 45
    moniteur._cancel_deadline()


async def test_e_une_reponse_due_ne_finit_pas_en_delai_de_reponse():
    moniteur = _moniteur()
    moniteur._response_watch = object()  # l'outil seul, sans parole : une réponse resterait « due »
    moniteur.accorder_l_attente()
    assert moniteur._response_watch is None
    moniteur._cancel_deadline()


class _MoteurAttente(_MoteurSilence):
    def __init__(self, **kw):
        super().__init__(**kw)
        self.call_monitor = _moniteur()
        self.call_monitor.attente_accordee = True


async def test_e_au_delai_la_phrase_douce_remplace_la_relance_et_il_n_y_a_jamais_de_raccrochage():
    moteur = _MoteurAttente(relances={"user_idle_max_prompts": 0})  # sans attente, la première relance raccrocherait
    agregateur = _Agregateur()
    await handle_user_idle(moteur, agregateur, 1)
    await moteur.phrases.attendre_la_fin()
    assert moteur.dites == ["Prenez votre temps, je suis toujours là."]
    assert agregateur.consignes == [] and moteur.raccroche is None
    assert moteur.call_monitor.attente_accordee is False  # puis le comportement normal reprend
    assert [t["evenement"] for t in moteur._gathered_context[TRACE_PAROLE]] == ["relance_douce_dite"]
    moteur.call_monitor._cancel_deadline()


async def test_e_la_phrase_douce_est_modifiable_a_l_ecran_et_eteinte_elle_se_tait_sans_raccrocher():
    moteur = _MoteurAttente()
    moteur.active_agent.reglages = {
        "phrases_regles": [{"motif": ATTENTE_ACCORDEE, "portee": "agent", "variantes": ["Je reste là."], "active": True}]
    }
    await handle_user_idle(moteur, _Agregateur(), 1)
    await moteur.phrases.attendre_la_fin()
    assert moteur.dites == ["Je reste là."]
    muet = _MoteurAttente()
    muet.active_agent.reglages = {
        "phrases_regles": [{"motif": ATTENTE_ACCORDEE, "portee": "agent", "variantes": ["x"], "active": False}]
    }
    agregateur = _Agregateur()
    await handle_user_idle(muet, agregateur, 1)
    assert muet.dites == [] and agregateur.consignes == [] and muet.raccroche is None
    assert muet.call_monitor.attente_accordee is False


async def test_e_la_personne_qui_reparle_leve_l_attente():
    moniteur = _moniteur()
    leves = []
    moniteur.sur_attente_levee = lambda: leves.append(True)
    moniteur.accorder_l_attente()
    assert moniteur.attente_accordee is True
    moniteur._user_started()
    assert moniteur.attente_accordee is False and leves == [True]
    moniteur._cancel_deadline()


async def test_e_sans_attente_la_relance_normale_et_le_raccrochage_sont_inchanges():
    moteur = _MoteurSilence(relances={"user_idle_max_prompts": 0})
    moteur.call_monitor = _moniteur()
    await handle_user_idle(moteur, _Agregateur(), 1)
    assert moteur.raccroche is not None  # sans l'attente : le comportement d'avant


async def test_e_un_vrai_moteur_offre_l_outil_case_allumee_et_pas_case_eteinte(three_node_workflow, no_disposition_mapping):
    """Le branchement est dans le moteur (téléphone et clavier : même `set_node`)."""

    async def outils(reglages):
        moteur = PipecatEngine(
            llm=MockLLMService(), context=LLMContext(), workflow=three_node_workflow, call_context_vars={}, workflow_run_id=1
        )
        moteur.active_agent.reglages = reglages
        vus: list[list[str]] = []
        origine = moteur._update_llm_context

        async def espion(prompt, fonctions):
            vus.append([f.name for f in fonctions])
            return await origine(prompt, fonctions)

        moteur._update_llm_context = espion
        await moteur.set_node(moteur.active_agent.workflow.start_node_id)
        return vus[-1]

    assert NOM_OUTIL in await outils({"laisser_la_parole": True})
    assert NOM_OUTIL not in await outils({})
