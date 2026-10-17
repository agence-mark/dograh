"""[.mark] Lot 3 d'orchestrateur-trois-cerveaux (D7) : UNE voix pour tout l'appel.

Avant ce lot, chaque agent portait sa voix : une voix neuve était ouverte à chaque passation, dans le
sous-circuit de l'agent appelé, et la connexion de cette voix faisait partie du temps de la passation.
Maintenant le pipeline d'appel porte la voix, après le pont (``build_pipeline(voice=...)``) ; les agents
ne portent que leur cerveau, leur texte revient par le bus et c'est la voix de l'appel qui le dit.

Ces tests passent par la VRAIE route (le banc de passation de l'amont : moteur, coordinateur, pont, bus,
workers d'agent) ; seuls les modèles et la voix sont des stand-ins. Le banc de l'amont monte l'appel sans
voix : ``banc_voix.voix_de_l_appel`` lui donne celle que ``run_pipeline`` monte en production.

| Test | La garantie |
|---|---|
| scénarios de l'amont | les scénarios de passation de l'amont, rejoués AVEC la voix de l'appel, passent (ils sont déclarés dans ``divergences_amont.py`` sans elle) |
| un agent appelé parle | l'annonce de la source ET l'accueil de l'agent appelé sont dits par la voix de l'appel ; aucune voix d'agent n'est utilisée |
| parole dictée pendant l'attente | pendant l'attente (personne n'a la main), une phrase dictée est ENTENDUE, sans réveiller la source |
| course : texte en vol | le texte d'un agent écarté, encore en vol sur le bus, n'est jamais dit |
| course : interruption | une parole locale encore en file est effacée par l'interruption : rien n'est dit après |
| montage | la voix est le premier processeur après le pont, avant la sortie ; sans voix, la liste est celle d'avant |
| run_pipeline | le chemin téléphonique monte la voix de l'appel et la route locale (lu au source) |
| horodatage | « passation demandée → premier octet de voix » est écrit dans la trace de la passation |
"""

import asyncio
import inspect
from unittest.mock import AsyncMock, patch

import pytest
from pipecat.frames.frames import (
    InterruptionFrame,
    LLMFullResponseEndFrame,
    LLMFullResponseStartFrame,
    LLMTextFrame,
    TTSSpeakFrame,
)
from pipecat.processors.frame_processor import FrameProcessor
from pipecat.tests import MockLLMService

import api.tests.test_agent_transfer as amont
from api.services.groupe.mesure_passation import (
    CLE_APRES_COMMIT,
    CLE_PREMIER_OCTET,
    MesureDePassation,
    ObservateurPremierOctet,
)
from api.services.pipecat.pipeline_builder import build_pipeline
from api.tests.mark.banc_voix import brancher_la_parole_locale, voix_de_l_appel
from api.tests.test_agent_transfer import (
    TransferAgentTool,
    TransferHarness,
    build_agent_workflow,
    run_transfer,
)

ANNONCE = "Let me put you through to billing."
ACCUEIL = "Billing here, how can I help?"


async def _banc(*, avec_la_route_locale: bool = True, destination_greeting: str | None = ACCUEIL):
    """Le banc de passation de l'amont avec la voix de l'appel ; ``banc`` rend la voix et le pont."""
    harness = TransferHarness()
    with voix_de_l_appel() as banc:
        await harness.build(
            source_llm=MockLLMService(
                mock_steps=[
                    MockLLMService.create_function_call_chunks(
                        "transfer_to_billing", {}, tool_call_id="call_transfer_1"
                    )
                ],
                chunk_delay=0.001,
            ),
            destination_llm=MockLLMService(
                mock_steps=[MockLLMService.create_text_chunks("Anything else?")],
                chunk_delay=0.001,
            ),
            source_workflow=build_agent_workflow(
                name="Reception", greeting=None, tool_uuids=[amont.TRANSFER_TOOL_UUID]
            ),
            destination_workflow=build_agent_workflow(
                name="Billing", greeting=destination_greeting
            ),
        )
    if avec_la_route_locale:
        brancher_la_parole_locale(harness, banc)
    harness.banc_voix = banc
    return harness, banc


# --------------------------------------------------------------------------- #
# Les scénarios de passation de l'amont, avec la voix de l'appel
# --------------------------------------------------------------------------- #


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "scenario, arguments",
    [
        ("test_transfer_hands_the_call_over_without_dropping_it", ()),
        ("test_idle_monitor_resumes_after_transfer_opening_or_recovery", (True,)),
        ("test_arrivee_sur_un_transfert_ouvert_la_phrase_est_dite_puis_le_transfert_part", ()),
    ],
)
async def test_les_scenarios_de_passation_de_l_amont_passent_avec_la_voix_de_l_appel(
    scenario, arguments
):
    """Ces trois scénarios échouent sur le banc de l'amont (aucune voix dans l'appel) : ils sont
    déclarés dans ``divergences_amont.py`` (xfail strict). Ici ils passent, sur le même scénario, dès
    que l'appel porte sa voix : la divergence est bien celle-là, et rien d'autre ne s'est cassé."""
    with voix_de_l_appel() as banc:
        # Le scénario construit son propre banc : on lui donne la route locale par le moteur.
        reel = amont.TransferHarness.build

        async def construire(self, **kwargs):
            await reel(self, **kwargs)
            brancher_la_parole_locale(self, banc)

        with patch.object(amont.TransferHarness, "build", construire):
            await getattr(amont, scenario)(*arguments)


# --------------------------------------------------------------------------- #
# Un agent appelé parle avec la voix de l'appel
# --------------------------------------------------------------------------- #


@pytest.mark.asyncio
async def test_l_annonce_de_la_source_et_l_accueil_de_l_agent_appele_sont_dits_par_la_voix_de_l_appel():
    harness, banc = await _banc()
    await harness.start()
    try:
        await run_transfer(harness, tool=TransferAgentTool())
        engine = harness.engine
        assert engine.transfer_coordinator.completed[-1]["outcome"] == "completed"
        assert engine.active_agent.workflow_id == amont.DESTINATION_WORKFLOW_ID

        # UNE voix a tout dit, dans l'ordre : l'annonce de la source puis l'accueil de l'agent appelé.
        dit = banc.voix.received_texts
        assert ANNONCE in dit and ACCUEIL in dit, dit
        assert dit.index(ANNONCE) < dit.index(ACCUEIL)

        # Les voix « d'agent » du banc de l'amont (source et destination) n'ont rien dit : elles ne
        # sont plus dans aucun circuit.
        assert harness.destination_tts is not None
        assert harness.destination_tts.received_texts == []
        assert engine.active_agent.tts is harness.destination_tts  # posée par le banc, jamais montée
        assert harness.banc_voix.voix is not harness.destination_tts
    finally:
        await harness.stop()


@pytest.mark.asyncio
async def test_la_voix_de_l_appel_est_le_premier_processeur_apres_le_pont_et_juste_avant_la_sortie():
    harness, banc = await _banc()
    try:
        processeurs = list(banc.pipeline.processors)
        i = processeurs.index(banc.pont)
        assert processeurs[i + 1] is banc.voix, "la voix doit suivre le pont immédiatement"
        # Entre la voix et la sortie : rien (la voix est juste avant le transport de sortie).
        sortie = harness.transport.output()
        assert processeurs[i + 2] is sortie
    finally:
        await harness.stop()


# --------------------------------------------------------------------------- #
# La parole dictée pendant l'attente
# --------------------------------------------------------------------------- #


@pytest.mark.asyncio
async def test_une_phrase_dictee_pendant_l_attente_est_entendue_sans_reveiller_la_source():
    """Pendant l'attente d'une passation personne n'a la main (``selected_visit_id`` vaut None) : le pont
    jette tout ce qui vient d'un agent. La phrase dictée prend donc la route locale du pont, vers la voix
    de l'appel. Contrôle : sans la route locale, rien n'arrive à l'appelant."""
    harness, banc = await _banc()
    await harness.start()
    try:
        engine = harness.engine
        source = engine.active_agent
        await engine.deactivate_agent(source)
        async with asyncio.timeout(5):
            while source.worker.active:  # la désactivation passe par le bus
                await asyncio.sleep(0.02)
        assert engine.selected_visit_id is None

        speech = await engine.queue_speech(
            "Un instant, je regarde.", append_to_context=False, persist_to_logs=True
        )
        assert await asyncio.wait_for(speech.wait(), 10), "la phrase n'a pas été jouée"
        assert "Un instant, je regarde." in banc.voix.received_texts
        # La source n'a pas été sollicitée (ni réactivée) pour la dire.
        assert [t for qui, t in harness.speech.lines if t == "Un instant, je regarde."] == []
        assert not source.worker.active

        # Contrôle : la route d'avant (via l'agent désactivé) n'amène rien à l'appelant.
        engine.set_parole_locale(None)
        perdue = await engine.queue_speech("Phrase perdue.", persist_to_logs=True, timeout=1.5)
        assert not await perdue.wait()
        assert "Phrase perdue." not in banc.voix.received_texts
    finally:
        await harness.stop()


# --------------------------------------------------------------------------- #
# Les courses
# --------------------------------------------------------------------------- #


@pytest.mark.asyncio
async def test_course_le_texte_d_un_agent_ecarte_encore_en_vol_n_est_jamais_dit():
    """Un agent qui n'a plus la main (passation en cours) pousse encore du texte sur le bus : le pont le
    jette, la voix de l'appel n'en dit rien. Contrôle : le même texte, tant que l'agent a la main, est dit."""
    harness, banc = await _banc()
    await harness.start()
    try:
        engine = harness.engine
        source = engine.active_agent

        async def texte_de(agent, phrase):
            await agent.worker.queue_frame(LLMFullResponseStartFrame())
            await agent.worker.queue_frame(LLMTextFrame(phrase))
            await agent.worker.queue_frame(LLMFullResponseEndFrame())
            await asyncio.sleep(0.4)
            await engine.drain_call_pipeline()

        await texte_de(source, "Texte tenu.")
        assert any("Texte tenu." in t for t in banc.voix.received_texts), (
            "le contrôle échoue : le texte d'un agent qui a la main n'arrive pas à la voix"
        )

        await engine.deactivate_agent(source)  # la passation commence : personne n'a la main
        await texte_de(source, "Texte en vol.")
        assert not any("Texte en vol." in t for t in banc.voix.received_texts)
    finally:
        await harness.stop()


@pytest.mark.asyncio
async def test_course_une_interruption_efface_la_parole_locale_encore_en_file():
    harness, banc = await _banc()
    await harness.start()
    try:
        engine = harness.engine
        await engine.deactivate_agent(engine.active_agent)
        pont = banc.pont

        # Contrôle : une parole locale posée sans interruption est dite.
        await pont.dire_en_local(TTSSpeakFrame("Dite.", append_to_context=False))
        await asyncio.sleep(0.4)
        await engine.drain_call_pipeline()
        assert "Dite." in banc.voix.received_texts

        # Le pont est occupé (sa file ne se vide pas) : la parole attend, puis l'appelant coupe la parole.
        await pont.pause_processing_frames()
        await pont.dire_en_local(TTSSpeakFrame("Jamais dite.", append_to_context=False))
        await harness.call_worker.queue_frame(InterruptionFrame())
        await asyncio.sleep(0.3)
        await pont.resume_processing_frames()
        await asyncio.sleep(0.4)
        await engine.drain_call_pipeline()
        assert "Jamais dite." not in banc.voix.received_texts
        assert pont._paroles_locales == set(), "l'identifiant d'une parole effacée est resté"
    finally:
        await harness.stop()


# --------------------------------------------------------------------------- #
# Le montage
# --------------------------------------------------------------------------- #


def _composants_d_appel():
    return {
        "transport": type("T", (), {"input": lambda s: FrameProcessor(), "output": lambda s: FrameProcessor()})(),
        "stt": FrameProcessor(),
        "audio_buffer": FrameProcessor(),
        "user_context_aggregator": FrameProcessor(),
        "assistant_context_aggregator": FrameProcessor(),
        "call_monitor_processor": FrameProcessor(),
        "generation_stage": [FrameProcessor()],
        "pipeline_metrics_aggregator": FrameProcessor(),
        "termination_funnel": FrameProcessor(),
    }


def test_la_voix_se_place_apres_la_generation_et_avant_la_sortie():
    composants = _composants_d_appel()
    voix = FrameProcessor()
    processeurs = list(build_pipeline(**composants, voice=voix).processors)
    pont = composants["generation_stage"][0]
    assert processeurs[processeurs.index(pont) + 1] is voix


def test_sans_voix_la_liste_du_pipeline_d_appel_est_celle_d_avant():
    """Un appel temps réel (pas de voix séparée) et les pipelines de l'amont : ``voice=None`` ne change rien."""
    sans = build_pipeline(**_composants_d_appel()).processors
    avec_none = build_pipeline(**_composants_d_appel(), voice=None).processors
    assert [type(p) for p in sans] == [type(p) for p in avec_none]
    assert len(sans) == len(avec_none)


def test_le_circuit_de_l_agent_ne_porte_plus_de_voix():
    from api.services.pipecat.pipeline_builder import build_agent_generation_pipeline

    parametres = inspect.signature(build_agent_generation_pipeline).parameters
    assert "tts" not in parametres, "le circuit d'un agent ne porte plus de voix (D7)"


def test_le_chemin_telephonique_monte_la_voix_unique_et_la_route_locale():
    """``run_pipeline`` ne se monte pas en test (patron de ``test_post_scriptum``) : le branchement est lu
    au source, le reste est joué plus haut."""
    from api.services.pipecat import run_pipeline

    source = inspect.getsource(run_pipeline)
    assert "voice=tts," in source
    assert "engine.set_parole_locale(pont_des_agents.dire_en_local)" in source
    assert "agent.tts = tts" not in source, "la voix de l'appel ne doit plus être celle d'un agent"
    assert "voix_de_l_appel=user_config.tts" in source
    assert "ObservateurPremierOctet(engine, tts)" in source


# --------------------------------------------------------------------------- #
# L'horodatage « passation demandée, premier octet de voix »
# --------------------------------------------------------------------------- #


class _Horloge:
    def __init__(self):
        self.t = 100.0

    def __call__(self):
        return self.t


def test_la_mesure_prend_la_demande_le_commit_puis_le_premier_octet_une_seule_fois():
    h = _Horloge()
    mesure = MesureDePassation(h)
    assert mesure.premier_octet() is None  # rien demandé
    mesure.demandee("xfer-1")
    h.t = 101.0
    assert mesure.premier_octet() is None, "pas de mesure avant le commit"
    mesure.commise()
    h.t = 102.5
    resultat = mesure.premier_octet()
    assert resultat == {CLE_PREMIER_OCTET: 2.5, CLE_APRES_COMMIT: 1.5}
    h.t = 110.0
    assert mesure.premier_octet() is None, "une seule fois par passation"
    # Une passation non commise n'a pas de mesure.
    mesure.demandee("xfer-2")
    assert mesure.premier_octet() is None
    assert mesure.completer({"request_id": "xfer-1", "to_visit_id": "v"}) == {
        "request_id": "xfer-1",
        "to_visit_id": "v",
    }


def test_la_mesure_ne_complete_que_l_enregistrement_d_une_passation_commise():
    h = _Horloge()
    mesure = MesureDePassation(h)
    mesure.demandee("xfer-1")
    mesure.commise()
    h.t = 101.0
    mesure.premier_octet()
    echouee = mesure.completer({"request_id": "xfer-1", "to_visit_id": None})
    assert CLE_PREMIER_OCTET not in echouee
    autre = mesure.completer({"request_id": "xfer-0", "to_visit_id": "v"})
    assert CLE_PREMIER_OCTET not in autre
    commise = mesure.completer({"request_id": "xfer-1", "to_visit_id": "v"})
    assert commise[CLE_PREMIER_OCTET] == 1.0 and commise[CLE_APRES_COMMIT] == 1.0


@pytest.mark.asyncio
async def test_une_passation_ecrit_son_premier_octet_de_voix_dans_la_trace():
    """R1 : la vraie route (coordinateur, commit, voix de l'appel, observateur du worker d'appel) écrit
    ``voix_premier_octet_s`` et ``voix_apres_commit_s`` dans l'enregistrement de la passation."""
    harness, banc = await _banc()
    harness.call_worker.add_observer(ObservateurPremierOctet(harness.engine, banc.voix))
    await harness.start()
    try:
        await run_transfer(harness, tool=TransferAgentTool())
        engine = harness.engine
        async with asyncio.timeout(10):
            while CLE_PREMIER_OCTET not in engine.transfer_coordinator.completed[-1]:
                await asyncio.sleep(0.05)
        enregistrement = engine.transfer_coordinator.completed[-1]
        assert enregistrement["outcome"] == "completed"
        assert 0 < enregistrement[CLE_PREMIER_OCTET] < 30
        assert 0 <= enregistrement[CLE_APRES_COMMIT] <= enregistrement[CLE_PREMIER_OCTET]
        # La trace du run (``agent_transfers``) porte les mêmes objets.
        assert CLE_PREMIER_OCTET in engine._gathered_context["agent_transfers"][-1]
    finally:
        await harness.stop()


@pytest.mark.asyncio
async def test_une_passation_qui_echoue_n_a_pas_de_mesure_de_voix():
    harness = TransferHarness()
    with voix_de_l_appel() as banc:
        from api.services.pipecat.agent_runtime_factory import AgentBuildError

        await harness.build(
            source_llm=MockLLMService(
                mock_steps=[
                    MockLLMService.create_function_call_chunks(
                        "transfer_to_billing", {}, tool_call_id="call_transfer_1"
                    ),
                    MockLLMService.create_text_chunks("Désolé."),
                ],
                chunk_delay=0.001,
            ),
            destination_llm=MockLLMService(mock_steps=[], chunk_delay=0.001),
            source_workflow=build_agent_workflow(
                name="Reception", greeting=None, tool_uuids=[amont.TRANSFER_TOOL_UUID]
            ),
            destination_workflow=build_agent_workflow(name="Billing", greeting="Billing."),
            destination_build_error=AgentBuildError("destination_not_published", "absent"),
        )
    brancher_la_parole_locale(harness, banc)
    harness.call_worker.add_observer(ObservateurPremierOctet(harness.engine, banc.voix))
    await harness.start()
    try:
        await run_transfer(harness, tool=TransferAgentTool())
        await asyncio.sleep(0.5)
        enregistrement = harness.engine.transfer_coordinator.completed[-1]
        assert enregistrement["outcome"] == "destination_not_published"
        assert CLE_PREMIER_OCTET not in enregistrement
    finally:
        await harness.stop()


@pytest.mark.asyncio
async def test_l_observateur_ne_leve_jamais():
    class _Moteur:
        mesure_passation = None

    from types import SimpleNamespace

    from pipecat.frames.frames import TTSAudioRawFrame

    voix = object()
    observateur = ObservateurPremierOctet(_Moteur(), voix)
    donnees = SimpleNamespace(
        source=voix, frame=TTSAudioRawFrame(b"\0" * 64, 16000, 1), direction=None
    )
    await observateur.on_push_frame(donnees)  # moteur sans mesure : rien, pas d'erreur
    sans_moteur = ObservateurPremierOctet(None, voix)
    await sans_moteur.on_push_frame(donnees)
