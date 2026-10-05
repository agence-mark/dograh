"""[.mark] Chantier langwatch-et-fenetre-du-run, lot 1 : l'analyse d'un run pour sa fenêtre.

Une route en lecture, ``GET /workflow/{workflow_id}/runs/{run_id}/analyse``. Le run est lu dans
l'organisation de l'utilisateur, jamais par un identifiant passé en paramètre ; un run d'une autre
organisation, ou d'un autre agent que celui de l'adresse, rend 404. La définition jouée (portes,
champs de la fiche) est celle que le run porte, chargée avec lui.
"""

from fastapi import APIRouter, Depends, HTTPException

from api.db import db_client
from api.db.models import UserModel
from api.services.analyse_run.analyse import analyser_run
from api.services.auth.depends import get_user_with_selected_organization
from api.services.workflow.fiche_au_fil_de_leau import CLE_CHAMPS
from api.services.workflow.workflow_graph import transition_tool_name

router = APIRouter(prefix="/workflow", tags=["workflow-analyse-run"])


def _portes(definition) -> set[str] | None:
    if definition is None:
        return None
    aretes = (definition.workflow_json or {}).get("edges") or []
    return {
        transition_tool_name(label)
        for arete in aretes
        if isinstance(arete, dict)
        and isinstance(label := (arete.get("data") or {}).get("label"), str)
        and label
    }


def _champs_fiche(definition) -> list[str] | None:
    if definition is None:
        return None
    champs = (definition.workflow_configurations or {}).get(CLE_CHAMPS)
    if not isinstance(champs, list):
        return None
    return [
        c["nom"]
        for c in champs
        if isinstance(c, dict) and isinstance(c.get("nom"), str)
    ]


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
    definition = run.definition
    return analyser_run(
        {
            "id": run.id,
            "workflow_id": run.workflow_id,
            "definition_id": run.definition_id,
            "mode": run.mode,
            "usage_info": run.usage_info,
            "initial_context": run.initial_context,
            "gathered_context": run.gathered_context,
            "logs": run.logs,
        },
        portes=_portes(definition),
        champs_fiche=_champs_fiche(definition),
    )
