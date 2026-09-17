"""[.mark] The voice says the numbers of the answer in words (plan voix-et-communes, V1).

Why a text TRANSFORM, not a text filter
---------------------------------------
The plan named a text filter (T1). Read in Pipecat on 2026-09-17: a filter
changes the text that ALSO becomes the ``TTSTextFrame`` added to the
assistant's context (``tts_service.py``, ``TTSTextFrame(text, …)`` after the
filters). The model would then read "soixante, cinq cent cinquante" in its
own history, and the transcript would too: the opposite of V1. A transform
changes only the text sent to the voice; the context keeps what the model
wrote. It is Pipecat's own seam for "for the voice only", the one the
pronunciation replacements already use.

⚠️ True for voices WITHOUT word timestamps, Voxtral (Mistral) among them
(asserted by test_nombres_pour_la_voix.py). A voice that times each word (ElevenLabs, Cartesia, Azure, Rime,
Inworld, Speechify, Dograh) builds the context from what it SAID: the history
would then hold the words (Pipecat, ``tts_service.py``). Our agents speak with
Voxtral; changing the voice means checking this first (review of 2026-09-17).

When it runs
------------
- French agents only (``langue_agent_francaise``), without a switch on screen:
  Dograh is our internal tool, and a setting that must be turned on is a
  setting that can be forgotten (decision confirmed at the go, 2026-09-17).
- Sentence aggregation only (the default, and every agent today). Word by
  word ("token"), a number arrives in pieces ("15" then " 000") and cannot be
  read; the context there is also built from the transformed text.

⛔ What it must never do
- Cost the answer: Pipecat drops the whole sentence's audio when a transform
  raises. Any failure returns the text unchanged, with a warning.
- Read the list of communes on the event loop: the list is used only if
  already read (the caller-reading step preloads it at the start of the
  call); otherwise it is read in a worker thread for the next sentences, and
  five digits are a postal code only by their context meanwhile.
"""

from __future__ import annotations

import asyncio

from loguru import logger

from api.services.communes.base import base_si_chargee, obtenir_base
from api.services.nombres.voix import ecrire_pour_la_voix

_chargement: asyncio.Task | None = None


def _codes_postaux():
    global _chargement
    base = base_si_chargee()
    if base is not None:
        return base.par_cp
    if _chargement is None or (_chargement.done() and base_si_chargee() is None):
        try:
            _chargement = asyncio.get_running_loop().create_task(obtenir_base())
            _chargement.add_done_callback(_signaler_echec)
        except RuntimeError:
            pass
    return None


def _signaler_echec(tache: asyncio.Task) -> None:
    if not tache.cancelled() and tache.exception() is not None:
        logger.warning(f"[.mark] List of communes not read for the voice: {tache.exception()!r}")


async def nombres_en_mots(texte: str, _type: str = "*") -> str:
    """Pipecat text transform: ``texte`` with its numbers in words. Never raises."""
    try:
        return ecrire_pour_la_voix(texte, _codes_postaux())
    except Exception as erreur:  # noqa: BLE001 -- the voice must go on
        logger.warning(f"[.mark] Numbers not written in words for the voice: {erreur!r}")
        return texte
