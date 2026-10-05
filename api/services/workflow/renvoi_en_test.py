"""[.mark] Lot D (chantier fiabilite-fiche-et-renvoi, 01/10/2026) : la simulation du renvoi d'appel en test.

Hors téléphonie (clavier, casque), l'outil de transfert de Dograh répondait « échec » d'office :
le renvoi ne s'essayait nulle part avant la production, et l'étape transfert improvisait
(« Vous êtes toujours en ligne ? »). En test, l'outil attend désormais la décision du testeur,
donnée par deux boutons, « Accepter le renvoi d'appel » et « Refuser le renvoi d'appel », et
rend à l'agent le même résultat que la téléphonie : accepté = l'appel est passé, l'agent se
retire ; refusé, ou sans réponse avant le délai de l'outil (D3) = échec, l'agent reprend.

⛔ Rien de propre à un client ni à un métier : un mécanisme de test de l'outil de transfert.
En production (téléphonie), rien ne change.

La décision passe par Redis, comme les événements de transfert de la téléphonie : la page qui
clique et le moteur qui attend ne sont pas forcément dans le même processus.
"""

from __future__ import annotations

import asyncio

import redis.asyncio as aioredis

from api.constants import REDIS_URL
from api.db import db_client
from api.enums import WorkflowRunMode

# Les modes où l'outil de transfert ne peut pas joindre de téléphonie. L'appel simulé
# (langwatch-et-fenetre-du-run, lot 3) en est : un renvoi n'y compose jamais de vrai numéro.
MODES_DE_TEST = frozenset(
    {
        WorkflowRunMode.TEXTCHAT.value,
        WorkflowRunMode.WEBRTC.value,
        WorkflowRunMode.SMALLWEBRTC.value,
        WorkflowRunMode.SIMULATED.value,
    }
)


async def est_un_essai(workflow_run) -> bool:
    """Un essai lancé depuis l'écran (clavier, testeur vocal), jamais un visiteur du
    widget public : lui ne peut pas cliquer, et un membre de l'organisation ne doit
    pas pouvoir décider à sa place (relecture du 01/10)."""
    if workflow_run is None or workflow_run.mode not in MODES_DE_TEST:
        return False
    # Un appel simulé n'a jamais de vraie téléphonie : essai d'office, sans dépendre
    # d'aucune autre lecture (revue du 05/10, défense en profondeur).
    if workflow_run.mode == WorkflowRunMode.SIMULATED.value:
        return True
    return not await db_client.run_vient_du_widget(workflow_run.id)


ACCEPTE = "accepte"
REFUSE = "refuse"

_INTERVALLE = 0.25

_client: aioredis.Redis | None = None


async def _redis() -> aioredis.Redis:
    global _client
    if _client is None:
        _client = await aioredis.from_url(REDIS_URL, decode_responses=True)
    return _client


def _cle_attente(run_id: int) -> str:
    return f"mark:renvoi-en-test:attente:{run_id}"


def _cle_decision(run_id: int) -> str:
    return f"mark:renvoi-en-test:decision:{run_id}"


async def attendre_la_decision(run_id: int, delai_secondes: float) -> str | None:
    """Ouvre l'attente de ce run, puis rend ``ACCEPTE``, ``REFUSE``, ou None au délai."""
    redis = await _redis()
    await redis.delete(_cle_decision(run_id))
    await redis.set(_cle_attente(run_id), "1", ex=max(1, int(delai_secondes) + 5))
    loop = asyncio.get_running_loop()
    fin = loop.time() + max(0.0, delai_secondes)
    try:
        while loop.time() < fin:
            decision = await redis.get(_cle_decision(run_id))
            if decision in (ACCEPTE, REFUSE):
                return decision
            await asyncio.sleep(_INTERVALLE)
        return None
    finally:
        await redis.delete(_cle_attente(run_id), _cle_decision(run_id))


async def renvoi_en_attente(run_id: int) -> bool:
    """Un renvoi attend-il la décision du testeur sur ce run ?"""
    return bool(await (await _redis()).exists(_cle_attente(run_id)))


async def donner_la_decision(run_id: int, accepte: bool) -> bool:
    """Enregistre la décision ; False quand aucun renvoi n'attend (clic tardif)."""
    redis = await _redis()
    if not await redis.exists(_cle_attente(run_id)):
        return False
    await redis.set(_cle_decision(run_id), ACCEPTE if accepte else REFUSE, ex=60)
    return True
