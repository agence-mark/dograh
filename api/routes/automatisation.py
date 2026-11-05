"""[.mark] Partie 3, N3b : les tests d'un agent lancés par une automatisation (n8n), avec la clé d'API de l'organisation.

- ``POST /automatisation/agents/{workflow_id}/tests/lancer``   joue la suite de l'agent (ou les tests nommés) et rend un résultat lisible ;
- ``GET  /automatisation/agents/{workflow_id}/tests/dernier``  relit les dernières exécutions rangées, sans rien jouer ni dépenser.

Permission ``tests.automatiser`` (liste fermée des clés : une clé n'a pas ``tests.jouer``, qui ouvrirait aussi les appels réels).
L'organisation est celle de la clé ou de la session, jamais celle du corps ; un agent d'une autre organisation est un 404. Même plafond
de rejeu et mêmes budgets du mois des rôles que l'écran. Le détail est dans ``services/builder/tests_agent/automatisation.py``.
"""

from __future__ import annotations

from typing import Any, Literal

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from api.db import db_client
from api.db.models import UserModel
from api.services.auth.depends import get_user_with_selected_organization
from api.services.builder.tests_agent import automatisation
from api.services.tests_rejouables.modele import ErreurTestRejouable

router = APIRouter(prefix="/automatisation", tags=["automatisation"])


class LancerLesTests(BaseModel):
    tests: list[str] | None = Field(default=None, max_length=100, description="Slugs or names of the tests to play; empty = the whole suite.")
    repetitions: int = Field(default=automatisation.REPETITIONS_PAR_DEFAUT, ge=1, le=5, description="Times each test is played.")


class UnTest(BaseModel):
    slug: str
    nom: str
    obligatoire: bool = False
    statut: str | None = None
    reussis: int | None = None
    total: int | None = None
    le: str | None = None
    version: int | None = None


class UnEchec(BaseModel):
    test: str
    nom: str | None = None
    obligatoire: bool = False
    critere: str | None = None
    raison: str | None = None
    replique: str | None = None


class ResultatDesTests(BaseModel):
    """What an automation reads: ``ok`` and ``statut`` first, then the counters, the tests and the failures."""

    agent_id: int
    ok: bool = Field(description="True only when the WHOLE suite was played and every test passed.")
    statut: Literal["ok", "echec", "incomplet", "plafond", "sans_test"]
    tests_total: int
    tests_reussis: int
    suite_complete: bool
    obligatoire_en_echec: bool
    version: int | None = None
    plafond: str | None = Field(default=None, description="The ceiling that stopped the run (replay ceiling or monthly budget of a role).")
    depense: dict[str, Any] | None = None
    message: str | None = None
    tests: list[UnTest]
    echecs: list[UnEchec]


async def _agent_ou_404(user: UserModel, workflow_id: int):
    workflow = await db_client.get_workflow(workflow_id, organization_id=user.selected_organization_id)
    if workflow is None:
        raise HTTPException(status_code=404, detail="Workflow not found")
    return workflow


@router.post("/agents/{workflow_id}/tests/lancer", response_model=ResultatDesTests)
async def lancer_les_tests(
    workflow_id: int, corps: LancerLesTests | None = None, user: UserModel = Depends(get_user_with_selected_organization)
):
    """Plays the agent's tests and answers in one JSON an automation can branch on (``ok``, ``statut``)."""
    corps = corps or LancerLesTests()
    workflow = await _agent_ou_404(user, workflow_id)
    try:
        return await automatisation.lancer(user, workflow, tests=corps.tests, repetitions=corps.repetitions)
    except automatisation.DejaEnCours:
        raise HTTPException(status_code=409, detail="A replay of this agent's tests is already running.") from None
    except automatisation.TropLong:
        raise HTTPException(
            status_code=504, detail="The replay is too long: read what was finished with GET .../tests/dernier."
        ) from None
    except ErreurTestRejouable as erreur:
        raise HTTPException(status_code=422, detail=str(erreur)) from None


@router.get("/agents/{workflow_id}/tests/dernier", response_model=ResultatDesTests)
async def dernier_resultat_des_tests(workflow_id: int, user: UserModel = Depends(get_user_with_selected_organization)):
    """The last stored run of each test of the agent; plays nothing and spends nothing."""
    await _agent_ou_404(user, workflow_id)
    return await automatisation.dernier(user.selected_organization_id, workflow_id)
