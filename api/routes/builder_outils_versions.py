"""[.mark] Partie 3, SA-L3d (décision 21) : les versions des outils (``/builder/outils``).

- ``GET /builder/outils/{outil}/versions``                    les versions d'un outil et qui utilise quelle version ;
- ``GET /builder/outils/agent/{agent}``                       les outils de l'agent ouvert : version épinglée et version courante ;
- ``PUT /builder/outils/agent/{agent}/version``               « Passer à la v5 » : écrit dans le BROUILLON de l'agent ouvert.

Une version d'agent joue toujours la version d'outil qu'elle a figée ; elle ne suit jamais seule. Tout est lu et écrit AVEC l'organisation
de la personne (un outil ou un agent d'une autre organisation est un 404). Le passage est un geste de modification d'agent, journalisé.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException

from api.db import db_client
from api.db.models import UserModel
from api.db.outils_versions_client import ErreurOutilVersion
from api.schemas.outils_versions import (
    OutilsDeLAgent,
    PassageDeVersion,
    VersionsDUnOutil,
)
from api.services.auth.depends import get_user_with_selected_organization

router = APIRouter(tags=["builder-outils-versions"])

CODES_HTTP = {"introuvable": 404, "pas_utilise": 409}


def _http(erreur: ErreurOutilVersion) -> HTTPException:
    return HTTPException(status_code=CODES_HTTP.get(erreur.code, 422), detail=str(erreur))


@router.get("/builder/outils/agent/{workflow_id}", response_model=OutilsDeLAgent)
async def lire_les_outils_de_l_agent(workflow_id: int, user: UserModel = Depends(get_user_with_selected_organization)):
    try:
        return await db_client.outils_epingles_de_l_agent(user.selected_organization_id, workflow_id)
    except ErreurOutilVersion as erreur:
        raise _http(erreur) from None


@router.put("/builder/outils/agent/{workflow_id}/version")
async def passer_a_une_version(
    workflow_id: int, corps: PassageDeVersion, user: UserModel = Depends(get_user_with_selected_organization)
):
    from api.services.equipe_mark.acces import journaliser

    agent = await db_client.get_workflow(workflow_id, organization_id=user.selected_organization_id)
    if agent is None:
        raise HTTPException(status_code=404, detail="Workflow not found")
    try:
        fait = await db_client.passer_un_outil_a_la_version(
            user.selected_organization_id, workflow_id, corps.tool_uuid, corps.version
        )
    except ErreurOutilVersion as erreur:
        raise _http(erreur) from None
    await journaliser(
        user,
        "agents.outil_version_changee",
        user.selected_organization_id,
        {"agent": workflow_id, "outil": corps.tool_uuid, "version": corps.version},
    )
    return {"ok": True, **fait}


@router.get("/builder/outils/{tool_uuid}/versions", response_model=VersionsDUnOutil)
async def lire_les_versions_d_un_outil(tool_uuid: str, user: UserModel = Depends(get_user_with_selected_organization)):
    organisation = user.selected_organization_id
    try:
        outil, versions = await db_client.versions_d_un_outil(organisation, tool_uuid)
        usage = await db_client.usage_d_un_outil(organisation, tool_uuid)
    except ErreurOutilVersion as erreur:
        raise _http(erreur) from None
    courante = outil.version_courante or 1
    en_retard = {u["workflow_id"] for u in usage if u["en_ligne"] and (u["version_outil"] or courante) < courante}
    return {
        "tool_uuid": outil.tool_uuid,
        "nom": outil.name,
        "courante": courante,
        "versions": [
            {"version": v.version, "nom": v.name, "cree_le": v.created_at, "courante": v.version == courante} for v in versions
        ],
        "usage": usage,
        "agents_en_retard": len(en_retard),
    }
