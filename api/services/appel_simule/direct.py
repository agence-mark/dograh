"""[.mark] Le direct d'un appel simulé (chantier direct-et-passe-muette, lot A, P1 à P5, P14).

Un appel simulé n'a pas de navigateur au bout : personne n'enregistrait de canal pour son run, et ses
événements (transcriptions de l'appelant, texte de l'agent, outils, étapes, erreurs) n'arrivaient à
l'écran qu'à la fin. Ici, avant que le pipeline démarre, un canal est enregistré pour le run dans le
registre de Dograh (``ws_sender_registry``) : chaque événement est horodaté comme dans le journal du
run et ajouté à une liste Redis propre au run, que l'écran relit chaque seconde (route
``GET /appel-simule/runs/{run}/direct``), quel que soit le processus qui joue l'appel.

Ce qui doit tenir :
- **le canal ne fait jamais attendre l'appel** (R1, revue du lot A) : il dépose l'événement dans une
  file en mémoire et rend la main ; une seule tâche par run écrit dans Redis, dans l'ordre, chaque
  écriture bornée dans le temps. Un Redis lent ou figé ne fige ni un changement d'étape, ni la fin
  du run, ni l'horodatage du journal enregistré (que l'observateur de Dograh écrit après le canal) ;
- la liste est bornée (``MAX_EVENEMENTS``, un marqueur le dit à l'écran) et s'efface d'elle-même
  (``DUREE_DE_VIE_S`` après la dernière écriture) ; la transcription du run s'écrit comme avant à la
  fin de l'appel ;
- le direct porte **le même contenu que le journal du run, rien de plus** (arguments et résultats
  d'outils compris), lisible par la seule organisation du run ; il ne vit que deux heures dans Redis ;
- un direct en panne s'écrit au journal d'erreur ; l'appel continue et l'écran dit « direct
  indisponible ».
"""

from __future__ import annotations

import asyncio
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
DELAI_ECRITURE_S = 1.0
DELAI_FERMETURE_S = 3.0
TYPE_FIN = "mark-direct-fin"
TYPE_TRONQUE = "mark-direct-tronque"

_redis: aioredis.Redis | None = None


async def _client_redis() -> aioredis.Redis:
    global _redis
    if _redis is None:
        _redis = await aioredis.from_url(
            REDIS_URL,
            decode_responses=True,
            socket_timeout=DELAI_ECRITURE_S,
            socket_connect_timeout=DELAI_ECRITURE_S,
        )
    return _redis


def cle_du_direct(workflow_run_id: int) -> str:
    return f"mark:appel-simule:direct:{workflow_run_id}"


class _Direct:
    """La file d'un run et sa tâche d'écriture, seule à parler à Redis pour ce run."""

    def __init__(self, workflow_run_id: int):
        self.run = workflow_run_id
        # Bornée par le compte des dépôts, pas par la file : la fin n'est jamais refusée.
        self.file: asyncio.Queue[dict] = asyncio.Queue()
        self.deposes = 0
        self.ecrits = 0
        self.tache = asyncio.create_task(self._ecrire())

    def deposer(self, evenement: dict) -> None:
        if evenement.get("type") != TYPE_FIN:
            if self.deposes >= MAX_EVENEMENTS:
                return  # La borne est atteinte : le marqueur est déjà dans la file.
            self.deposes += 1
        self.file.put_nowait(evenement)

    async def _ecrire(self) -> None:
        cle = cle_du_direct(self.run)
        try:
            redis = await _client_redis()
            await asyncio.wait_for(redis.delete(cle), DELAI_ECRITURE_S)
        except Exception as erreur:  # noqa: BLE001
            logger.error(
                f"[.mark] Live view of simulated run {self.run} not reset: {erreur!r}"
            )
        while True:
            evenement = await self.file.get()
            try:
                if evenement.get("type") != TYPE_FIN:
                    if self.ecrits >= MAX_EVENEMENTS:
                        continue
                    if self.ecrits == MAX_EVENEMENTS - 1:
                        evenement = {
                            "type": TYPE_TRONQUE,
                            "payload": {"max": MAX_EVENEMENTS},
                        }
                redis = await _client_redis()
                # Un seul aller-retour : l'ajout et la durée de vie ensemble.
                transaction = redis.pipeline(transaction=True)
                transaction.rpush(cle, json.dumps(evenement, default=str))
                transaction.expire(cle, DUREE_DE_VIE_S)
                await asyncio.wait_for(transaction.execute(), DELAI_ECRITURE_S)
                self.ecrits += 1
            except Exception as erreur:  # noqa: BLE001
                logger.error(
                    f"[.mark] Live view of simulated run {self.run} failed: {erreur!r}"
                )
            finally:
                self.file.task_done()
            if evenement.get("type") == TYPE_FIN:
                return


_directs: dict[int, _Direct] = {}


def canal_du_direct(workflow_run_id: int) -> Callable[[dict], Awaitable[None]]:
    """Le canal que le pipeline appelle pour chaque événement : il dépose et rend la main."""

    async def envoyer(message: dict) -> None:
        try:
            direct = _directs.get(workflow_run_id)
            if direct is None:
                return
            direct.deposer(
                stamp_realtime_feedback_event(
                    dict(message),
                    timestamp=datetime.now(UTC).isoformat(timespec="milliseconds"),
                    turn=None,
                    node_id=message.get("node_id"),
                    node_name=message.get("node_name"),
                )
            )
        except Exception as erreur:  # noqa: BLE001
            # R1 : le direct ne casse jamais l'appel ; il manquera à l'écran, qui le dira.
            logger.error(
                f"[.mark] Live view of simulated run {workflow_run_id} failed: {erreur!r}"
            )

    return envoyer


async def ouvrir_le_direct(workflow_run_id: int) -> None:
    """Avant le pipeline : la file et sa tâche d'écriture, et le canal du run dans le registre.
    Ne parle pas à Redis ici : c'est la tâche d'écriture qui remet la liste à zéro."""
    _directs[workflow_run_id] = _Direct(workflow_run_id)
    register_ws_sender(workflow_run_id, canal_du_direct(workflow_run_id))


async def fermer_le_direct(workflow_run_id: int) -> None:
    """Après l'appel, quoi qu'il arrive : le canal se retire, la fin s'écrit, et la file se vide
    dans un délai borné (au-delà, la tâche est abandonnée : l'écran conclut par l'état du run)."""
    unregister_ws_sender(workflow_run_id)
    direct = _directs.pop(workflow_run_id, None)
    if direct is None:
        return
    direct.deposer({"type": TYPE_FIN, "payload": {}})
    try:
        await asyncio.wait_for(asyncio.shield(direct.tache), DELAI_FERMETURE_S)
    except Exception as erreur:  # noqa: BLE001
        direct.tache.cancel()
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
