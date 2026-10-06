"""[.mark] Le direct d'un appel simulé (chantier direct-et-passe-muette, lot A, P1 à P5, P14).

Un appel simulé n'a pas de navigateur au bout : personne n'enregistrait de canal pour son run, et ses
événements (transcriptions de l'appelant, texte de l'agent, outils, étapes, erreurs) n'arrivaient à
l'écran qu'à la fin. Ici, avant que le pipeline démarre, un canal est enregistré pour le run dans le
registre de Dograh (``ws_sender_registry``) : chaque événement est horodaté comme dans le journal du
run et ajouté à une liste Redis propre au run, que l'écran relit chaque seconde (route
``GET /appel-simule/runs/{run}/direct``), quel que soit le processus qui joue l'appel.

Ce qui doit tenir :
- la liste est bornée (``MAX_EVENEMENTS``) et s'efface d'elle-même (``DUREE_DE_VIE_S`` après le
  dernier événement) ; la transcription du run, elle, s'écrit comme avant à la fin de l'appel ;
- le direct ne contient que ce que le journal du run contient déjà : aucune clé ;
- un direct qui échoue ne touche jamais l'appel (R1) : l'erreur s'écrit au journal, l'appel continue,
  et l'écran dit « direct indisponible ».
"""

from __future__ import annotations

import json
from datetime import UTC, datetime
from typing import Any, Awaitable, Callable

import redis.asyncio as aioredis
from loguru import logger

from api.constants import REDIS_URL
from api.services.pipecat.realtime_feedback_events import stamp_realtime_feedback_event
from api.services.pipecat.ws_sender_registry import (
    register_ws_sender,
    unregister_ws_sender,
)

MAX_EVENEMENTS = 2000
DUREE_DE_VIE_S = 2 * 3600
TYPE_FIN = "mark-direct-fin"
TYPE_TRONQUE = "mark-direct-tronque"

_redis: aioredis.Redis | None = None


async def _client_redis() -> aioredis.Redis:
    global _redis
    if _redis is None:
        _redis = await aioredis.from_url(REDIS_URL, decode_responses=True)
    return _redis


def cle_du_direct(workflow_run_id: int) -> str:
    return f"mark:appel-simule:direct:{workflow_run_id}"


async def _ajouter(workflow_run_id: int, evenement: dict) -> None:
    redis = await _client_redis()
    cle = cle_du_direct(workflow_run_id)
    if evenement.get("type") != TYPE_FIN:
        # La fin s'écrit toujours ; le reste s'arrête à la borne, qu'un marqueur signale.
        longueur = await redis.llen(cle)
        if longueur >= MAX_EVENEMENTS:
            return
        if longueur == MAX_EVENEMENTS - 1:
            evenement = {"type": TYPE_TRONQUE, "payload": {"max": MAX_EVENEMENTS}}
    await redis.rpush(cle, json.dumps(evenement, default=str))
    await redis.expire(cle, DUREE_DE_VIE_S)


def canal_du_direct(workflow_run_id: int) -> Callable[[dict], Awaitable[None]]:
    """Le canal que le pipeline appelle pour chaque événement de l'appel simulé."""

    async def envoyer(message: dict) -> None:
        try:
            evenement = stamp_realtime_feedback_event(
                dict(message),
                timestamp=datetime.now(UTC).isoformat(timespec="milliseconds"),
                turn=None,
                node_id=message.get("node_id"),
                node_name=message.get("node_name"),
            )
            await _ajouter(workflow_run_id, evenement)
        except Exception as erreur:  # noqa: BLE001
            # R1 : le direct ne casse jamais l'appel ; il manquera à l'écran, qui le dira.
            logger.error(
                f"[.mark] Live view of simulated run {workflow_run_id} failed: {erreur!r}"
            )

    return envoyer


async def ouvrir_le_direct(workflow_run_id: int) -> None:
    """Avant le pipeline : le canal du run pointe vers Redis, la liste repart de zéro."""
    try:
        await (await _client_redis()).delete(cle_du_direct(workflow_run_id))
    except Exception as erreur:  # noqa: BLE001
        logger.error(
            f"[.mark] Live view of simulated run {workflow_run_id} not reset: {erreur!r}"
        )
    register_ws_sender(workflow_run_id, canal_du_direct(workflow_run_id))


async def fermer_le_direct(workflow_run_id: int) -> None:
    """Après l'appel, quoi qu'il arrive : le canal se retire et la fin s'écrit pour l'écran."""
    unregister_ws_sender(workflow_run_id)
    try:
        await _ajouter(workflow_run_id, {"type": TYPE_FIN, "payload": {}})
    except Exception as erreur:  # noqa: BLE001
        logger.error(
            f"[.mark] Live view of simulated run {workflow_run_id} not closed: {erreur!r}"
        )


async def lire_le_direct(workflow_run_id: int, depuis: int) -> dict[str, Any]:
    """Les événements à partir du ``depuis``-ième, l'index du suivant, et si l'appel est fini."""
    redis = await _client_redis()
    depuis = max(0, depuis)
    bruts = await redis.lrange(cle_du_direct(workflow_run_id), depuis, -1)
    evenements = [json.loads(b) for b in bruts]
    fini = any(e.get("type") == TYPE_FIN for e in evenements)
    return {
        "evenements": [e for e in evenements if e.get("type") != TYPE_FIN],
        "suivant": depuis + len(evenements),
        "fini": fini,
    }
