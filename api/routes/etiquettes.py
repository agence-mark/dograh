"""[.mark] Les étiquettes des agents (U3, E30).

Lire = membre de l'organisation de l'adresse ; poser = ``agents.modifier`` (registre des routes). Tout passe par
l'organisation du compte (``get_user``) : l'agent est relu dans CETTE organisation, jamais par son seul identifiant.
"""

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from api.db import db_client
from api.db.models import UserModel
from api.services.auth.depends import get_user
from api.services.etiquettes import stockage

router = APIRouter(prefix="/etiquettes", tags=["etiquettes"])


class EtiquetteResponse(BaseModel):
    nom: str
    nb_agents: int


class EtiquettesResponse(BaseModel):
    etiquettes: list[EtiquetteResponse]
    par_agent: dict[int, list[str]]


class PoserEtiquettesRequest(BaseModel):
    etiquettes: list[str] = Field(default_factory=list, max_length=stockage.PAR_AGENT_MAX * 2)


@router.get("", response_model=EtiquettesResponse)
async def lire_les_etiquettes(user: UserModel = Depends(get_user)) -> EtiquettesResponse:
    return EtiquettesResponse(**await stockage.lire(user.selected_organization_id))


@router.put("/agents/{workflow_id}", response_model=EtiquettesResponse)
async def poser_les_etiquettes(
    workflow_id: int, requete: PoserEtiquettesRequest, user: UserModel = Depends(get_user)
) -> EtiquettesResponse:
    """Remplace les étiquettes de l'agent ; une liste vide les retire toutes."""
    organisation_id = user.selected_organization_id
    agent = await db_client.get_workflow(workflow_id, organization_id=organisation_id)
    if agent is None:
        raise HTTPException(status_code=404, detail="Agent not found")
    try:
        return EtiquettesResponse(**await stockage.poser(organisation_id, workflow_id, requete.etiquettes))
    except stockage.ErreurEtiquette as erreur:
        raise HTTPException(status_code=422, detail=str(erreur)) from None
