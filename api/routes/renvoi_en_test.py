"""[.mark] Lot D (chantier fiabilite-fiche-et-renvoi) : la décision du testeur sur un renvoi d'appel.

Hors téléphonie (clavier, casque), l'outil de transfert attend « Accepter le renvoi d'appel » ou
« Refuser le renvoi d'appel » (``api.services.workflow.renvoi_en_test``). Ces deux routes disent à
la page si un renvoi attend, et portent le clic. Le run est toujours lu dans l'organisation de
l'utilisateur.
"""

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from api.db import db_client
from api.db.models import UserModel
from api.services.auth.depends import get_user_with_selected_organization
from api.services.workflow.renvoi_en_test import (
    donner_la_decision,
    est_un_essai,
    renvoi_en_attente,
)

router = APIRouter(prefix="/workflow", tags=["workflow-renvoi-en-test"])


class DecisionDeRenvoi(BaseModel):
    accepte: bool


class EtatDuRenvoi(BaseModel):
    en_attente: bool


async def _run_de_test(workflow_id: int, run_id: int, user: UserModel):
    run = await db_client.get_workflow_run(
        run_id, organization_id=user.selected_organization_id
    )
    # Ni un run d'une autre organisation, ni un appel du widget public (relecture du 01/10).
    if run is None or run.workflow_id != workflow_id or not await est_un_essai(run):
        raise HTTPException(status_code=404, detail="Run not found")
    return run


@router.get("/{workflow_id}/runs/{run_id}/renvoi-en-test", response_model=EtatDuRenvoi)
async def etat_du_renvoi(
    workflow_id: int,
    run_id: int,
    user: UserModel = Depends(get_user_with_selected_organization),
) -> EtatDuRenvoi:
    await _run_de_test(workflow_id, run_id, user)
    return EtatDuRenvoi(en_attente=await renvoi_en_attente(run_id))


@router.post("/{workflow_id}/runs/{run_id}/renvoi-en-test", response_model=EtatDuRenvoi)
async def decider_du_renvoi(
    workflow_id: int,
    run_id: int,
    decision: DecisionDeRenvoi,
    user: UserModel = Depends(get_user_with_selected_organization),
) -> EtatDuRenvoi:
    await _run_de_test(workflow_id, run_id, user)
    if not await donner_la_decision(run_id, decision.accepte):
        # Clic après le délai, ou sur un appel sans renvoi en cours.
        raise HTTPException(
            status_code=409, detail="No transfer waiting for a decision"
        )
    return EtatDuRenvoi(en_attente=False)
