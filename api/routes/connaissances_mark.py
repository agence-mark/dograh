"""[.mark] Partie 3, lot 14 (SE-21, K-2) : ce que l'écran « Connaissances » sait d'un document, en plus de l'amont.

``GET /knowledge-base/documents/{uuid}/utilisation`` : combien d'agents de l'organisation lisent ce document (dans la
dernière version de chaque agent : ``document_uuids`` de ses étapes) et lesquels. Jamais un chiffre inventé : compté sur les
agents de l'organisation de l'appelant, un document d'une autre organisation répond 404 comme absent. Les permissions
viennent du registre des routes (``/knowledge-base`` : lecture = tout membre).
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from api.db import db_client
from api.services.auth.depends import get_user

router = APIRouter(prefix="/knowledge-base", tags=["knowledge-base"])

AGENTS_MONTRES = 10


class AgentQuiLit(BaseModel):
    workflow_id: int
    nom: str


class UtilisationDocument(BaseModel):
    nombre: int
    agents: list[AgentQuiLit] = Field(default_factory=list, description="The first agents, by name (at most 10).")


@router.get("/documents/{document_uuid}/utilisation", response_model=UtilisationDocument)
async def utilisation_d_un_document(document_uuid: str, user=Depends(get_user)) -> UtilisationDocument:
    organisation = user.selected_organization_id
    if not organisation:
        raise HTTPException(status_code=400, detail="No organization selected for the user")
    if not await db_client.get_document_by_uuid(document_uuid=document_uuid, organization_id=organisation):
        raise HTTPException(status_code=404, detail="Document not found")
    lisent: list[AgentQuiLit] = []
    for agent in await db_client.get_all_workflows(organization_id=organisation):
        definition = getattr(agent.current_definition, "workflow_json", None) or {}
        if any(document_uuid in ((n.get("data") or {}).get("document_uuids") or []) for n in definition.get("nodes", [])):
            lisent.append(AgentQuiLit(workflow_id=agent.id, nom=agent.name))
    lisent.sort(key=lambda a: a.nom.casefold())
    return UtilisationDocument(nombre=len(lisent), agents=lisent[:AGENTS_MONTRES])
