"""L'entrée audio des appels simulés (.mark, chantier langwatch-et-fenetre-du-run, lot 3, L8, L9, L19).

Un appel simulé est un run ordinaire de mode ``simulated``. Le simulateur (LangWatch Scenario,
dans son propre environnement Python, L19) s'y branche par un WebSocket au protocole Twilio Media
Streams, sur ``/appel-simule/ws/{run}/{jeton}``.

Le jeton :
- est **aléatoire et propre au run** (``secrets.token_urlsafe``), jamais dérivé d'un identifiant ;
- n'est stocké que par son **empreinte** (SHA-256) dans ``run.extra`` (jamais dans le contexte de
  l'appel, dont les clés deviennent des variables lisibles par les prompts) ;
- sert **une seule fois** : le run doit être à l'état « initialized », et passe à « running » dès
  qu'il est accepté ; un second branchement est refusé.
"""

from __future__ import annotations

import hashlib
import hmac
import secrets
import uuid
from typing import Any

import redis.asyncio as aioredis

from api.constants import REDIS_URL
from api.db import db_client
from api.enums import CallType, WorkflowRunMode, WorkflowRunState
from api.services.workflow.run_creation import prepare_workflow_run_inputs

CLE_EXTRA = "mark_simulation"
CHEMIN_WS = "/api/v1/appel-simule/ws"


def empreinte(jeton: str) -> str:
    return hashlib.sha256(jeton.encode()).hexdigest()


def jeton_valide(run: Any, jeton: str | None) -> bool:
    """Comparaison à temps constant de l'empreinte du jeton présenté et de celle du run."""
    if not jeton:
        return False
    attendue = ((getattr(run, "extra", None) or {}).get(CLE_EXTRA) or {}).get(
        "jeton_sha256"
    )
    if not isinstance(attendue, str):
        return False
    return hmac.compare_digest(attendue, empreinte(jeton))


def run_branchable(run: Any) -> bool:
    """Un run simulé, pas encore joué : condition de l'usage unique du jeton."""
    return (
        run is not None
        and getattr(run, "mode", None) == WorkflowRunMode.SIMULATED.value
        and getattr(run, "state", None) == WorkflowRunState.INITIALIZED.value
    )


async def creer_run_simule(
    workflow: Any,
    *,
    user_id: int,
    organization_id: int,
    simulation: dict,
    use_draft: bool = True,
) -> tuple[Any, str]:
    """Crée le run d'un appel simulé et rend ``(run, jeton)``. ``simulation`` décrit la série et le
    scénario joué ; il est rangé avec l'empreinte du jeton, hors du contexte de l'appel.

    Comme les onglets voisins de « Test Agent » (``routes/workflow.py``) : le BROUILLON de l'agent
    et ses variables de modèle. Sinon, une série jouée pour comparer une option basculée dans le
    brouillon jouerait deux fois la version publiée (revue du 05/10)."""
    jeton = secrets.token_urlsafe(32)
    entrees = await prepare_workflow_run_inputs(
        db_client, workflow, use_draft=use_draft, include_template_context=True
    )
    numero = int(uuid.uuid4().hex[:8], 16) % 100000000
    run = await db_client.create_workflow_run(
        f"WR-SIM-{numero:08d}",
        workflow.id,
        WorkflowRunMode.SIMULATED.value,
        user_id,
        call_type=CallType.INBOUND,
        initial_context={
            **(entrees.initial_context or {}),
            "provider": WorkflowRunMode.SIMULATED.value,
            "direction": "inbound",
        },
        organization_id=organization_id,
        definition_id=entrees.definition_id,
        use_draft=entrees.use_draft,
    )
    await db_client.update_workflow_run(
        run_id=run.id,
        extra={CLE_EXTRA: {**simulation, "jeton_sha256": empreinte(jeton)}},
    )
    return run, jeton


def _cle_branchement(run_id: int) -> str:
    return f"mark:appel-simule:branche:{run_id}"


async def reserver_le_branchement(run_id: int) -> bool:
    """L'usage unique, atomique : de deux branchements simultanés avec le bon jeton, un seul
    obtient le run (``SET NX``), avant même la lecture de son état (revue du 05/10)."""
    redis = await aioredis.from_url(REDIS_URL, decode_responses=True)
    try:
        return bool(
            await redis.set(_cle_branchement(run_id), "1", nx=True, ex=24 * 3600)
        )
    finally:
        await redis.aclose()


def adresse_ws(base_ws: str, run_id: int, jeton: str) -> str:
    """``wss://api…`` + chemin : le jeton est dans le CHEMIN, comme pour Twilio (les paramètres
    d'adresse ne sont pas transmis partout)."""
    return f"{base_ws.rstrip('/')}{CHEMIN_WS}/{run_id}/{jeton}"
