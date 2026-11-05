"""[.mark] Builder partie 3, lot P (P2, A2) : la passation recouverte, sur le VRAI moteur et le VRAI coordinateur.

Le pipeline fendu du banc de l'amont (``TransferHarness``) avec la voix de l'appel (``banc_voix``) ; seuls les modèles,
la voix et la base sont remplacés. Le collègue attend dans la réserve de l'appel, construit au décroché.

| Groupe | Ce qu'il prouve |
|---|---|
| ordre (R1) | la requête du collègue part pendant l'annonce ; la voix dit l'annonce, PUIS le collègue, jamais l'inverse, l'annonce une seule fois ; aucune musique |
| échec | un collègue qui ne s'active pas : aucune parole du collègue, l'annonce finie avant que l'accueil reprenne la main |
| annulation | un appel raccroché pendant l'annonce : le collègue n'est jamais activé, aucune requête n'est partie |
| A2 | les sessions MCP du collègue s'ouvrent à la mise en réserve, jamais à la passation ; le contexte reste le même objet, l'historique est gardé ; fermées en fin d'appel |
| consigne | le collègue reçoit « l'accueil a quitté l'appel… » dans sa note d'aller |
"""

import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest
from pipecat.tests import MockLLMService, MockTTSService

from api.services.groupe.notes import note_d_aller
from api.services.groupe.prechauffage import Precharge
from api.services.workflow.agent_transfer import TransferRequest
from api.tests.mark.banc_voix import brancher_la_parole_locale, voix_de_l_appel
from api.tests.mark.test_passation_rapide_groupe import GROUPE, PATCH_OUTILS, _sonnerie
from api.tests.test_agent_transfer import (
    DESTINATION_WORKFLOW_ID,
    TransferAgentTool,
    TransferHarness,
    build_agent_workflow,
)

ANNONCE = "Je vous passe ma collègue des rendez-vous."
REPONSE = "Bonjour, je prends votre rendez-vous."


async def _monter(*, annonce_ms: int = 1500):
    """Un appel de groupe : l'accueil a la main, le collègue « 99 » attend construit dans la réserve."""
    harness = TransferHarness()
    with voix_de_l_appel() as banc:
        await harness.build(
            source_llm=MockLLMService(mock_steps=[], chunk_delay=0.001),
            destination_llm=MockLLMService(
                mock_steps=[MockLLMService.create_text_chunks(REPONSE)],
                chunk_delay=0.001,
            ),
            source_workflow=build_agent_workflow(
                name="Accueil", greeting=None, tool_uuids=["tool-transfer-agent"]
            ),
            destination_workflow=build_agent_workflow(name="Specialise", greeting=None),
        )
    brancher_la_parole_locale(harness, banc)
    engine = harness.engine
    engine.reglages_appel = dict(GROUPE)
    engine.active_agent.reglages = dict(GROUPE)
    engine._get_organization_id = AsyncMock(return_value=1)
    await harness.start()
    # L'annonce dure : la voix de l'appel met ``annonce_ms`` à dire chaque phrase.
    banc.voix._mock_audio_data = MockTTSService.create_mock_audio(annonce_ms)
    factory = engine._agent_factory
    factory.precharge = Precharge(organization_id=1)
    construire = factory.build

    async def construire_le_collegue(*, workflow_id, visit_id):
        runtime = await construire(workflow_id=workflow_id, visit_id=visit_id)
        runtime.reglages = {"agent_principal_id": 1}
        return runtime

    factory.build = construire_le_collegue
    return harness, banc


async def _mettre_en_reserve(harness):
    """La réserve du décroché (``_mettre_en_reserve``), puis une refabrication en fond sans circuit : le banc
    réutilise le même modèle factice, et un processeur n'a qu'une place."""
    engine = harness.engine
    await engine._mettre_en_reserve(DESTINATION_WORKFLOW_ID)
    collegue = engine._agent_factory.precharge.prets[DESTINATION_WORKFLOW_ID]

    async def refaire(*, workflow_id, visit_id):
        return SimpleNamespace(
            preconstruit=False,
            error=None,
            is_running=True,
            travail=None,
            llm=None,
            visit_id=visit_id,
            reglages={},
            mcp_sessions={},
            workflow=SimpleNamespace(nodes={}),
            close_mcp_sessions=AsyncMock(),
        )

    engine._agent_factory.build = refaire
    return collegue


def _espions(engine):
    """Note l'ordre : l'annonce (sa parole), le départ de la requête du collègue, l'activation de l'accueil."""
    journal: list[tuple[str, bool]] = []
    paroles: list = []
    dire, ouvrir, activer = (
        engine.queue_speech,
        engine.queue_node_opening,
        engine.activate_agent,
    )

    async def dire_espion(*args, **kwargs):
        parole = await dire(*args, **kwargs)
        if kwargs.get("mute_user"):
            paroles.append(parole)
        return parole

    async def ouvrir_espion(**kwargs):
        journal.append(("requete du collegue", bool(paroles) and paroles[0].done))
        return await ouvrir(**kwargs)

    async def activer_espion(agent, **kwargs):
        if agent.workflow_id == 1:
            journal.append(
                ("l'accueil reprend la main", bool(paroles) and paroles[0].done)
            )
        return await activer(agent, **kwargs)

    engine.queue_speech = dire_espion
    engine.queue_node_opening = ouvrir_espion
    engine.activate_agent = activer_espion
    return journal, paroles


def _demander(harness):
    engine = harness.engine
    demande = TransferRequest(
        destination_workflow_id=DESTINATION_WORKFLOW_ID,
        destination_label="Passer aux rendez-vous",
        origin_visit_id=engine.active_agent.visit_id,
        announcement=ANNONCE,
    )
    coordinateur = engine.transfer_coordinator
    assert coordinateur.accept(demande)
    coordinateur.start(demande)
    return coordinateur


async def _attendre_le_texte(banc, texte, delai=10.0):
    async with asyncio.timeout(delai):
        while texte not in banc.voix.received_texts:
            await asyncio.sleep(0.02)


@pytest.mark.asyncio
async def test_r1_la_requete_du_collegue_part_pendant_l_annonce_et_il_parle_apres(
    monkeypatch,
):
    sonneries = _sonnerie(monkeypatch)
    harness, banc = await _monter()
    engine = harness.engine
    try:
        with patch(PATCH_OUTILS, AsyncMock(return_value=[TransferAgentTool()])):
            collegue = await _mettre_en_reserve(harness)
            assert engine.collegue_en_reserve(DESTINATION_WORKFLOW_ID)
            journal, paroles = _espions(engine)
            coordinateur = _demander(harness)
            await asyncio.wait_for(coordinateur._task, 20)
            assert coordinateur.completed[-1]["outcome"] == "completed"
            assert engine.active_agent is collegue
            await _attendre_le_texte(banc, REPONSE)
        # La requête du collègue est partie PENDANT l'annonce (sa parole n'était pas finie).
        assert journal == [("requete du collegue", False)]
        # La voix de l'appel : l'annonce, PUIS le collègue ; l'annonce une seule fois.
        textes = banc.voix.received_texts
        assert textes.count(ANNONCE) == 1
        assert textes.index(ANNONCE) < textes.index(REPONSE)
        # Ni musique ni durée minimale vers un collègue de la réserve.
        assert sonneries == []
        assert paroles and await asyncio.wait_for(paroles[0].wait(), 10)
        enregistrement = coordinateur.completed[-1]
        assert enregistrement["installation"] == "reserve"
        # Le collègue a pris la main (et sa requête est partie) avant la fin de l'annonce.
        assert enregistrement["commit_s"] < enregistrement["annonce_finie_s"]
    finally:
        await harness.stop()


@pytest.mark.asyncio
async def test_un_collegue_qui_ne_s_active_pas_ne_dit_rien_et_l_annonce_finit_avant_l_accueil(
    monkeypatch,
):
    _sonnerie(monkeypatch)
    harness, banc = await _monter()
    engine = harness.engine
    try:
        with patch(PATCH_OUTILS, AsyncMock(return_value=[TransferAgentTool()])):
            await _mettre_en_reserve(harness)
            journal, _paroles = _espions(engine)
            activer = engine.activate_agent

            async def refuser_le_collegue(agent, **kwargs):
                if agent.workflow_id == DESTINATION_WORKFLOW_ID:
                    return False
                return await activer(agent, **kwargs)

            engine.activate_agent = refuser_le_collegue
            coordinateur = _demander(harness)
            await asyncio.wait_for(coordinateur._task, 30)
            assert coordinateur.completed[-1]["outcome"] == "activation_failed"
            await asyncio.sleep(0.3)
        assert engine.active_agent.workflow_id == 1
        # Aucune requête du collègue, aucune parole du collègue ; l'accueil reprend après la fin de l'annonce.
        assert journal == [("l'accueil reprend la main", True)]
        assert REPONSE not in banc.voix.received_texts
    finally:
        await harness.stop()


@pytest.mark.asyncio
async def test_un_appel_raccroche_pendant_l_annonce_n_active_jamais_le_collegue(
    monkeypatch,
):
    _sonnerie(monkeypatch)
    harness, banc = await _monter(annonce_ms=3000)
    engine = harness.engine
    try:
        with patch(PATCH_OUTILS, AsyncMock(return_value=[TransferAgentTool()])):
            collegue = await _mettre_en_reserve(harness)
            journal, _paroles = _espions(engine)
            preparer = engine.prepare_agent

            async def preparer_lentement(agent):
                await asyncio.sleep(1.0)
                await preparer(agent)

            engine.prepare_agent = preparer_lentement
            coordinateur = _demander(harness)
            await asyncio.sleep(0.3)
            await coordinateur.invalidate("caller_hung_up")
        assert ("requete du collegue", False) not in journal
        assert engine.active_agent is not collegue
        assert not collegue.worker.active
        await asyncio.sleep(0.3)
        assert REPONSE not in banc.voix.received_texts
    finally:
        await harness.stop()


@pytest.mark.asyncio
async def test_a2_les_sessions_mcp_s_ouvrent_a_la_mise_en_reserve_et_le_contexte_reste_le_meme(
    monkeypatch,
):
    _sonnerie(monkeypatch)
    harness, _banc = await _monter(annonce_ms=200)
    engine = harness.engine
    fermee = AsyncMock()
    ouvertures: list[str] = []

    async def ouvrir(agent=None):
        agent = agent or engine.active_agent
        ouvertures.append(agent.visit_id)
        agent.mcp_sessions["outil-mcp"] = SimpleNamespace(close_managed=fermee)

    engine._open_mcp_sessions = ouvrir
    contexte = engine.context
    engine.context.set_messages(
        [
            {"role": "user", "content": "Je voudrais un rendez-vous."},
            {"role": "assistant", "content": "Bien sûr."},
        ]
    )
    try:
        with patch(PATCH_OUTILS, AsyncMock(return_value=[TransferAgentTool()])):
            collegue = await _mettre_en_reserve(harness)
            assert ouvertures == [collegue.visit_id], (
                "sessions non ouvertes à la mise en réserve"
            )
            construites = list(harness.built_destinations)
            coordinateur = _demander(harness)
            await asyncio.wait_for(coordinateur._task, 20)
            assert coordinateur.completed[-1]["outcome"] == "completed"
        # Rien de rouvert, rien de reconstruit à la passation ; même contexte, historique gardé. (La réserve se
        # refait en fond pour la passation suivante : ce nouveau collègue ouvre les siennes, au décroché de lui.)
        assert ouvertures.count(collegue.visit_id) == 1
        assert harness.built_destinations == construites
        assert engine.context is contexte
        contenus = [m.get("content") for m in engine.context.get_messages()]
        assert "Je voudrais un rendez-vous." in contenus
    finally:
        await harness.stop()


@pytest.mark.asyncio
async def test_a2_les_sessions_d_un_collegue_reste_en_reserve_se_ferment_en_fin_d_appel():
    harness, _banc = await _monter(annonce_ms=200)
    engine = harness.engine
    fermee = AsyncMock()

    async def ouvrir(agent=None):
        agent.mcp_sessions["outil-mcp"] = SimpleNamespace(close_managed=fermee)

    engine._open_mcp_sessions = ouvrir
    try:
        await engine._mettre_en_reserve(DESTINATION_WORKFLOW_ID)
        collegue = engine._agent_factory.precharge.prets[DESTINATION_WORKFLOW_ID]
        assert collegue.mcp_sessions
        await engine.close_mcp_sessions()
        assert collegue.mcp_sessions == {}
        fermee.assert_awaited()
    finally:
        await harness.stop()


def test_la_note_d_aller_dit_au_collegue_que_l_accueil_a_quitte_l_appel():
    note = note_d_aller(None, {}, outil="Passer aux rendez-vous")
    assert (
        "L'accueil a quitté l'appel : tu ne parles pas comme lui et tu ne finis pas ses phrases."
        in note
    )
