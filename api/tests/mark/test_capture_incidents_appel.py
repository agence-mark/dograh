"""[.mark] Coupures, interruptions et relances d'inactivité sont gardées par le run
(chantier langwatch-et-fenetre-du-run, lot 2, étape 3).

Questions :
1. Une déconnexion ou une erreur de connexion de la transcription ou de la voix, annoncée par
   Pipecat, arrive-t-elle au journal du run ? (vrais services Deepgram, aucun réseau)
2. Une interruption de l'agent PAR L'APPELANT est-elle notée, et une interruption que le moteur
   provoque hors de toute parole de l'appelant ne l'est-elle pas ?
3. Une relance d'inactivité est-elle notée par ``handle_user_idle`` lui-même ?
4. La fenêtre en tire-t-elle les incidents et les marques, sans compter la déconnexion normale de
   fin d'appel ?
"""

import asyncio
import inspect
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from pipecat.frames.frames import (
    BotStartedSpeakingFrame,
    BotStoppedSpeakingFrame,
    InterruptionFrame,
    UserStartedSpeakingFrame,
    UserStoppedSpeakingFrame,
)
from pipecat.observers.base_observer import FramePushed
from pipecat.processors.frame_processor import FrameDirection
from pipecat.services.deepgram.flux.stt import DeepgramFluxSTTService
from pipecat.services.deepgram.tts import DeepgramTTSService

from api.services.analyse_run.analyse import analyser_run
from api.services.analyse_run.incidents_appel import (
    ATTRIBUT_JOURNAL,
    TYPE_CONNEXION,
    TYPE_INTERRUPTION,
    TYPE_RELANCE,
    ObservateurDesInterruptions,
    brancher_les_connexions,
)
from api.services.pipecat import run_pipeline
from api.services.workflow import pipecat_engine_callbacks


class _Journal:
    def __init__(self):
        self.evenements = []

    async def append(self, evenement):
        self.evenements.append(evenement)


async def _laisser_tourner():
    for _ in range(5):
        await asyncio.sleep(0)


@pytest.mark.asyncio
async def test_les_coupures_de_la_transcription_et_de_la_voix_sont_notees():
    stt = DeepgramFluxSTTService(api_key="cle-de-test")
    tts = DeepgramTTSService(api_key="cle-de-test")
    journal = _Journal()
    assert brancher_les_connexions(
        {"transcription": stt, "voice": tts, "rien": None}, journal
    ) == [
        "transcription",
        "voice",
    ]
    await stt._call_event_handler("on_connected")
    await stt._call_event_handler("on_disconnected")
    await tts._call_event_handler("on_connection_error", "boom")
    await _laisser_tourner()
    notes = [
        (e["payload"]["component"], e["payload"]["event"]) for e in journal.evenements
    ]
    assert all(e["type"] == TYPE_CONNEXION for e in journal.evenements)
    assert sorted(notes) == [
        ("transcription", "connected"),
        ("transcription", "disconnected"),
        ("voice", "error"),
    ]
    erreur = next(e for e in journal.evenements if e["payload"]["event"] == "error")
    assert erreur["payload"]["error"] == "boom"
    assert erreur["payload"]["service"] == "DeepgramTTSService"


def _poussee(trame):
    return FramePushed(
        source=None,
        destination=None,
        frame=trame,
        direction=FrameDirection.DOWNSTREAM,
        timestamp=0,
    )


@pytest.mark.asyncio
async def test_seule_l_interruption_par_l_appelant_est_notee():
    journal = _Journal()
    observateur = ObservateurDesInterruptions(journal)
    # Le moteur interrompt l'agent sans que l'appelant parle : rien.
    for trame in (BotStartedSpeakingFrame(), InterruptionFrame()):
        await observateur.on_push_frame(_poussee(trame))
    assert journal.evenements == []
    # L'appelant parle pendant que l'agent parle : une interruption, comptée une seule fois
    # même si la trame passe par plusieurs processeurs.
    interruption = InterruptionFrame()
    for trame in (
        UserStartedSpeakingFrame(),
        interruption,
        interruption,
        BotStoppedSpeakingFrame(),
    ):
        await observateur.on_push_frame(_poussee(trame))
    assert [e["type"] for e in journal.evenements] == [TYPE_INTERRUPTION]
    # L'agent ne parle plus : la parole de l'appelant n'interrompt rien.
    for trame in (
        UserStoppedSpeakingFrame(),
        UserStartedSpeakingFrame(),
        InterruptionFrame(),
    ):
        await observateur.on_push_frame(_poussee(trame))
    assert len(journal.evenements) == 1


@pytest.mark.asyncio
async def test_handle_user_idle_note_la_relance_puis_le_raccrochage():
    journal = _Journal()
    moteur = SimpleNamespace(
        reglages_relances={"user_idle_max_prompts": 1},
        end_call_with_reason=AsyncMock(),
    )
    setattr(moteur, ATTRIBUT_JOURNAL, journal)
    agregateur = SimpleNamespace(push_frame=AsyncMock())
    await pipecat_engine_callbacks.handle_user_idle(moteur, agregateur, 1)
    await pipecat_engine_callbacks.handle_user_idle(moteur, agregateur, 2)
    assert [e["payload"] for e in journal.evenements] == [
        {"attempt": 1, "hang_up": False},
        {"attempt": 2, "hang_up": True},
    ]
    assert all(e["type"] == TYPE_RELANCE for e in journal.evenements)


@pytest.mark.asyncio
async def test_sans_journal_la_relance_se_joue_quand_meme():
    moteur = SimpleNamespace(reglages_relances={}, end_call_with_reason=AsyncMock())
    agregateur = SimpleNamespace(push_frame=AsyncMock())
    await pipecat_engine_callbacks.handle_user_idle(moteur, agregateur, 1)
    agregateur.push_frame.assert_awaited()


def test_l_appel_vocal_pose_les_trois_captures_apres_l_observateur_de_dograh():
    source = inspect.getsource(run_pipeline)
    dograh = source.index("task.add_observer(feedback_observer)")
    for geste in (
        "task.add_observer(ObservateurDesInterruptions(in_memory_logs_buffer))",
        'brancher_les_connexions({"transcription": stt, "voice": tts}, in_memory_logs_buffer)',
        "setattr(engine, ATTRIBUT_JOURNAL, in_memory_logs_buffer)",
    ):
        assert source.index(geste) > dograh, geste


def test_la_fenetre_tire_incidents_et_marques_sans_la_fin_d_appel():
    def ev(type_, tour, **charge):
        return {
            "type": type_,
            "turn": tour,
            "timestamp": f"2026-10-05T10:00:{10 + tour:02d}.000+00:00",
            "payload": charge,
        }

    run = {
        "id": 1,
        "logs": {
            "realtime_feedback_events": [
                ev(
                    TYPE_CONNEXION,
                    1,
                    component="transcription",
                    service="S",
                    event="connected",
                ),
                ev(
                    TYPE_CONNEXION,
                    4,
                    component="transcription",
                    service="S",
                    event="disconnected",
                ),
                ev(
                    TYPE_CONNEXION,
                    4,
                    component="transcription",
                    service="S",
                    event="connected",
                ),
                ev(
                    TYPE_CONNEXION,
                    5,
                    component="voice",
                    service="V",
                    event="error",
                    error="boom",
                ),
                ev(TYPE_INTERRUPTION, 3),
                ev(TYPE_RELANCE, 6, attempt=1, hang_up=False),
                ev(
                    TYPE_CONNEXION,
                    9,
                    component="transcription",
                    service="S",
                    event="disconnected",
                ),
            ]
        },
    }
    analyse = analyser_run(run)
    assert analyse["providers"]["connections"] == {
        "transcription": {"disconnections": 1, "errors": 0},
        "voice": {"disconnections": 0, "errors": 1},
    }
    natures = sorted(i["kind"] for i in analyse["incidents"]["items"])
    assert natures == ["provider_disconnected", "provider_error"]
    assert [m["kind"] for m in analyse["conversation"]["marks"]] == [
        "caller_interrupted",
        "idle_reminder",
    ]
