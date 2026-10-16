"""[.mark] Chantier agents-specialises, lot « schéma et phrase pont » (partie B) : la phrase pont.

Plan `Labo-agent-vocal/plans/agents-specialises/2026-10-16-plan-lot-schema-et-phrase-pont.md`.
Réglage ``attente.phrase_pont`` (texte, vide = désactivée) et ``attente.delai_phrase_pont_s`` (défaut 2) :
si la passation n'est pas commise après le délai, l'agent qui passe la main dit la phrase, une seule
fois. Ces tests passent par le VRAI moteur et le VRAI coordinateur (le banc de passation fendu) ;
seuls les modèles, la voix et la base sont remplacés. La préparation de l'agent appelé est ralentie
pour que le délai puisse tomber pendant la passation.

| Test | Ce qu'il prouve |
|---|---|
| réglages | défaut 2 s ; texte vide ou absent = désactivée ; valeur illisible = défaut |
| dite après le délai | la phrase part de l'agent SOURCE, une seule fois ; le son d'attente se tait le temps de la phrase puis reprend |
| passation rapide | passation commise avant le délai : rien n'est dit, la tâche différée est annulée |
| vide | aucune phrase, même si la passation dure |
| principal chaud | retour vers le principal resté chaud (instantané) : rien n'est dit |
| clavier | aucune voix, aucune phrase |
| retour silencieux | une demande silencieuse ne dit rien |
| sans son | « son aucun » : la phrase est dite quand même |
"""

import asyncio
from unittest.mock import AsyncMock, patch

from pipecat.frames.frames import TTSAudioRawFrame

import pytest

from api.services.groupe.reglages_passation import (
    DELAI_PHRASE_PONT_DEFAUT_S,
    attente_de,
)
from api.services.workflow import agent_transfer
from api.tests.mark.test_passation_rapide_groupe import (
    GROUPE,
    PATCH_OUTILS,
    _monter_groupe,
    _passer,
    _sonnerie,
)
from api.tests.test_agent_transfer import TransferAgentTool

PHRASE = "Une seconde, je vous passe quelqu'un."


def _ralentir_la_preparation(harness, secondes: float):
    """La préparation de l'agent appelé dure ``secondes`` de plus (passation lente)."""
    engine = harness.engine
    original = engine.prepare_agent

    async def lente(runtime):
        await asyncio.sleep(secondes)
        return await original(runtime)

    engine.prepare_agent = lente


def _phrase_sans_fin(engine):
    """``queue_speech`` dont la phrase pont ne finit jamais de jouer (le reste passe normalement)."""
    queue_speech = engine.queue_speech

    async def sans_fin(*args, **kwargs):
        if args and args[0] == PHRASE:
            return engine.speech_playback.create()
        return await queue_speech(*args, **kwargs)

    return sans_fin


def _phrases(harness) -> list[tuple[str, str]]:
    return [(qui, texte) for qui, texte in harness.speech.lines if texte == PHRASE]


async def _passation(reglages, *, lenteur: float, vers: int = 99, avant=None, **options):
    harness = await _monter_groupe({**GROUPE, **reglages})
    try:
        _ralentir_la_preparation(harness, lenteur)
        if avant is not None:
            avant(harness)
        with patch(PATCH_OUTILS, AsyncMock(return_value=[TransferAgentTool()])):
            resultat = await _passer(harness, vers, **options)
        return harness, resultat
    except BaseException:
        await harness.stop()
        raise


# --------------------------------------------------------------------------- #
# Les réglages
# --------------------------------------------------------------------------- #


def test_les_reglages_de_la_phrase_pont():
    a = attente_de({})
    assert a.phrase_pont == "" and a.delai_phrase_pont_s == DELAI_PHRASE_PONT_DEFAUT_S == 2.0
    a = attente_de({"attente": {"phrase_pont": f"  {PHRASE} ", "delai_phrase_pont_s": 0.5}})
    assert a.phrase_pont == PHRASE and a.delai_phrase_pont_s == 0.5
    # Vide, absente ou illisible : désactivée ; délai illisible ou négatif : défaut ou zéro.
    for brut in ("", "   ", None, 12, ["x"]):
        assert attente_de({"attente": {"phrase_pont": brut}}).phrase_pont == ""
    for brut in ("x", True, None, float("nan"), float("inf")):
        assert attente_de({"attente": {"delai_phrase_pont_s": brut}}).delai_phrase_pont_s == 2.0
    assert attente_de({"attente": {"delai_phrase_pont_s": -3}}).delai_phrase_pont_s == 0.0
    assert attente_de({"attente": {"delai_phrase_pont_s": 0}}).delai_phrase_pont_s == 0.0


# --------------------------------------------------------------------------- #
# Le comportement pendant la passation
# --------------------------------------------------------------------------- #


@pytest.mark.asyncio
async def test_la_phrase_est_dite_par_la_source_apres_le_delai_une_seule_fois(monkeypatch):
    sonneries = _sonnerie(monkeypatch)
    entendu: list[float] = []

    def ecouter(harness):
        sortie = harness.transport.output()
        traiter = sortie.process_frame

        async def observer(frame, direction):
            if isinstance(frame, TTSAudioRawFrame):
                entendu.append(asyncio.get_running_loop().time())
            await traiter(frame, direction)

        sortie.process_frame = observer

    harness, resultat = await _passation(
        {"attente": {"phrase_pont": PHRASE, "delai_phrase_pont_s": 0.2}}, lenteur=1.0, avant=ecouter
    )
    fin = asyncio.get_running_loop().time()
    try:
        assert resultat["outcome"] == "completed" and harness.engine.active_agent.workflow_id == 99
        assert _phrases(harness) == [("source", PHRASE)]
        # La phrase ARRIVE à l'appelant pendant la passation (l'agent d'origine est en attente et
        # sa voix y est coupée : sans levée de l'attente, aucun son ne sortirait).
        assert entendu and entendu[0] < fin - 0.4, "la phrase n'a pas été entendue pendant l'attente"
        # Le son d'attente s'est tu pour la phrase, puis a repris jusqu'à la fin de la passation.
        assert len(sonneries) == 2
        assert harness.engine.transfer_coordinator._phrase_task is None
    finally:
        await harness.stop()


@pytest.mark.asyncio
async def test_une_passation_rapide_ne_dit_rien_et_annule_la_tache(monkeypatch):
    _sonnerie(monkeypatch)
    # Délai long, passation immédiate : la phrase n'est jamais dite, et on n'attend pas le délai.
    debut = asyncio.get_running_loop().time()
    harness, resultat = await _passation(
        {"attente": {"phrase_pont": PHRASE, "delai_phrase_pont_s": 30}}, lenteur=0
    )
    try:
        assert resultat["outcome"] == "completed"
        assert asyncio.get_running_loop().time() - debut < 10
        assert _phrases(harness) == []
        assert harness.engine.transfer_coordinator._phrase_task is None
    finally:
        await harness.stop()


@pytest.mark.asyncio
@pytest.mark.parametrize("attente", [{}, {"phrase_pont": ""}, {"phrase_pont": "  "}], ids=["absente", "vide", "blanche"])
async def test_phrase_vide_ou_absente_rien_n_est_dit(monkeypatch, attente):
    _sonnerie(monkeypatch)
    harness, resultat = await _passation(
        {"attente": {**attente, "delai_phrase_pont_s": 0.1}}, lenteur=0.6
    )
    try:
        assert resultat["outcome"] == "completed"
        assert _phrases(harness) == []
        assert harness.engine.transfer_coordinator._phrase_task is None
    finally:
        await harness.stop()


@pytest.mark.asyncio
async def test_jamais_vers_le_principal_chaud(monkeypatch):
    _sonnerie(monkeypatch)
    harness, premier = await _passation(
        {"attente": {"phrase_pont": PHRASE, "delai_phrase_pont_s": 0.2}}, lenteur=1.0
    )
    try:
        assert premier["outcome"] == "completed"
        assert _phrases(harness) == [("source", PHRASE)]
        # Retour vers le principal resté chaud : la préparation reste lente, le délai tombe, rien n'est dit.
        with patch(PATCH_OUTILS, AsyncMock(return_value=[TransferAgentTool()])):
            assert (await _passer(harness, 1))["outcome"] == "completed"
        assert harness.engine.active_agent.workflow_id == 1
        assert _phrases(harness) == [("source", PHRASE)], "phrase dite vers un agent déjà construit"
    finally:
        await harness.stop()


@pytest.mark.asyncio
async def test_jamais_au_clavier(monkeypatch):
    _sonnerie(monkeypatch)

    def clavier(harness):
        harness.engine.sans_sortie_audio = True

    harness, resultat = await _passation(
        {"attente": {"phrase_pont": PHRASE, "delai_phrase_pont_s": 0.1}}, lenteur=0.6, avant=clavier
    )
    try:
        assert resultat["outcome"] == "completed"
        assert _phrases(harness) == []
    finally:
        await harness.stop()


@pytest.mark.asyncio
async def test_une_demande_silencieuse_ne_dit_rien(monkeypatch):
    _sonnerie(monkeypatch)
    harness, resultat = await _passation(
        {"attente": {"phrase_pont": PHRASE, "delai_phrase_pont_s": 0.1}},
        lenteur=0.6,
        silencieuse=True,
    )
    try:
        assert resultat["outcome"] == "completed"
        assert _phrases(harness) == []
    finally:
        await harness.stop()


@pytest.mark.asyncio
async def test_sans_son_d_attente_la_phrase_est_dite_quand_meme(monkeypatch):
    sonneries = _sonnerie(monkeypatch)
    harness, resultat = await _passation(
        {"attente": {"son": "aucun", "phrase_pont": PHRASE, "delai_phrase_pont_s": 0.1}}, lenteur=0.8
    )
    try:
        assert resultat["outcome"] == "completed"
        assert _phrases(harness) == [("source", PHRASE)]
        assert sonneries == []
    finally:
        await harness.stop()


@pytest.mark.asyncio
async def test_une_passation_invalidee_annule_la_phrase(monkeypatch):
    _sonnerie(monkeypatch)
    harness = await _monter_groupe(
        {**GROUPE, "attente": {"phrase_pont": PHRASE, "delai_phrase_pont_s": 30}}
    )
    try:
        _ralentir_la_preparation(harness, 5)
        coordinateur = harness.engine.transfer_coordinator
        demande = agent_transfer.TransferRequest(
            destination_workflow_id=99,
            destination_label="vers",
            origin_visit_id=harness.engine.active_agent.visit_id,
        )
        with patch(PATCH_OUTILS, AsyncMock(return_value=[TransferAgentTool()])):
            assert coordinateur.accept(demande)
            coordinateur.start(demande)
            await asyncio.sleep(0.3)
            assert coordinateur._phrase_task is not None and not coordinateur._phrase_task.done()
            await coordinateur.invalidate("test")
        assert coordinateur._phrase_task is None
        assert _phrases(harness) == []
    finally:
        await harness.stop()


# --------------------------------------------------------------------------- #
# Relecture du 16/10 : la source réactivée le temps de la phrase ne pense pas, le son d'attente
# reprend quoi qu'il arrive, la passation n'attend pas une phrase longue.
# --------------------------------------------------------------------------- #


@pytest.mark.asyncio
async def test_la_source_reactivee_ne_lance_aucune_inference_pendant_la_phrase(monkeypatch):
    """L'appelant parle pendant la phrase : le contexte que l'appel enverrait au modèle de la source
    n'arrive jamais jusqu'à lui (``allow_inference``), et son cerveau est muet (``muter``). Contrôle :
    avant la passation, le même contexte l'atteint (sinon le test ne prouverait rien)."""
    from pipecat.frames.frames import LLMContextFrame

    from api.services.pipecat.main_passee import ATTRIBUT

    _sonnerie(monkeypatch)
    harness = await _monter_groupe(
        {**GROUPE, "attente": {"phrase_pont": PHRASE, "delai_phrase_pont_s": 0.2}}
    )
    try:
        engine = harness.engine
        source = engine.active_agent
        recus: list[float] = []
        traiter = source.llm.process_frame

        async def espion(frame, direction):
            if isinstance(frame, LLMContextFrame):
                recus.append(asyncio.get_running_loop().time())
            await traiter(frame, direction)

        source.llm.process_frame = espion
        # Contrôle : hors passation, le contexte arrive au modèle de la source.
        await harness.call_worker.queue_frame(LLMContextFrame(engine.context))
        await asyncio.sleep(0.3)
        assert recus, "l'espion ne voit pas le contexte : le test ne prouverait rien"
        recus.clear()

        _ralentir_la_preparation(harness, 1.2)
        pendant_la_phrase: dict = {}
        queue_speech = engine.queue_speech

        async def phrase_espionnee(*args, **kwargs):
            if args and args[0] == PHRASE:  # pas l'ouverture de l'agent appelé, plus tard
                pendant_la_phrase["muet"] = getattr(source.llm, ATTRIBUT, False)
                pendant_la_phrase["actif"] = source.worker.active
                # L'appelant a parlé : le contexte part vers le modèle de la source.
                await harness.call_worker.queue_frame(LLMContextFrame(engine.context))
            return await queue_speech(*args, **kwargs)

        engine.queue_speech = phrase_espionnee
        with patch(PATCH_OUTILS, AsyncMock(return_value=[TransferAgentTool()])):
            assert (await _passer(harness, 99))["outcome"] == "completed"
        assert pendant_la_phrase == {"muet": True, "actif": True}
        assert recus == [], "le modèle de la source a reçu un contexte pendant la passation"
        assert _phrases(harness) == [("source", PHRASE)]
    finally:
        await harness.stop()


@pytest.mark.asyncio
async def test_une_passation_qui_echoue_pendant_la_phrase_rend_l_appel_a_la_source(monkeypatch):
    from api.services.pipecat.agent_runtime_factory import AgentBuildError

    sonneries = _sonnerie(monkeypatch)
    harness = await _monter_groupe(
        {**GROUPE, "attente": {"phrase_pont": PHRASE, "delai_phrase_pont_s": 0.2}}
    )
    try:
        engine = harness.engine
        source = engine.active_agent

        async def echoue(runtime):
            await asyncio.sleep(1.0)
            raise AgentBuildError("test_echec", "la préparation échoue après la phrase")

        engine.prepare_agent = echoue
        with patch(PATCH_OUTILS, AsyncMock(return_value=[TransferAgentTool()])):
            resultat = await _passer(harness, 99)
        assert resultat["outcome"] == "test_echec"
        assert _phrases(harness) == [("source", PHRASE)]
        # La source garde l'appel, active, hors attente ; plus de tâche ni de son d'attente.
        assert engine.active_agent is source and source.worker.active
        assert engine.selected_visit_id == source.visit_id
        coordinateur = engine.transfer_coordinator
        assert coordinateur._phrase_task is None and coordinateur._hold_task is None
        assert sonneries, "le son d'attente n'a jamais joué"
    finally:
        await harness.stop()


@pytest.mark.asyncio
async def test_le_son_d_attente_reprend_meme_si_la_phrase_ne_peut_pas_etre_dite(monkeypatch):
    """``queue_speech`` lève : le son d'attente reprend (un filet ne coûte jamais le silence) et la
    passation aboutit."""
    sonneries = _sonnerie(monkeypatch)
    harness = await _monter_groupe(
        {**GROUPE, "attente": {"phrase_pont": PHRASE, "delai_phrase_pont_s": 0.2}}
    )
    try:
        engine = harness.engine
        _ralentir_la_preparation(harness, 1.2)
        queue_speech = engine.queue_speech

        async def voix_absente(*args, **kwargs):
            if args and args[0] == PHRASE:
                raise RuntimeError("voix absente")
            return await queue_speech(*args, **kwargs)

        engine.queue_speech = voix_absente
        with patch(PATCH_OUTILS, AsyncMock(return_value=[TransferAgentTool()])):
            assert (await _passer(harness, 99))["outcome"] == "completed"
        # Deux sons : l'un coupé pour la phrase, l'autre repris jusqu'à la fin de la passation.
        assert len(sonneries) == 2
        assert engine.active_agent.workflow_id == 99
    finally:
        await harness.stop()


@pytest.mark.asyncio
async def test_une_phrase_trop_longue_n_est_pas_attendue_au_dela_de_deux_secondes(monkeypatch):
    _sonnerie(monkeypatch)
    harness = await _monter_groupe(
        {**GROUPE, "attente": {"phrase_pont": PHRASE, "delai_phrase_pont_s": 0.2}}
    )
    try:
        engine = harness.engine
        _ralentir_la_preparation(harness, 0.6)
        # Une phrase qui ne finit jamais de jouer.
        engine.queue_speech = _phrase_sans_fin(engine)
        debut = asyncio.get_running_loop().time()
        with patch(PATCH_OUTILS, AsyncMock(return_value=[TransferAgentTool()])):
            assert (await _passer(harness, 99))["outcome"] == "completed"
        duree = asyncio.get_running_loop().time() - debut
        assert agent_transfer.ATTENTE_FIN_PHRASE_PONT_S == 2.0
        assert duree < 0.6 + agent_transfer.ATTENTE_FIN_PHRASE_PONT_S + 2.5, duree
        assert engine.transfer_coordinator._phrase_task is None
    finally:
        await harness.stop()


@pytest.mark.asyncio
async def test_annuler_la_passation_en_pleine_phrase_ne_l_attend_pas(monkeypatch):
    _sonnerie(monkeypatch)
    harness = await _monter_groupe(
        {**GROUPE, "attente": {"phrase_pont": PHRASE, "delai_phrase_pont_s": 0.1}}
    )
    try:
        engine = harness.engine
        _ralentir_la_preparation(harness, 10)
        engine.queue_speech = _phrase_sans_fin(engine)
        coordinateur = engine.transfer_coordinator
        demande = agent_transfer.TransferRequest(
            destination_workflow_id=99,
            destination_label="vers",
            origin_visit_id=engine.active_agent.visit_id,
        )
        with patch(PATCH_OUTILS, AsyncMock(return_value=[TransferAgentTool()])):
            assert coordinateur.accept(demande)
            coordinateur.start(demande)
            async with asyncio.timeout(5):
                while not coordinateur._phrase_en_cours:
                    await asyncio.sleep(0.02)
            debut = asyncio.get_running_loop().time()
            await coordinateur.invalidate("test")
        assert asyncio.get_running_loop().time() - debut < 1.5
        assert coordinateur._phrase_task is None and coordinateur._phrase_en_cours is False
    finally:
        await harness.stop()
