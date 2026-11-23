"""[.mark] Module Restauration, lot 10 : « une seule fois » : une alerte, un SMS ne partent jamais deux fois (clé à usage unique dans Redis, qui s'efface seule)."""

from __future__ import annotations

import redis.asyncio as aioredis

from api.constants import REDIS_URL

DUREE_S = 24 * 3600  # la commande a quitté les « sans réponse » bien avant ; la clé s'efface seule


def _redis() -> aioredis.Redis:
    return aioredis.from_url(REDIS_URL, decode_responses=True, socket_timeout=3, socket_connect_timeout=3)


async def une_seule_fois(cle: str) -> bool:
    """``True`` la première fois pour cette clé."""
    redis = _redis()
    try:
        return bool(await redis.set(cle, "1", ex=DUREE_S, nx=True))
    finally:
        await redis.aclose()


async def oublier_une_fois(cle: str) -> None:
    """Rend la clé : ce qu'elle gardait n'a pas eu lieu, il pourra être retenté."""
    redis = _redis()
    try:
        await redis.delete(cle)
    finally:
        await redis.aclose()
