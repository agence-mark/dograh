"""[.mark] A lock by name, for the actions of ONE call that read, decide, then write (revue du 07/10).

Pipecat runs the tool calls of one turn in parallel. An action that reads a state, compares, then
writes it back (the caller's verification, the booking of an appointment) would let two calls of
the same turn read the same state: four wrong answers counted as two attempts, a success
overwritten by a failure, two appointments for one slot.

Two layers, both needed:

- an ``asyncio.Lock`` in the process (cheap, exact for the tool calls of one engine);
- a Redis ``SET NX PX`` (the keyboard rebuilds an engine per message, a call can reach another
  worker): the lease ends by itself, so a crash never leaves the name taken, and the release
  only removes the lock of its own holder.

Nothing client-specific, no business word: the caller chooses the name (organization AND run).
Redis unreachable or the lock not obtained within ``attente_s``: ``Occupe`` is raised, the caller
fails closed (nothing is read, nothing is booked).
"""

from __future__ import annotations

import asyncio
import contextvars
import secrets
from contextlib import asynccontextmanager

from loguru import logger

PREFIXE = "mark:verrou:v1:"
BAIL_S = 15.0  # the lease: longer than the slowest action (the deadline of a tool is 15 s at most)
ATTENTE_S = 12.0
_PAS_S = 0.025

_LIBERER = (
    "if redis.call('get', KEYS[1]) == ARGV[1] then return redis.call('del', KEYS[1]) else return 0 end"
)


class Occupe(RuntimeError):
    """The lock could not be taken: refuse rather than act on a state another call is changing."""


# name -> [lock, number of users]; an entry lives only while someone uses it (no lock stays
# attached to the event loop of a call that is over).
_locaux: dict[str, list] = {}


# The protected writes (``garder``) of the locks held by the current task: a lock is given back
# only once they are over, or a waiting call would read the old state and overwrite the new one.
_ecritures: contextvars.ContextVar[tuple[set, ...]] = contextvars.ContextVar("mark_verrou_ecritures", default=())


async def garder(coro):
    """Runs ``coro`` to its end even if the caller is cancelled (the tool's deadline), and makes
    every lock held by the caller wait for it before it is released."""
    tache = asyncio.ensure_future(coro)
    for lot in _ecritures.get():
        lot.add(tache)
        tache.add_done_callback(lot.discard)
    return await asyncio.shield(tache)


async def _redis():
    from api.services.etablissements.copie import _redis as client

    return await client()


@asynccontextmanager
async def verrou(nom: str, *, bail_s: float = BAIL_S, attente_s: float = ATTENTE_S):
    cle = f"{PREFIXE}{nom}"
    entree = _locaux.setdefault(nom, [asyncio.Lock(), 0])
    entree[1] += 1
    jeton = secrets.token_hex(8)
    redis = None
    try:
        try:
            await asyncio.wait_for(entree[0].acquire(), timeout=attente_s)
        except asyncio.TimeoutError as erreur:
            raise Occupe(f"lock « {nom} » busy") from erreur
        try:
            redis = await _redis()
            fin = asyncio.get_running_loop().time() + attente_s
            while True:
                if await redis.set(cle, jeton, nx=True, px=int(bail_s * 1000)):
                    break
                if asyncio.get_running_loop().time() >= fin:
                    raise Occupe(f"lock « {nom} » busy")
                await asyncio.sleep(_PAS_S)
        except Occupe:
            entree[0].release()
            raise
        except Exception as erreur:  # Redis unreachable: fail closed
            entree[0].release()
            logger.error(f"[.mark] Lock « {nom} » not taken, Redis unreachable: {erreur!r}")
            raise Occupe(f"lock « {nom} » unavailable") from erreur
        except BaseException:  # cancelled while waiting: never keep the local lock
            entree[0].release()
            raise
        mon_lot: set = set()
        jeton_ctx = _ecritures.set((*_ecritures.get(), mon_lot))
        annule = False
        try:
            yield
        finally:
            try:
                _ecritures.reset(jeton_ctx)
            except ValueError:  # another context (generator closed elsewhere): nothing to restore
                pass
            try:
                # The protected writes end BEFORE the lock goes back.
                while mon_lot:
                    try:
                        await asyncio.wait(set(mon_lot))
                    except asyncio.CancelledError:
                        annule = True
                try:
                    await asyncio.shield(redis.eval(_LIBERER, 1, cle, jeton))
                except asyncio.CancelledError:
                    annule = True  # the lease ends by itself; the cancellation is passed on below
                except Exception as erreur:  # noqa: BLE001 -- the lease ends by itself
                    logger.warning(f"[.mark] Lock « {nom} » not released, its lease will end: {erreur!r}")
            finally:
                entree[0].release()
            if annule:
                raise asyncio.CancelledError
    finally:
        entree[1] -= 1
        if entree[1] <= 0 and _locaux.get(nom) is entree:
            del _locaux[nom]
