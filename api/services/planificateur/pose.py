"""[.mark] What the planner has booked in ONE call, kept apart from the call's record (revue du 07/10).

Why it exists. ``poser_rendez_vous`` writes in the client's calendar software, then the record
notes it for the hub. Two things escaped that: the model can book twice in one call (« finalement
jeudi ») or two bookings of one turn can run in parallel; and the tool's deadline can cancel the
action AFTER the software created the event, leaving an event nobody knows.

So the booking state lives in Redis, under the organization AND the run (like the verification
state: never in the record the model's extraction writes, never in a parameter):

- ``en_cours``: a creation was started (the slot, the agenda). Cleared when the software said no.
  It stays when the answer was lost (timeout, cancellation): the event may exist.
- ``pose``: the appointment booked in this call, with the note for the hub, ready to be given
  again unchanged if the model asks for the same slot twice.

Nothing here is a business word or a client's: a slot, an agenda, an identifier.
"""

from __future__ import annotations

import asyncio
import json

from loguru import logger

PREFIXE = "mark:planificateur:pose:v1:"
DUREE_S = 4 * 3600


def cle(organization_id: int, run_id: int) -> str:
    return f"{PREFIXE}{int(organization_id)}:{int(run_id)}"


async def _redis():
    from api.services.etablissements.copie import _redis as client

    return await client()


async def lire(organization_id: int, run_id: int) -> dict:
    """The state, ``{}`` when none. Raises when Redis is unreachable: the caller refuses to book
    rather than risk a second event."""
    brut = await (await _redis()).get(cle(organization_id, run_id))
    if not brut:
        return {}
    try:
        donnees = json.loads(brut)
        return donnees if isinstance(donnees, dict) else {}
    except ValueError:
        logger.error("[.mark] Booking state unreadable, treated as empty")
        return {}


async def ecrire(organization_id: int, run_id: int, etat: dict) -> None:
    """Kept even if the tool's deadline cancels the caller meanwhile (``shield``)."""
    await asyncio.shield(
        _ecrire(organization_id, run_id, etat)
    )


async def _ecrire(organization_id: int, run_id: int, etat: dict) -> None:
    redis = await _redis()
    if etat:
        await redis.set(cle(organization_id, run_id), json.dumps(etat), ex=DUREE_S)
    else:
        await redis.delete(cle(organization_id, run_id))
