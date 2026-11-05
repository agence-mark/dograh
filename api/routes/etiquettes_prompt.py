"""[.mark] Lots 8 et 22 : les étiquettes d'objets des prompts (outils, étapes, agents, équipe, documents, phrases, blocs).

- ``GET  /mark/etiquettes-prompt?agent=<id>``                 le catalogue des objets citables et les étiquettes en erreur du brouillon ;
- ``GET  /mark/etiquettes-prompt/utilise-dans?cle=…``         les prompts des agents de l'organisation qui citent cet objet ;
- ``POST /mark/etiquettes-prompt/{agent}/corriger``          la correction en un clic, écrite dans le BROUILLON.

Lire = membre de l'organisation ; corriger = ``agents.modifier`` (registre des routes). Tout est lu AVEC l'organisation de
l'utilisateur : un agent d'une autre organisation est un 404, un objet d'une autre organisation n'est jamais au catalogue.
"""

from __future__ import annotations

from typing import Any, Literal

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, ConfigDict, Field

from api.db import db_client
from api.db.models import UserModel
from api.services.auth.depends import get_user_with_selected_organization
from api.services.etiquettes_prompt import catalogue as cat
from api.services.etiquettes_prompt import corrections
from api.services.etiquettes_prompt.familles import FAMILLES

router = APIRouter(prefix="/mark", tags=["mark"])


class ObjetCitableVu(BaseModel):
    cle: str
    famille: str
    libelle: str
    statut: str
    resume: str = ""
    rendu: str = ""
    lignes: list[list[str]] = Field(default_factory=list)
    etapes: list[str] = Field(default_factory=list)
    version: int | None = None
    versions: list[dict[str, Any]] = Field(default_factory=list)


class CorrectionVue(BaseModel):
    type: str
    cle: str
    libelle: str
    champ: str | None = None
    noeud_id: str | None = None
    version: int | None = None


class ProblemeVu(BaseModel):
    cle: str
    famille: str
    motif: str
    message: str
    champ: str
    noeud_id: str | None = None
    etape: str | None = None
    bloquant: bool = True
    corrections: list[CorrectionVue] = Field(default_factory=list)


class CatalogueEtiquettes(BaseModel):
    familles: list[str]
    objets: list[ObjetCitableVu]
    problemes: list[ProblemeVu]
    illisibles: list[str] = Field(default_factory=list)


class Citation(BaseModel):
    agent_id: int
    agent: str
    noeud_id: str | None = None
    etape: str | None = None
    champ: str
    cle: str
    version: int | None = None


class UtiliseDans(BaseModel):
    cle: str
    citations: list[Citation]


class CorrigerEtiquette(BaseModel):
    model_config = ConfigDict(extra="forbid")
    type: Literal["retirer", "rattacher", "suivre", "passer_version"]
    cle: str = Field(min_length=3, max_length=300)
    champ: str | None = Field(default=None, max_length=300)
    noeud_id: str | None = Field(default=None, max_length=200)
    version: int | None = Field(default=None, ge=1, le=9999)


class Diagnostic(BaseModel):
    problemes: list[ProblemeVu]


async def _agent_ou_404(user: UserModel, workflow_id: int):
    workflow = await db_client.get_workflow(workflow_id, organization_id=user.selected_organization_id)
    if workflow is None:
        raise HTTPException(status_code=404, detail="Workflow not found")
    return workflow


@router.get("/etiquettes-prompt", response_model=CatalogueEtiquettes)
async def lire_les_etiquettes(agent: int | None = Query(default=None), user: UserModel = Depends(get_user_with_selected_organization)):
    organisation = user.selected_organization_id
    brouillon = None
    if agent is not None:
        workflow = await _agent_ou_404(user, agent)
        brouillon = await db_client.get_draft_version(workflow.id) or getattr(workflow, "released_definition", None)
    graphe = getattr(brouillon, "workflow_json", None)
    configurations = getattr(brouillon, "workflow_configurations", None)
    objets, illisibles = await cat.catalogue_de(organisation, graphe if isinstance(graphe, dict) else None)
    problemes = cat.diagnostiquer(graphe if isinstance(graphe, dict) else None, configurations if isinstance(configurations, dict) else None, objets, illisibles)
    return CatalogueEtiquettes(
        familles=list(FAMILLES),
        objets=[ObjetCitableVu(**o.en_dict()) for o in objets.values()],
        problemes=[ProblemeVu(**p.en_dict()) for p in problemes],
        illisibles=sorted(illisibles),
    )


@router.get("/etiquettes-prompt/utilise-dans", response_model=UtiliseDans)
async def lire_utilise_dans(cle: str = Query(min_length=3, max_length=300), user: UserModel = Depends(get_user_with_selected_organization)):
    return UtiliseDans(cle=cle, citations=[Citation(**c) for c in await corrections.utilise_dans(user.selected_organization_id, cle)])


@router.post("/etiquettes-prompt/{workflow_id}/corriger", response_model=Diagnostic)
async def corriger_une_etiquette(workflow_id: int, corps: CorrigerEtiquette, user: UserModel = Depends(get_user_with_selected_organization)):
    from api.db.protection_principale import PrincipaleProtegee

    workflow = await _agent_ou_404(user, workflow_id)
    try:
        vue = await corrections.corriger(workflow, user.selected_organization_id, corps.model_dump())
    except corrections.CorrectionRefusee as erreur:
        raise HTTPException(status_code=409, detail=str(erreur)) from None
    except PrincipaleProtegee as erreur:
        raise HTTPException(status_code=409, detail=str(erreur)) from None
    return Diagnostic(problemes=[ProblemeVu(**p) for p in vue["problemes"]])
