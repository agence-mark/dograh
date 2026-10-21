"""[.mark] Lot 4 d'orchestrateur-trois-cerveaux (D8, D9, D12, D13) : le cerveau de fond.

Un agent dont « Travail en arrière-plan » est allumé peut confier une demande à un second cerveau qui
travaille avec ses outils pendant que la conversation continue, puis reçoit le résultat. Ces tests
passent par la VRAIE route (le banc de passation de l'amont, avec la voix de l'appel : moteur, pont,
bus, workers d'agent, worker de fond, job, agrégateurs, outils) ; seuls les modèles (scénarisés) et la
voix sont des stand-ins.

| Test | La garantie |
|---|---|
| route complète | le modèle de conversation appelle « confier », l'outil rend « lancé » tout de suite, le fond appelle son outil et répond, le résultat entre dans la conversation et l'agent actif le dit |
| micro jamais coupé | pendant tout le travail, l'appelant n'est jamais muet à cause du travail (l'outil rend avant que le fond ne commence) |
| résultat gardé | un résultat qui arrive pendant que le robot parle attend la fin de la parole |
| après une passation | un résultat qui arrive après une passation est lu par le NOUVEL agent |
| deux « confier » | un second « confier » pendant un travail annule le premier et lance le nouveau (fiabilite-orchestration, F2) |
| échec et délai | un fond qui échoue ou dépasse son délai rend un résultat qui le dit, jamais une exception dans l'appel |
| éteint par défaut | un agent sans réglage n'a ni outil, ni worker, ni rien dans la requête |
| coût | les jetons du fond sont versés au collecteur de l'appel |
| trace | la fiche garde le travail : demande, outils appelés, durée, statut, jetons |
| worker neuf | après un délai dépassé, le travail suivant part sur un worker neuf (contexte vierge, service refait) : la fin tardive de l'ancien ne fausse jamais le suivant |
| outils gardés | un agent qui se retire pendant un travail garde ses sessions MCP jusqu'à la fin du travail, puis les ferme |
"""

import asyncio
import contextlib
from types import SimpleNamespace
from unittest.mock import AsyncMock, PropertyMock, patch

import pytest
from openai.types.completion_usage import CompletionUsage
from pipecat.adapters.schemas.function_schema import FunctionSchema
from pipecat.tests import MockLLMService

from api.services.groupe.passations import (
    PREFIXE_RESULTAT_DU_TRAVAIL,
    est_la_note_de_passation,
    est_un_resultat_de_travail,
)
from api.services.pipecat.pipeline_metrics_aggregator import PipelineMetricsAggregator
from api.services.travail.reglages import NOM_OUTIL, ReglagesTravail
from api.services.workflow.pipecat_engine_custom_tools import CustomToolManager
from api.tests.mark.banc_voix import brancher_la_parole_locale, voix_de_l_appel
from api.tests.test_agent_transfer import (
    TRANSFER_TOOL_UUID,
    TransferAgentTool,
    TransferHarness,
    build_agent_workflow,
)

DEMANDE = "Cherche un créneau libre demain et rends-le moi."
RESULTAT = "Créneau libre demain à 14 h."
PAROLE_ATTENTE = "Je regarde ça avec vous."
PAROLE_FINALE = "J'ai trouvé : demain à 14 h."


def _appel_d_outil(nom, arguments, identifiant):
    return MockLLMService.create_function_call_chunks(nom, arguments, tool_call_id=identifiant)


def _texte(texte, *, jetons=None):
    morceaux = MockLLMService.create_text_chunks(texte)
    if jetons is not None:
        morceaux[-1].usage = CompletionUsage(
            prompt_tokens=jetons[0],
            completion_tokens=jetons[1],
            total_tokens=jetons[0] + jetons[1],
        )
    return morceaux



def _avec_le_fond(graphe, etape_cochee=True):
    """modules-et-cerveaux (lot 5, M3) : l'étape de départ porte « Travail en arrière-plan »."""
    graphe.nodes["start"].travail_de_fond = etape_cochee
    return graphe

class Appel:
    """Un appel monté sur le banc de l'amont, avec un agent qui peut confier du travail."""

    def __init__(self):
        self.harness = TransferHarness()
        self.outil_du_fond_appele: list[dict] = []
        # Si posé, l'outil du fond attend ce signal avant de répondre (un fond volontairement lent).
        self.portail: asyncio.Event | None = None
        self.collecteur = PipelineMetricsAggregator()

    @property
    def engine(self):
        return self.harness.engine

    @property
    def source_llm(self):
        return self._source_llm

    async def monter(
        self,
        *,
        source_etapes,
        fond_etapes,
        reglages=None,
        outils_du_fond=True,
        destination_etapes=None,
        tool_uuids=None,
        delai_max_s=60,
        etape_cochee=True,
    ):
        self._source_llm = MockLLMService(mock_steps=source_etapes, chunk_delay=0.001)
        self.fond_llm = MockLLMService(mock_steps=fond_etapes, chunk_delay=0.001)
        self._banc_ctx = voix_de_l_appel()
        self.banc = self._banc_ctx.__enter__()
        await self.harness.build(
            source_llm=self._source_llm,
            destination_llm=MockLLMService(
                mock_steps=destination_etapes or [_texte("Ici l'autre agent.")],
                chunk_delay=0.001,
            ),
            source_workflow=_avec_le_fond(
                build_agent_workflow(name="Accueil", greeting=None, tool_uuids=tool_uuids or []),
                etape_cochee,
            ),
            destination_workflow=build_agent_workflow(name="Autre", greeting=None),
        )
        brancher_la_parole_locale(self.harness, self.banc)
        moteur = self.engine
        moteur._get_organization_id = AsyncMock(return_value=1)
        moteur._custom_tool_manager = CustomToolManager(moteur)
        moteur.collecteur_de_cout = self.collecteur
        source = moteur.active_agent
        source.reglages = (
            reglages
            if reglages is not None
            else {"travail_actif": True, "travail_delai_max_s": delai_max_s}
        )
        source.user_config = SimpleNamespace()

        async def fausse_preparation(run_configs, user_config, organisation, runtime, **_):
            return ReglagesTravail.depuis(run_configs), self.fond_llm

        async def faux_outils(moteur_, agent_, llm, uuids, muet=None):
            if not outils_du_fond:
                return [], []

            async def chercher(params):
                self.outil_du_fond_appele.append(dict(params.arguments))
                if self.portail is not None:
                    await self.portail.wait()
                await params.result_callback({"creneau": "14h"})

            llm.register_function("chercher_creneau", chercher)
            return [
                FunctionSchema(
                    name="chercher_creneau",
                    description="Cherche un créneau.",
                    properties={"jour": {"type": "string"}},
                    required=["jour"],
                )
            ], ["chercher_creneau"]

        self._patchs = [
            patch(
                "api.services.travail.agent.preparer_le_service_du_travail",
                fausse_preparation,
            ),
            patch("api.services.travail.agent.preparer_les_outils", faux_outils),
        ]
        for p in self._patchs:
            p.start()
        await moteur.preparer_le_travail(source, attacher=False)
        await self.harness.start()
        return self

    async def ouvrir(self):
        """L'ouverture de l'étape : le modèle de conversation joue sa première étape."""
        moteur = self.engine
        await moteur.set_node("start")
        await moteur.queue_node_opening(
            node_id="start", previous_node_id=None, generate_if_no_greeting=True
        )

    async def attendre(self, condition, delai=15.0, pas=0.02):
        async with asyncio.timeout(delai):
            while not condition():
                await asyncio.sleep(pas)

    async def arreter(self):
        for p in getattr(self, "_patchs", []):
            with contextlib.suppress(Exception):
                p.stop()
        try:
            await self.harness.stop()
        finally:
            self._banc_ctx.__exit__(None, None, None)

    def messages(self):
        return self.engine.context.get_messages()

    def travaux(self):
        return self.engine._gathered_context.get("travaux", [])


@pytest.fixture
async def appel():
    a = Appel()
    try:
        yield a
    finally:
        await a.arreter()


# --------------------------------------------------------------------------- #
# La route complète
# --------------------------------------------------------------------------- #


@pytest.mark.asyncio
async def test_une_demande_confiee_revient_et_l_agent_la_dit(appel):
    """Confier → « lancé » → le fond travaille avec son outil → le résultat entre dans la
    conversation → l'agent actif le dit (3e génération du modèle de conversation)."""
    await appel.monter(
        source_etapes=[
            _appel_d_outil(NOM_OUTIL, {"demande": DEMANDE}, "call_confier"),
            _texte(PAROLE_ATTENTE),
            _texte(PAROLE_FINALE),
        ],
        fond_etapes=[
            _appel_d_outil("chercher_creneau", {"jour": "demain"}, "call_fond"),
            _texte(RESULTAT, jetons=(120, 30)),
        ],
    )
    await appel.ouvrir()
    await appel.attendre(lambda: appel.travaux() and appel.travaux()[0]["remis"])
    await appel.attendre(lambda: appel.source_llm.get_current_step() >= 3)

    # L'outil du fond a été appelé avec ce que le fond a décidé.
    assert appel.outil_du_fond_appele == [{"jour": "demain"}]
    # Le résultat est dans la conversation de l'appel, sous la forme du code.
    resultats = [m for m in appel.messages() if est_un_resultat_de_travail(m)]
    assert len(resultats) == 1
    assert resultats[0]["role"] == "user"
    assert resultats[0]["content"] == f"{PREFIXE_RESULTAT_DU_TRAVAIL} {RESULTAT}]"
    # Le modèle de conversation a parlé trois fois : confier, « je regarde », puis le résultat.
    assert appel.source_llm.get_current_step() == 3
    # La demande confiée est bien celle que le modèle de conversation a écrite.
    trace = appel.travaux()[0]
    assert trace["demande"] == DEMANDE
    assert trace["statut"] == "fait"
    assert trace["outils"] == ["chercher_creneau"]
    assert trace["resultat"] == RESULTAT
    assert trace["duree_ms"] is not None
    assert (trace["jetons_entree"], trace["jetons_sortie"]) == (120, 30)


@pytest.mark.asyncio
async def test_le_resultat_n_est_jamais_une_parole_de_l_appelant(appel):
    """Marqué comme la note de passation : exclu des paroles de l'appelant, de l'historique de
    passation et du greffier."""
    await appel.monter(
        source_etapes=[
            _appel_d_outil(NOM_OUTIL, {"demande": DEMANDE}, "call_confier"),
            _texte(PAROLE_ATTENTE),
            _texte(PAROLE_FINALE),
        ],
        fond_etapes=[_texte(RESULTAT)],
        outils_du_fond=False,
    )
    await appel.ouvrir()
    await appel.attendre(lambda: appel.travaux() and appel.travaux()[0]["remis"])
    # « remis » part avant que le message n'arrive au contexte : on attend le message lui-même
    # (le test échouait sous la charge de la suite complète, relecture du lot 6).
    await appel.attendre(lambda: any(est_un_resultat_de_travail(m) for m in appel.messages()))
    resultat = next(m for m in appel.messages() if est_un_resultat_de_travail(m))
    assert est_la_note_de_passation(resultat)

    from api.services.pipecat.greffier import _derniere_replique
    from api.services.workflow.agent_handoff_context import conversation_messages
    from api.services.workflow.fiche_au_fil_de_leau import paroles_de_l_appelant

    messages = appel.messages()
    assert paroles_de_l_appelant(messages) == []
    assert _derniere_replique(messages) is None
    assert resultat not in conversation_messages(messages)


@pytest.mark.asyncio
async def test_l_outil_rend_lance_tout_de_suite_le_fond_n_a_pas_encore_fini(appel):
    """Le micro de l'appelant n'est jamais coupé par le travail : l'outil rend « lancé » avant
    que le fond n'ait fini (le fond est volontairement lent)."""
    appel.portail = asyncio.Event()
    await appel.monter(
        source_etapes=[
            _appel_d_outil(NOM_OUTIL, {"demande": DEMANDE}, "call_confier"),
            _texte(PAROLE_ATTENTE),
            _texte(PAROLE_FINALE),
        ],
        fond_etapes=[
            _appel_d_outil("chercher_creneau", {"jour": "demain"}, "call_fond"),
            _texte(RESULTAT),
        ],
    )
    await appel.ouvrir()
    # Le modèle de conversation a déjà repris la parole (2e génération) alors que le fond travaille.
    await appel.attendre(lambda: appel.source_llm.get_current_step() >= 2)
    assert appel.engine.active_agent.travail.occupe is True
    assert appel.travaux()[0]["statut"] == "en_cours"
    # Le fond n'a posé aucune coupure de l'appelant : ni muet de l'appel, ni parole en attente.
    assert appel.engine._mute_pipeline is False
    assert appel.engine.speech_playback.mutes_user is False
    appel.portail.set()
    await appel.attendre(lambda: appel.travaux()[0]["remis"])
    assert appel.travaux()[0]["statut"] == "fait"


@pytest.mark.asyncio
async def test_un_second_confier_pendant_un_travail_remplace_le_premier(appel):
    """Une seule tâche à la fois par agent ; fiabilite-orchestration (F2) : le 2e « confier »
    annule la demande en cours et lance la nouvelle (modifier = annuler + confier)."""
    await appel.monter(
        source_etapes=[_texte("rien")],
        fond_etapes=[_texte(RESULTAT)],
        outils_du_fond=False,
    )
    travail = appel.engine.active_agent.travail
    portail = asyncio.Event()
    vues: list[str] = []

    async def bloque(_travail, demande):
        vues.append(demande)
        await portail.wait()
        return RESULTAT

    travail._executeur = bloque
    premier = await travail.confier(DEMANDE)
    await appel.attendre(lambda: vues == [DEMANDE])
    second = await travail.confier("Autre chose")
    assert premier == {"statut": "lancé"}
    assert second == {"statut": "lancé", "demande_precedente": "annulée"}
    assert [t["statut"] for t in appel.travaux()] == ["annule", "en_cours"]
    assert appel.travaux()[0]["remis"] is False
    portail.set()
    await travail.attendre()
    assert travail.occupe is False
    assert [t["demande"] for t in appel.travaux()] == [DEMANDE, "Autre chose"]
    assert appel.travaux()[1]["statut"] == "fait"


# --------------------------------------------------------------------------- #
# Le résultat est gardé, puis routé vers l'agent qui a la main
# --------------------------------------------------------------------------- #


@pytest.mark.asyncio
async def test_le_resultat_attend_que_l_appel_soit_calme(appel):
    """Tant que le robot parle (ou que l'appelant parle), le résultat attend ; dès que l'appel est
    calme, il part."""
    await appel.monter(
        source_etapes=[_texte("rien")],
        fond_etapes=[_texte(RESULTAT)],
        outils_du_fond=False,
    )
    moteur = appel.engine
    calme = PropertyMock(return_value=False)
    with patch.object(type(moteur.call_monitor), "appel_au_calme", calme):
        travail = moteur.active_agent.travail
        await travail.confier(DEMANDE)
        await appel.attendre(lambda: appel.travaux()[0]["statut"] == "fait", delai=5)
        await asyncio.sleep(0.4)
        # Le travail est fini, mais l'appel n'est pas calme : rien n'est entré dans la conversation.
        assert appel.travaux()[0]["statut"] == "fait"
        assert appel.travaux()[0]["remis"] is False
        assert not [m for m in appel.messages() if est_un_resultat_de_travail(m)]
        calme.return_value = True
        await appel.attendre(lambda: appel.travaux()[0]["remis"], delai=5)
        await appel.attendre(
            lambda: any(est_un_resultat_de_travail(m) for m in appel.messages()), delai=5
        )


@pytest.mark.asyncio
async def test_un_resultat_apres_une_passation_est_lu_par_le_nouvel_agent(appel):
    """Le résultat est routé vers l'agent ACTIF au moment de la remise, jamais vers celui qui
    avait confié : le modèle de conversation confie, puis passe la main ; le fond finit après."""
    appel.portail = asyncio.Event()
    with patch(
        "api.services.workflow.pipecat_engine_custom_tools.db_client.get_tools_by_uuids",
        new_callable=AsyncMock,
        return_value=[TransferAgentTool(message=None)],
    ):
        await appel.monter(
            source_etapes=[
                _appel_d_outil(NOM_OUTIL, {"demande": DEMANDE}, "call_confier"),
                _appel_d_outil("transfer_to_billing", {}, "call_transfer"),
            ],
            fond_etapes=[
                _appel_d_outil("chercher_creneau", {"jour": "demain"}, "call_fond"),
                _texte(RESULTAT),
            ],
            tool_uuids=[TRANSFER_TOOL_UUID],
            destination_etapes=[_texte("Je vous écoute."), _texte("Je lis le résultat.")],
        )
        source = appel.engine.active_agent
        await appel.ouvrir()
        await appel.attendre(lambda: appel.engine.active_agent is not source)
        assert source.travail.occupe, "le fond travaille encore quand la passation a lieu"

        # Le résultat arrive APRÈS la passation : c'est le nouvel agent qui le lit.
        appel.portail.set()
        await appel.attendre(lambda: appel.travaux()[0]["remis"])
        await appel.attendre(lambda: appel.harness.destination_llm.get_current_step() >= 2)
        assert appel.engine.active_agent is not source
        assert [m for m in appel.messages() if est_un_resultat_de_travail(m)]
        # Le modèle de la SOURCE n'a pas été relancé pour le résultat (2 générations seulement).
        assert appel.source_llm.get_current_step() == 2


# --------------------------------------------------------------------------- #
# Échec, délai
# --------------------------------------------------------------------------- #


@pytest.mark.asyncio
async def test_un_fond_qui_echoue_rend_un_resultat_qui_le_dit(appel):
    await appel.monter(
        source_etapes=[_texte("rien")], fond_etapes=[_texte(RESULTAT)], outils_du_fond=False
    )
    travail = appel.engine.active_agent.travail

    async def echoue(_travail, _demande):
        raise RuntimeError("clé-secrète-du-fournisseur")

    travail._executeur = echoue
    await travail.confier(DEMANDE)
    await travail.attendre()
    await appel.attendre(lambda: appel.travaux()[0]["remis"])
    trace = appel.travaux()[0]
    assert trace["statut"] == "echec"
    await appel.attendre(lambda: any(est_un_resultat_de_travail(m) for m in appel.messages()))
    resultat = next(m for m in appel.messages() if est_un_resultat_de_travail(m))
    assert "n'a pas abouti" in resultat["content"]
    # Le texte de l'erreur (qui pourrait citer une clé) n'est jamais dans la conversation ni la trace.
    assert "secrète" not in resultat["content"]
    assert "secrète" not in str(trace)
    assert not appel.engine.is_call_disposed()


@pytest.mark.asyncio
async def test_un_fond_trop_lent_rend_un_resultat_de_delai(appel):
    appel.portail = asyncio.Event()
    await appel.monter(
        source_etapes=[_texte("rien")],
        fond_etapes=[_appel_d_outil("chercher_creneau", {"jour": "demain"}, "call_fond"), _texte(RESULTAT)],
        delai_max_s=5,
    )
    # Le fond attend 30 s ; le délai réglé est le plus petit permis (5 s) : on le raccourcit pour le test.
    travail = appel.engine.active_agent.travail
    travail.reglages = ReglagesTravail(actif=True, delai_max_s=1)
    await travail.confier(DEMANDE)
    await appel.attendre(lambda: appel.travaux()[0]["remis"], delai=20)
    appel.portail.set()
    trace = appel.travaux()[0]
    assert trace["statut"] == "delai"
    await appel.attendre(lambda: any(est_un_resultat_de_travail(m) for m in appel.messages()))
    resultat = next(m for m in appel.messages() if est_un_resultat_de_travail(m))
    assert "temps imparti" in resultat["content"]
    assert not appel.engine.is_call_disposed()


@pytest.mark.asyncio
async def test_la_fin_de_l_appel_annule_le_travail(appel):
    await appel.monter(
        source_etapes=[_texte("rien")], fond_etapes=[_texte(RESULTAT)], outils_du_fond=False
    )
    travail = appel.engine.active_agent.travail
    portail = asyncio.Event()

    async def bloque(_travail, _demande):
        await portail.wait()
        return RESULTAT

    travail._executeur = bloque
    await travail.confier(DEMANDE)
    assert travail.occupe
    await appel.engine.cleanup()
    assert travail.occupe is False
    assert appel.travaux()[0]["statut"] == "annule"
    assert not [m for m in appel.messages() if est_un_resultat_de_travail(m)]


# --------------------------------------------------------------------------- #
# Éteint par défaut
# --------------------------------------------------------------------------- #


@pytest.mark.asyncio
async def test_un_agent_sans_reglage_n_a_ni_outil_ni_worker(appel):
    await appel.monter(
        source_etapes=[_texte("Bonjour.")], fond_etapes=[_texte(RESULTAT)], reglages={}
    )
    moteur = appel.engine
    agent = moteur.active_agent
    assert agent.travail is None
    assert moteur.travaux == []
    await appel.ouvrir()
    noms = [f.name for f in agent.tools.standard_tools]
    assert NOM_OUTIL not in noms
    assert NOM_OUTIL not in (agent.llm._functions or {})
    assert not any(n.startswith("travail-") for n in moteur.call_worker.children_names()) if hasattr(
        moteur.call_worker, "children_names"
    ) else True


@pytest.mark.asyncio
async def test_un_agent_regle_a_l_outil_confier_dans_sa_requete(appel):
    await appel.monter(
        source_etapes=[_texte("Bonjour.")], fond_etapes=[_texte(RESULTAT)], outils_du_fond=False
    )
    await appel.ouvrir()
    agent = appel.engine.active_agent
    noms = [f.name for f in agent.tools.standard_tools]
    assert NOM_OUTIL in noms
    schema = next(f for f in agent.tools.standard_tools if f.name == NOM_OUTIL)
    assert list(schema.properties) == ["demande"]
    assert schema.required == ["demande"]


@pytest.mark.asyncio
async def test_une_etape_non_cochee_n_offre_pas_confier(appel):
    """modules-et-cerveaux (lot 5, M3, run 1462) : le fond allumé pour l'agent ne suffit plus ;
    l'outil n'est offert qu'aux étapes cochées."""
    await appel.monter(
        source_etapes=[_texte("Bonjour.")],
        fond_etapes=[_texte(RESULTAT)],
        outils_du_fond=False,
        etape_cochee=False,
    )
    await appel.ouvrir()
    agent = appel.engine.active_agent
    assert agent.travail is not None
    assert NOM_OUTIL not in [f.name for f in agent.tools.standard_tools]
    assert NOM_OUTIL not in (agent.llm._functions or {})


def test_la_case_de_l_etape_traverse_la_definition_de_l_agent():
    """La clé ``travail_de_fond`` est déclarée au DTO (une clé inconnue serait perdue) et
    arrive sur l'étape du graphe ; absente, l'étape n'offre rien."""
    from api.services.workflow.dto import ReactFlowDTO
    from api.services.workflow.workflow_graph import WorkflowGraph

    def graphe(data_depart, data_etape):
        return WorkflowGraph(
            ReactFlowDTO.model_validate(
                {
                    "nodes": [
                        {"id": "a", "type": "startCall", "position": {"x": 0, "y": 0},
                         "data": {"name": "accueil", "prompt": "p", **data_depart}},
                        {"id": "b", "type": "agentNode", "position": {"x": 0, "y": 1},
                         "data": {"name": "rendez_vous", "prompt": "p", **data_etape}},
                        {"id": "c", "type": "endCall", "position": {"x": 0, "y": 2},
                         "data": {"name": "fin", "prompt": "p"}},
                    ],
                    "edges": [
                        {"id": "ab", "source": "a", "target": "b",
                         "data": {"label": "rdv", "condition": "rdv"}},
                        {"id": "bc", "source": "b", "target": "c",
                         "data": {"label": "fin", "condition": "fin"}},
                    ],
                }
            )
        )

    coche = graphe({}, {"travail_de_fond": True})
    assert coche.nodes["b"].travail_de_fond is True
    assert coche.nodes["a"].travail_de_fond is False
    depart = graphe({"travail_de_fond": True}, {})
    assert depart.nodes["a"].travail_de_fond is True
    dto = ReactFlowDTO.model_validate(
        {"nodes": [{"id": "b", "type": "agentNode", "position": {"x": 0, "y": 0},
                    "data": {"name": "e", "prompt": "p", "travail_de_fond": True}}], "edges": []}
    )
    assert dto.model_dump()["nodes"][0]["data"]["travail_de_fond"] is True


@pytest.mark.asyncio
async def test_le_service_impossible_a_construire_joue_l_agent_sans_fond(appel):
    """Un échec de construction retombe sur l'appel d'avant, jamais un appel cassé."""
    appel_ = appel
    await appel_.monter(
        source_etapes=[_texte("Bonjour.")], fond_etapes=[_texte(RESULTAT)], reglages={}
    )
    agent = appel_.engine.active_agent
    agent.reglages = {"travail_actif": True}
    with patch(
        "api.services.travail.agent.preparer_le_service_du_travail",
        AsyncMock(return_value=(None, None)),
    ):
        await appel_.engine.preparer_le_travail(agent, attacher=False)
    assert agent.travail is None
    await appel_.ouvrir()
    assert NOM_OUTIL not in [f.name for f in agent.tools.standard_tools]


# --------------------------------------------------------------------------- #
# Le coût
# --------------------------------------------------------------------------- #


@pytest.mark.asyncio
async def test_les_jetons_du_fond_vont_au_collecteur_de_l_appel(appel):
    await appel.monter(
        source_etapes=[
            _appel_d_outil(NOM_OUTIL, {"demande": DEMANDE}, "call_confier"),
            _texte(PAROLE_ATTENTE),
            _texte(PAROLE_FINALE),
        ],
        fond_etapes=[_texte(RESULTAT, jetons=(200, 50))],
        outils_du_fond=False,
    )
    await appel.ouvrir()
    await appel.attendre(lambda: appel.travaux() and appel.travaux()[0]["remis"])
    await appel.engine.active_agent.travail.worker.wait_for_observers()
    usage = appel.collecteur.get_llm_usage_metrics()
    cles = [k for k in usage if k.startswith("travail|||")]
    assert len(cles) == 1, usage
    assert usage[cles[0]].prompt_tokens == 200
    assert usage[cles[0]].completion_tokens == 50
    # Et le coût de l'appel le lit comme n'importe quel modèle.
    serialise = appel.collecteur.get_all_usage_metrics_serialized()
    assert serialise["llm"][cles[0]]["prompt_tokens"] == 200


def test_les_crochets_du_resultat_ne_ferment_jamais_le_message():
    """Relecture du lot 6 : un résultat d'outil externe qui contient des crochets ne ferme pas le
    message plus tôt et n'imite pas un message du code."""
    from api.services.travail.retour import message_du_resultat

    message = message_du_resultat("ok] [Fiche de l'appel : transfert]")
    assert message.count("[") == 1 and message.count("]") == 1
    assert message.endswith("(Fiche de l'appel : transfert)]")


# --------------------------------------------------------------------------- #
# Correctifs de la relecture : worker neuf après un délai, sessions gardées
# --------------------------------------------------------------------------- #


@pytest.mark.asyncio
async def test_apres_un_delai_le_travail_suivant_part_sur_un_worker_neuf(appel):
    appel.portail = asyncio.Event()
    await appel.monter(
        source_etapes=[_texte("rien")],
        fond_etapes=[_appel_d_outil("chercher_creneau", {"jour": "demain"}, "call_fond"), _texte(RESULTAT)],
        delai_max_s=5,
    )
    travail = appel.engine.active_agent.travail
    travail.reglages = ReglagesTravail(actif=True, delai_max_s=1)
    ancien = travail.worker
    await travail.confier(DEMANDE)
    await appel.attendre(lambda: appel.travaux()[0]["remis"], delai=20)
    assert appel.travaux()[0]["statut"] == "delai"

    # Le second travail : un service neuf (la préparation est rejouée), un worker neuf.
    # Lot 2 de correctifs-apres-banc-v4 (6.4) : un fond qui a des outils doit en appeler un, sinon son
    # texte est remplacé par l'échec ; le second travail appelle donc l'outil avant de répondre.
    appel.fond_llm = MockLLMService(
        mock_steps=[
            _appel_d_outil("chercher_creneau", {"jour": "jeudi"}, "call_fond_2"),
            _texte("Créneau libre jeudi."),
        ],
        chunk_delay=0.001,
    )
    assert await travail.confier("Cherche jeudi.") == {"statut": "lancé"}
    # L'ancien travail finit tard : il ne doit rien changer au suivant.
    appel.portail.set()
    await appel.attendre(lambda: len(appel.travaux()) == 2 and appel.travaux()[1]["remis"], delai=20)
    second = appel.travaux()[1]
    assert second["statut"] == "fait"
    assert second["resultat"] == "Créneau libre jeudi."
    assert travail.worker is not ancien
    assert travail.worker.name != ancien.name
    assert travail.service is appel.fond_llm
    textes = str(travail.worker.context.get_messages())
    assert DEMANDE not in textes, "le contexte du worker neuf ne garde rien du travail abandonné"
    assert not appel.engine.is_call_disposed()


@pytest.mark.asyncio
async def test_un_agent_retire_garde_ses_sessions_mcp_jusqu_a_la_fin_du_travail(appel):
    appel.portail = asyncio.Event()
    with patch(
        "api.services.workflow.pipecat_engine_custom_tools.db_client.get_tools_by_uuids",
        new_callable=AsyncMock,
        return_value=[TransferAgentTool(message=None)],
    ):
        await appel.monter(
            source_etapes=[
                _appel_d_outil(NOM_OUTIL, {"demande": DEMANDE}, "call_confier"),
                _appel_d_outil("transfer_to_billing", {}, "call_transfer"),
            ],
            fond_etapes=[
                _appel_d_outil("chercher_creneau", {"jour": "demain"}, "call_fond"),
                _texte(RESULTAT),
            ],
            tool_uuids=[TRANSFER_TOOL_UUID],
            destination_etapes=[_texte("Je vous écoute."), _texte("Je lis le résultat.")],
        )
        source = appel.engine.active_agent
        fermees = asyncio.Event()

        async def fermer_les_sessions():
            fermees.set()

        source.close_mcp_sessions = fermer_les_sessions
        await appel.ouvrir()
        await appel.attendre(lambda: appel.engine.active_agent is not source)
        await appel.attendre(lambda: source._close_task is not None and source._close_task.done())
        assert source.travail.occupe
        assert not fermees.is_set(), "les outils du travail en cours restent ouverts"

        appel.portail.set()
        await appel.attendre(lambda: appel.travaux()[0]["remis"])
        await appel.attendre(fermees.is_set)
        assert appel.travaux()[0]["statut"] == "fait"



# 18/10 (runs 1460 et 1461) : le résultat ne réveille jamais le modèle par-dessus une question.
def test_une_question_de_l_agent_sans_reponse_retient_le_resultat():
    from api.services.travail.retour import question_en_suspens

    assert question_en_suspens(
        [{"role": "user", "content": "Jeudi."},
         {"role": "assistant", "content": "Je regarde les disponibilités. Avez-vous une adresse mail ?"}]
    )


def test_une_reponse_de_l_appelant_ou_une_phrase_sans_question_laisse_partir_le_resultat():
    from api.services.travail.retour import question_en_suspens

    assert not question_en_suspens(
        [{"role": "assistant", "content": "Avez-vous une adresse mail ?"},
         {"role": "user", "content": "evan@gmail.com"}]
    )
    assert not question_en_suspens([{"role": "assistant", "content": "Je regarde les disponibilités."}])
    assert not question_en_suspens([])


def test_un_message_du_code_n_est_pas_une_reponse_de_l_appelant():
    from api.services.groupe.passations import PREFIXE_RESULTAT_DU_TRAVAIL
    from api.services.travail.retour import question_en_suspens

    assert question_en_suspens(
        [{"role": "assistant", "content": "Avez-vous une adresse mail ?"},
         {"role": "assistant", "content": None, "tool_calls": [{"id": "1"}]},
         {"role": "user", "content": f"{PREFIXE_RESULTAT_DU_TRAVAIL} posé]"}]
    )
