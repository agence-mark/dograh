"""[.mark] Lot 4 d'orchestrateur-trois-cerveaux (D8) : le cerveau de fond au clavier, et ses traces.

Au clavier il n'y a ni circuit d'appel ni worker d'appel : chaque tour monte un moteur neuf. Le
travail de fond y suit la même route qu'au téléphone (même worker, même job, mêmes outils, mêmes
jetons) sur un mini-bus du tour ; il se termine DANS le tour, et son résultat est remis AU TOUR
SUIVANT, avant la réplique tapée, sous la même forme ``[Résultat du travail : …]``.

| Test | La garantie |
|---|---|
| tour puis tour suivant | confier au tour 1 : « lancé », le travail finit dans le tour, le résultat est injecté au tour 2 et pas deux fois |
| point de reprise | la trace voyage dans le point de reprise du clavier (JSON) : le tour suivant la retrouve |
| éteint | un agent sans réglage n'a ni outil ni worker au clavier non plus |
| câblage du clavier | le tour du clavier prépare le fond, l'attend avant de démonter, et injecte au tour suivant |
| envoi | ``travaux`` entre dans l'envoi du portail seulement quand il y en a (additif) |
| lecteurs | le résultat n'est lu ni par la lecture des nombres/communes ni par le lexique |
"""

import inspect
import json
from datetime import UTC, datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi.encoders import jsonable_encoder
from openai.types.completion_usage import CompletionUsage
from pipecat.processors.aggregators.llm_context import LLMContext
from pipecat.tests import MockLLMService

from api.services.apres_appel.envoi import travaux_de
from api.services.groupe.passations import (
    PREFIXE_RESULTAT_DU_TRAVAIL,
    est_un_resultat_de_travail,
)
from api.services.pipecat.pipeline_metrics_aggregator import PipelineMetricsAggregator
from api.services.travail.clavier import (
    remettre_les_travaux_termines,
    travaux_a_remettre,
)
from api.services.travail.reglages import NOM_OUTIL, ReglagesTravail
from api.services.workflow.pipecat_engine import PipecatEngine
from api.services.workflow.pipecat_engine_custom_tools import CustomToolManager
from api.tests.test_agent_transfer import build_agent_workflow

DEMANDE = "Cherche un créneau libre demain."
RESULTAT = "Créneau libre demain à 14 h."


def _texte(texte, jetons=None):
    morceaux = MockLLMService.create_text_chunks(texte)
    if jetons:
        morceaux[-1].usage = CompletionUsage(
            prompt_tokens=jetons[0], completion_tokens=jetons[1], total_tokens=sum(jetons)
        )
    return morceaux


async def _moteur_clavier(*, reglages, fond_etapes=None, collecteur=None, etape_cochee=True):
    """Un moteur comme celui d'un tour du clavier : sans sortie audio, sans circuit d'appel."""
    graphe = build_agent_workflow(name="Accueil", greeting=None)
    # modules-et-cerveaux (lot 5, M3) : l'étape de départ porte « Travail en arrière-plan ».
    graphe.nodes["start"].travail_de_fond = etape_cochee
    moteur = PipecatEngine(
        llm=MockLLMService(mock_steps=[], chunk_delay=0),
        context=LLMContext(),
        workflow=graphe,
        call_context_vars={},
        workflow_run_id=1,
    )
    moteur.sans_sortie_audio = True
    moteur._get_organization_id = AsyncMock(return_value=1)
    moteur._custom_tool_manager = CustomToolManager(moteur)
    moteur.collecteur_de_cout = collecteur
    agent = moteur.active_agent
    agent.reglages = reglages
    fond = MockLLMService(mock_steps=fond_etapes or [_texte(RESULTAT)], chunk_delay=0)

    async def fausse_preparation(run_configs, user_config, organisation, runtime, **_):
        return ReglagesTravail.depuis(run_configs), fond

    with patch(
        "api.services.travail.agent.preparer_le_service_du_travail", fausse_preparation
    ):
        await moteur.preparer_le_travail(agent, user_config=SimpleNamespace(), attacher=False)
    return moteur, agent


@pytest.mark.asyncio
async def test_le_travail_finit_dans_le_tour_et_son_resultat_est_remis_au_tour_suivant():
    collecteur = PipelineMetricsAggregator()
    moteur, agent = await _moteur_clavier(
        reglages={"travail_actif": True},
        fond_etapes=[_texte(RESULTAT, jetons=(150, 25))],
        collecteur=collecteur,
    )
    try:
        # Le fond est monté, l'outil est dans la requête de l'agent.
        assert agent.travail is not None
        await moteur.set_node("start")
        assert NOM_OUTIL in [f.name for f in agent.tools.standard_tools]

        # Tour 1 : le modèle de conversation confie. L'outil rend « lancé » tout de suite.
        assert await agent.travail.confier(DEMANDE) == {"statut": "lancé"}
        assert agent.travail.occupe is True
        # Le clavier attend la fin du travail avant de démonter le tour.
        await agent.travail.attendre()
        assert agent.travail.occupe is False
        trace = moteur._gathered_context["travaux"][0]
        assert trace["statut"] == "fait"
        assert trace["resultat"] == RESULTAT
        assert trace["remis"] is False  # pas poussé : le tour suivant le lira
        assert (trace["jetons_entree"], trace["jetons_sortie"]) == (150, 25)
        usage = collecteur.get_llm_usage_metrics()
        assert [k for k in usage if k.startswith("travail|||")]

        # Tour 2 : avant la réplique tapée, le résultat entre dans la conversation.
        contexte = LLMContext()
        contexte.add_message({"role": "user", "content": "Bonjour"})
        assert remettre_les_travaux_termines(moteur._gathered_context, contexte) == 1
        messages = contexte.get_messages()
        assert messages[-1] == {
            "role": "user",
            "content": f"{PREFIXE_RESULTAT_DU_TRAVAIL} {RESULTAT}]",
        }
        assert est_un_resultat_de_travail(messages[-1])
        assert trace["remis"] is True
        # Une seule fois : le tour d'après n'injecte plus rien.
        assert remettre_les_travaux_termines(moteur._gathered_context, contexte) == 0
        assert len(contexte.get_messages()) == 2
    finally:
        await moteur.cleanup()


@pytest.mark.asyncio
async def test_la_trace_voyage_dans_le_point_de_reprise_du_clavier():
    """Le point de reprise est du JSON : la trace d'un travail fini y entre et en ressort intacte,
    et le tour suivant la remet."""
    moteur, agent = await _moteur_clavier(reglages={"travail_actif": True})
    try:
        await agent.travail.confier(DEMANDE)
        await agent.travail.attendre()
        enregistre = json.loads(json.dumps(jsonable_encoder(moteur._gathered_context)))
    finally:
        await moteur.cleanup()
    assert travaux_a_remettre(enregistre)[0]["demande"] == DEMANDE
    contexte = LLMContext()
    assert remettre_les_travaux_termines(enregistre, contexte) == 1
    assert contexte.get_messages()[0]["content"].startswith(PREFIXE_RESULTAT_DU_TRAVAIL)


@pytest.mark.asyncio
async def test_un_travail_encore_en_cours_ou_deja_remis_n_est_pas_remis():
    fiche = {
        "travaux": [
            {"statut": "en_cours", "message": "x", "remis": False},
            {"statut": "fait", "message": "[Résultat du travail : a]", "remis": True},
            {"statut": "echec", "message": "[Résultat du travail : b]", "remis": False},
            {"statut": "fait", "remis": False},  # pas de message : rien à remettre
        ]
    }
    assert [t["message"] for t in travaux_a_remettre(fiche)] == ["[Résultat du travail : b]"]
    contexte = LLMContext()
    assert remettre_les_travaux_termines(fiche, contexte) == 1
    assert remettre_les_travaux_termines(None, contexte) == 0
    assert remettre_les_travaux_termines({}, contexte) == 0


@pytest.mark.asyncio
async def test_un_agent_sans_reglage_n_a_ni_outil_ni_worker_au_clavier():
    moteur, agent = await _moteur_clavier(reglages={})
    try:
        assert agent.travail is None
        assert moteur.travaux == []
        await moteur.set_node("start")
        assert NOM_OUTIL not in [f.name for f in agent.tools.standard_tools]
    finally:
        await moteur.cleanup()


@pytest.mark.asyncio
async def test_au_clavier_une_etape_non_cochee_n_offre_pas_confier():
    """modules-et-cerveaux (lot 5, M3) : la même règle qu'au téléphone."""
    moteur, agent = await _moteur_clavier(reglages={"travail_actif": True}, etape_cochee=False)
    try:
        assert agent.travail is not None
        await moteur.set_node("start")
        assert NOM_OUTIL not in [f.name for f in agent.tools.standard_tools]
    finally:
        await moteur.cleanup()


@pytest.mark.asyncio
async def test_un_echec_au_clavier_se_remet_aussi_au_tour_suivant():
    moteur, agent = await _moteur_clavier(reglages={"travail_actif": True})
    try:
        async def echoue(_travail, _demande):
            raise RuntimeError("secret")

        agent.travail._executeur = echoue
        await agent.travail.confier(DEMANDE)
        await agent.travail.attendre()
        contexte = LLMContext()
        assert remettre_les_travaux_termines(moteur._gathered_context, contexte) == 1
        contenu = contexte.get_messages()[0]["content"]
        assert "n'a pas abouti" in contenu and "secret" not in contenu
    finally:
        await moteur.cleanup()


def test_le_tour_du_clavier_prepare_attend_et_remet_le_fond():
    """Le câblage du tour du clavier, lu au source (le tour entier demande la base) : le fond de
    l'agent qui parle est préparé, attendu avant le démontage du tour, et son résultat est injecté
    avant la réplique tapée. Le collecteur de coût du passage est posé sur le moteur."""
    from api.services.workflow import text_chat_runner

    source = inspect.getsource(text_chat_runner.execute_text_chat_pending_turn)
    assert "await engine.preparer_le_travail(" in source
    assert "remettre_les_travaux_termines(engine._gathered_context, context)" in source
    assert "for travail in list(engine.travaux):" in source
    assert "await travail.attendre()" in source
    assert "engine.collecteur_de_cout = pipeline_metrics_aggregator" in source
    # L'injection précède l'ajout de la réplique tapée.
    assert source.index("remettre_les_travaux_termines(") < source.index(
        'context.add_message({"role": "user", "content": message_pour_le_modele})'
    )
    # L'attente précède le démontage (le bloc finally).
    assert source.index("await travail.attendre()") < source.index("finally:\n            try:\n                if not task.has_finished()")


def test_le_circuit_telephonique_pose_le_collecteur_et_prepare_le_fond_du_premier_agent():
    from api.services.pipecat import run_pipeline

    source = inspect.getsource(run_pipeline)
    assert "engine.collecteur_de_cout = pipeline_metrics_aggregator" in source
    assert "await engine.preparer_le_travail(agent, user_config=user_config, attacher=False)" in source
    from api.services.workflow.pipecat_engine import PipecatEngine as Moteur

    demarrage = inspect.getsource(Moteur.start_initial_agent)
    assert "agent.travail.attacher()" in demarrage
    construction = inspect.getsource(Moteur.build_agent)
    assert "await self.preparer_le_travail(runtime)" in construction


# --------------------------------------------------------------------------- #
# L'envoi vers le portail
# --------------------------------------------------------------------------- #


def test_les_travaux_entrent_dans_l_envoi_seulement_quand_il_y_en_a():
    assert travaux_de({}) == []
    assert travaux_de({"travaux": []}) == []
    assert travaux_de({"travaux": [{"statut": "fait"}]}) == []  # sans demande : pas une entrée
    sortie = travaux_de(
        {
            "travaux": [
                {
                    "agent": "Planning",
                    "demande": DEMANDE,
                    "statut": "fait",
                    "outils": ["chercher_creneau"],
                    "duree_ms": 4200,
                    "jetons_entree": 150,
                    "jetons_sortie": 25,
                    "resultat": RESULTAT,
                    "message": "[Résultat du travail : x]",  # interne : jamais envoyé
                    "remis": True,
                }
            ]
        }
    )
    assert sortie == [
        {
            "agent": "Planning",
            "demande": DEMANDE,
            "statut": "fait",
            "outils": ["chercher_creneau"],
            "duree_ms": 4200,
            "jetons_entree": 150,
            "jetons_sortie": 25,
            "resultat": RESULTAT,
        }
    ]


def test_l_envoi_d_un_appel_sans_travail_n_a_pas_la_cle():
    """Un run sans travail : l'envoi est celui d'avant, sans la clé ``travaux``."""
    from api.services.apres_appel.envoi import construire_envoi
    from api.schemas.apres_appel import ApresAppelAgent

    run = SimpleNamespace(
        id=1,
        workflow_id=2,
        definition_id=3,
        definition=SimpleNamespace(workflow_configurations={}, version_number=1),
        workflow=SimpleNamespace(name="A"),
        initial_context={},
        gathered_context={},
        usage_info={},
        mode="smallwebrtc",
        call_type="inbound",
        created_at=datetime(2026, 10, 17, 10, 0, tzinfo=UTC),
    )
    sans = construire_envoi(run, {}, ApresAppelAgent())
    assert "travaux" not in sans
    run.gathered_context = {
        "travaux": [{"demande": DEMANDE, "statut": "fait", "outils": [], "resultat": RESULTAT}]
    }
    avec = construire_envoi(run, {}, ApresAppelAgent())
    assert avec["travaux"][0]["demande"] == DEMANDE
    # Tout le reste de l'envoi est identique.
    assert {k: v for k, v in avec.items() if k != "travaux"} == sans


# --------------------------------------------------------------------------- #
# Les lecteurs de la parole de l'appelant
# --------------------------------------------------------------------------- #


@pytest.mark.asyncio
async def test_le_resultat_n_est_lu_ni_par_les_nombres_ni_par_le_lexique():
    """Un résultat « rendez-vous le 12 à 14 h » n'est pas dicté par l'appelant : ni nombres, ni
    communes, ni lexique à y lire (et rien à consigner dans la fiche)."""
    from api.services.pipecat import lecture_appelant, reconnaissance_lexique

    message = {"role": "user", "content": f"{PREFIXE_RESULTAT_DU_TRAVAIL} rendez-vous le 12 à 14 h, Creil.]"}
    frame = SimpleNamespace(context=SimpleNamespace(messages=[message]), speculation=False)
    soi = SimpleNamespace(_examines=set())
    with (
        patch.object(lecture_appelant, "lire_texte", AsyncMock()) as lecture,
        patch.object(reconnaissance_lexique, "corriger_texte", AsyncMock()) as lexique,
    ):
        await lecture_appelant.LectureAppelantProcessor._lire_contexte(soi, frame)
        await reconnaissance_lexique.ReconnaissanceLexiqueProcessor._lire_contexte(soi, frame)
    lecture.assert_not_called()
    lexique.assert_not_called()
    assert soi._examines == set()
    # Une vraie parole de l'appelant, elle, est bien lue (le garde ne coupe rien d'autre).
    parole = {"role": "user", "content": "Bonjour, je suis à Creil."}
    frame = SimpleNamespace(context=SimpleNamespace(messages=[parole]), speculation=False)
    soi = MagicMock()
    soi._examines = set()
    soi._etape_courante = lambda: None
    with patch.object(
        lecture_appelant, "lire_texte", AsyncMock(return_value=parole["content"])
    ) as lecture:
        await lecture_appelant.LectureAppelantProcessor._lire_contexte(soi, frame)
    lecture.assert_awaited_once()
