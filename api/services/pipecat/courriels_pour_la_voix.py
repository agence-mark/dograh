"""[.mark] The voice says e-mail addresses in words (plan courriel-dicte, lot 2).

A Pipecat text TRANSFORM, for the reason ``nombres_pour_la_voix.py`` gives: it changes
only the text sent to the voice (⚠️ with its same limit for a voice that times each
word, ElevenLabs among them: see ``epellation/voix.py``). Branched
at the same place and on the same conditions (French agent, sentence aggregation),
BEFORE the numbers: the digits of an address ("jean75@…") are then said by them.
"""

from __future__ import annotations

from loguru import logger

from api.services.epellation.voix import courriels_pour_la_voix


async def courriels_en_mots(texte: str, _type: str = "*") -> str:
    """Pipecat text transform: ``texte`` with its addresses in words. Never raises."""
    try:
        return courriels_pour_la_voix(texte)
    except Exception as erreur:  # noqa: BLE001 -- the voice must go on
        logger.warning(
            f"[.mark] Address not written in words for the voice: {erreur!r}"
        )
        return texte
