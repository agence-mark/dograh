"""[.mark] Chantier langwatch-et-fenetre-du-run, lot 1 : l'analyse d'un run pour sa fenêtre.

Une route en lecture, ``GET /workflow/{workflow_id}/runs/{run_id}/analyse``. Le run est lu dans
l'organisation de l'utilisateur, jamais par un identifiant passé en paramètre ; un run d'une autre
organisation, ou d'un autre agent que celui de l'adresse, rend 404. La définition jouée (portes,
champs de la fiche) est celle que le run porte, chargée avec lui.
"""

from fastapi import APIRouter, Depends, HTTPException

from api.db import db_client
from api.db.models import UserModel
from api.services.analyse_run.du_run import analyser_le_run
from api.services.apres_appel.envoi import fiche_de_fin_du_run
from api.services.auth.depends import get_user_with_selected_organization

router = APIRouter(prefix="/workflow", tags=["workflow-analyse-run"])


@router.get("/{workflow_id}/runs/{run_id}/analyse")
async def get_workflow_run_analyse(
    workflow_id: int,
    run_id: int,
    user: UserModel = Depends(get_user_with_selected_organization),
) -> dict:
    run = await db_client.get_workflow_run(
        run_id, organization_id=user.selected_organization_id
    )
    if run is None or run.workflow_id != workflow_id:
        raise HTTPException(status_code=404, detail="Workflow run not found")
    analyse = await analyser_le_run(run, user.selected_organization_id)
    # Lot 26 (M24) : la fiche de fin d'appel (T3), lue sur le run ; son résumé vient après l'envoi (étape « synthèse »), jamais inventé ici.
    return {**analyse, "fiche_de_fin": fiche_de_fin_du_run(run, analyse)}
