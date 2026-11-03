"""[.mark] Le module d'événements unique (builder partie 2, D2) : Redis réveille, la base fait foi, SSE diffuse.

Tout flux d'événements de .mark qui doit survivre à un rechargement de l'écran passe ici (le builder aujourd'hui ; les
sous-agents et la lecture du fork demain). Le principe :

* **la vérité est une table** : chaque producteur écrit ses événements dans sa table (ordre = identifiant croissant) ;
* **Redis ne porte aucune donnée**, seulement un réveil par canal (``publier``) : un Redis lent, absent ou figé ne perd
  jamais un événement, il rend seulement la diffusion plus lente (relecture de la table à intervalle court) ;
* **SSE** : ``suivre`` rejoue depuis le dernier événement reçu (``Last-Event-ID``), puis attend les réveils ;
  ``flux_sse`` met en forme (``id:``, ``data:``, battement de cœur).

Le transport est remplaçable (``utiliser_transport``) : les tests posent le transport en mémoire, rien n'ouvre Redis.
"""

from __future__ import annotations

import asyncio
import json
from collections.abc import AsyncIterator, Awaitable, Callable
from contextlib import asynccontextmanager
from typing import Any, Protocol

from loguru import logger

DELAI_REDIS_S = 1.0
RELECTURE_MAX_S = 1.0  # sans réveil, la table est relue au plus toutes les secondes
BATTEMENT_S = 15.0


class Abonne(Protocol):
    async def attendre(self, delai: float) -> bool: ...


class Transport(Protocol):
    async def publier(self, canal: str) -> None: ...

    def abonner(self, canal: str): ...


# --- transport en mémoire (tests, et repli sans Redis) --------------------------------------------------------------


class _AbonneMemoire:
    def __init__(self) -> None:
        self.reveil = asyncio.Event()

    async def attendre(self, delai: float) -> bool:
        try:
            await asyncio.wait_for(self.reveil.wait(), delai)
        except TimeoutError:
            return False
        self.reveil.clear()
        return True


class TransportMemoire:
    def __init__(self) -> None:
        self._abonnes: dict[str, set[_AbonneMemoire]] = {}

    async def publier(self, canal: str) -> None:
        for abonne in list(self._abonnes.get(canal, ())):
            abonne.reveil.set()

    @asynccontextmanager
    async def abonner(self, canal: str):
        abonne = _AbonneMemoire()
        self._abonnes.setdefault(canal, set()).add(abonne)
        try:
            yield abonne
        finally:
            self._abonnes[canal].discard(abonne)


# --- transport Redis -------------------------------------------------------------------------------------------------

_redis: Any = None


async def _client_redis():
    global _redis
    if _redis is None:
        import redis.asyncio as aioredis

        from api.constants import REDIS_URL

        _redis = aioredis.from_url(
            REDIS_URL, decode_responses=True, socket_timeout=DELAI_REDIS_S, socket_connect_timeout=DELAI_REDIS_S
        )
    return _redis


class _AbonneRedis:
    def __init__(self, pubsub: Any | None) -> None:
        self._pubsub = pubsub

    async def attendre(self, delai: float) -> bool:
        if self._pubsub is None:  # pas de Redis : simple relecture à intervalle court
            await asyncio.sleep(min(delai, RELECTURE_MAX_S))
            return False
        try:
            message = await self._pubsub.get_message(ignore_subscribe_messages=True, timeout=min(delai, RELECTURE_MAX_S))
            return message is not None
        except Exception as erreur:  # noqa: BLE001 -- Redis tombé en route : on relit la table
            logger.warning(f"[.mark] events: Redis wake-up lost ({erreur!r}), falling back to polling")
            self._pubsub = None
            await asyncio.sleep(min(delai, RELECTURE_MAX_S))
            return False


class TransportRedis:
    async def publier(self, canal: str) -> None:
        try:
            redis = await _client_redis()
            await asyncio.wait_for(redis.publish(canal, "1"), DELAI_REDIS_S)
        except Exception as erreur:  # noqa: BLE001 -- jamais bloquant : la table fait foi
            logger.warning(f"[.mark] events: wake-up not published on {canal} ({erreur!r})")

    @asynccontextmanager
    async def abonner(self, canal: str):
        pubsub = None
        try:
            redis = await _client_redis()
            pubsub = redis.pubsub()
            await asyncio.wait_for(pubsub.subscribe(canal), DELAI_REDIS_S)
        except Exception as erreur:  # noqa: BLE001
            logger.warning(f"[.mark] events: no Redis subscription on {canal} ({erreur!r}), polling instead")
            pubsub = None
        try:
            yield _AbonneRedis(pubsub)
        finally:
            if pubsub is not None:
                try:
                    await asyncio.wait_for(pubsub.aclose(), DELAI_REDIS_S)
                except Exception:  # noqa: BLE001
                    pass


_transport: Transport = TransportRedis()


def utiliser_transport(transport: Transport) -> Transport:
    """Remplace le transport (les tests) ; rend l'ancien pour le remettre."""
    global _transport
    ancien, _transport = _transport, transport
    return ancien


async def publier(canal: str) -> None:
    await _transport.publier(canal)


# --- la lecture : rejouer puis suivre --------------------------------------------------------------------------------

LireApres = Callable[[int], Awaitable[list[tuple[int, dict[str, Any]]]]]
EstFini = Callable[[], Awaitable[bool]]


async def suivre(
    canal: str, lire_apres: LireApres, est_fini: EstFini, depuis: int = 0, attente_max: float = BATTEMENT_S
) -> AsyncIterator[tuple[int, dict[str, Any]] | None]:
    """Les événements après ``depuis`` (``(identifiant, événement)``), puis les suivants à mesure ; ``None`` = battement de
    cœur (rien de nouveau depuis ``attente_max``). S'arrête quand la source est finie ET relue jusqu'au bout."""
    courant = max(0, depuis)
    silence = 0.0
    async with _transport.abonner(canal) as abonne:  # abonné AVANT la première lecture : aucun réveil n'est perdu
        while True:
            lignes = await lire_apres(courant)
            for identifiant, evenement in lignes:
                courant = identifiant
                silence = 0.0
                yield identifiant, evenement
            if lignes:
                continue
            if await est_fini():
                if not await lire_apres(courant):
                    return
                continue
            debut = asyncio.get_running_loop().time()
            await abonne.attendre(min(attente_max, RELECTURE_MAX_S))
            silence += asyncio.get_running_loop().time() - debut
            if silence >= attente_max:
                silence = 0.0
                yield None


def ligne_sse(identifiant: int, evenement: dict[str, Any]) -> str:
    return f"id: {identifiant}\ndata: {json.dumps(evenement, ensure_ascii=False, default=str)}\n\n"


BATTEMENT_SSE = ": battement\n\n"


async def flux_sse(source: AsyncIterator[tuple[int, dict[str, Any]] | None]) -> AsyncIterator[str]:
    async for element in source:
        yield BATTEMENT_SSE if element is None else ligne_sse(*element)
