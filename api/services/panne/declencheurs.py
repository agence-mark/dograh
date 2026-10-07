"""[.mark] What calls the outage guard (L7, PN1 to PN3; plan panne-vers-magasin lot 3).

Plugged at pick-up by ``run_pipeline`` for an agent that switched the fallback on (X2):

- an error the call cannot survive (voice, transcription, model: rejected key, quota, a voice
  that keeps answering without sound, F5, F6): ``sur_erreur_terminale``, called by the single
  disposal point of the pipeline (``event_handlers.dispose_call``), BEFORE the call ends;
- the model too slow twice in a row (PN2): ``ReplisDelaiModele`` on the Mistral service;
- the voice too slow (PN3): ``ObservateurVoixLente``, past ``delai_voix_s`` between the start of
  a synthesis and its first sound.

Each trigger asks the guard once; the guard decides once for the whole call.
"""

from __future__ import annotations

import asyncio
import time
from typing import Any

from loguru import logger
from pipecat.frames.frames import (
    InterruptionFrame,
    TTSAudioRawFrame,
    TTSStartedFrame,
    TTSStoppedFrame,
)
from pipecat.observers.base_observer import BaseObserver, FramePushed
from pipecat.utils.enums import EndTaskReason

from api.services.panne.delai_modele import ReplisDelaiModele
from api.services.panne.gardien import ContextePanne, GardienPanne

ATTRIBUT_GARDIEN = "mark_gardien_panne"


def gardien_de(engine: Any) -> GardienPanne | None:
    return getattr(engine, ATTRIBUT_GARDIEN, None)


def _brique(erreur: Any) -> str:
    nom = (
        type(getattr(erreur, "processor", None)).__name__.lower()
        if getattr(erreur, "processor", None)
        else ""
    )
    if "tts" in nom:
        return "voix"
    if "stt" in nom:
        return "transcription"
    if "llm" in nom:
        return "modele"
    return "chaine"


async def sur_erreur_terminale(engine: Any, erreur: Any) -> None:
    """Called before the pipeline is disposed of. Never raises."""
    gardien = gardien_de(engine)
    if gardien is None or erreur is None:
        return
    try:
        await gardien.declencher(
            "erreur_terminale",
            _brique(erreur),
            getattr(erreur, "error", None) or str(erreur),
        )
    except Exception as e:  # noqa: BLE001
        logger.error(f"[.mark] Outage fallback on a terminal error failed: {e!r}")


class ObservateurVoixLente(BaseObserver):
    """PN3: a synthesis that gives no sound within the delay is an outage of the voice."""

    def __init__(self, tts: Any, seuil_s: float, au_depassement):
        super().__init__()
        self._tts = tts
        self._seuil = seuil_s
        self._au_depassement = au_depassement
        self._minuterie: asyncio.Task | None = None
        self._declenche = False

    def _annuler(self) -> None:
        if self._minuterie is not None and not self._minuterie.done():
            self._minuterie.cancel()
        self._minuterie = None

    async def _attendre(self, debut: float) -> None:
        await asyncio.sleep(self._seuil)
        self._declenche = True
        await self._au_depassement(round(time.monotonic() - debut, 2))

    async def on_push_frame(self, data: FramePushed) -> None:
        if self._declenche or data.source is not self._tts:
            return
        trame = data.frame
        if isinstance(trame, TTSStartedFrame):
            if self._minuterie is None:
                self._minuterie = asyncio.get_running_loop().create_task(
                    self._attendre(time.monotonic())
                )
        elif isinstance(trame, (TTSAudioRawFrame, TTSStoppedFrame, InterruptionFrame)):
            self._annuler()


def brancher(
    engine: Any, task: Any, llm: Any, tts: Any, contexte: ContextePanne
) -> GardienPanne | None:
    """Build the guard of this call and plug its triggers. Never raises."""
    try:
        gardien = GardienPanne(contexte, engine)
        setattr(engine, ATTRIBUT_GARDIEN, gardien)

        async def terminer() -> None:
            await engine.end_call_with_reason(
                EndTaskReason.PIPELINE_ERROR.value, abort_immediately=True
            )

        if llm is not None and hasattr(llm, "mark_delai_modele_s"):
            llm.mark_delai_modele_s = contexte.reglages.delai_modele_s
            ReplisDelaiModele(engine, task, gardien, terminer).brancher(llm)

        async def voix_lente(ecart_s: float) -> None:
            try:
                await gardien.declencher("voix_lente", "voix", f"{ecart_s} s sans son")
            finally:
                await terminer()

        if tts is not None:
            task.add_observer(
                ObservateurVoixLente(tts, contexte.reglages.delai_voix_s, voix_lente)
            )
        return gardien
    except Exception as erreur:  # noqa: BLE001 -- the call goes on as before
        logger.error(
            f"[.mark] Outage fallback not plugged, the call goes on without it: {erreur!r}"
        )
        return None
