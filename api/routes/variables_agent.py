"""[.mark] U3 bis (E62) : le catalogue des variables d'un agent, pour les étiquettes.

- ``GET /mark/variables?agent=<id>``       le catalogue (clé, libellé, source, exemple), cloisonné par organisation ;
- ``GET /mark/variables/citations?cle=…``  les champs des agents de l'organisation qui citent cette clé (avant de renommer
  ou de supprimer une variable : l'écran les liste et propose de les réécrire).
Lecture seule : tout compte membre de l'organisation.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel

from api.db import db_client
from api.db.models import UserModel
from api.services.auth.depends import get_user_with_selected_organization
from api.services.variables_agent.catalogue import SOURCES, catalogue_de
from api.services.variables_agent.garde import champs_citant_dans_l_organisation

router = APIRouter(prefix="/mark", tags=["mark"])


class VariableCatalogue(BaseModel):
    cle: str
    libelle: str
    source: str
    exemple: str = ""
    description: str = ""


class CatalogueVariables(BaseModel):
    sources: list[str]
    variables: list[VariableCatalogue]


class ChampCitant(BaseModel):
    agent_id: int
    agent: str
    etape: str | None = None
    champ: str


class CitationsDeVariable(BaseModel):
    cle: str
    champs: list[ChampCitant]


@router.get("/variables", response_model=CatalogueVariables)
async def lire_le_catalogue(
    agent: int | None = Query(default=None),
    user: UserModel = Depends(get_user_with_selected_organization),
):
    organisation = user.selected_organization_id
    graphe = configs = essai = None
    if agent is not None:
        workflow = await db_client.get_workflow(agent, organization_id=organisation)
        if workflow is None:
            raise HTTPException(status_code=404, detail="Agent not found")
        brouillon = await db_client.get_draft_version(workflow.id)
        if brouillon is not None:
            graphe, configs = brouillon.workflow_json, brouillon.workflow_configurations
        essai = workflow.template_context_variables
    variables = await catalogue_de(organisation, graphe, configs, essai if isinstance(essai, dict) else None)
    return CatalogueVariables(sources=list(SOURCES), variables=[VariableCatalogue(**v.en_dict()) for v in variables])


@router.get("/variables/citations", response_model=CitationsDeVariable)
async def lire_les_citations(
    cle: str = Query(min_length=1, max_length=200),
    user: UserModel = Depends(get_user_with_selected_organization),
):
    champs = await champs_citant_dans_l_organisation(user.selected_organization_id, cle)
    return CitationsDeVariable(cle=cle, champs=[ChampCitant(**c) for c in champs])
