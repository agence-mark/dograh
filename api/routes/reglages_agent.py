"""[.mark] builder partie 2, U4 : la préparation d'un agent et l'origine de ses réglages (lecture seule, rien de stocké).

* ``GET /workflow/{id}/preparation``      la liste de préparation calculée (``services/preparation``) ;
* ``GET /workflow/{id}/heritage-reglages`` pour chaque réglage : valeur effective et origine (``services/heritage_reglages``) ;
* ``GET|PUT /workflow/{id}/juge-vrais-appels`` (U6, J3) : « juge des vrais appels » de cet agent (``services/juge/file``), éteint par défaut.

Toute lecture est bornée à l'organisation de l'appelant : l'agent d'une autre organisation répond 404.
"""

from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from api.db import db_client
from api.db.models import UserModel
from api.services import heritage_reglages, preparation
from api.services.juge import file as file_du_juge
from api.services.auth.depends import get_user
from api.services.modeles_reglages.service import ModeleRefuse

router = APIRouter(prefix="/workflow")


class EtapeDePreparation(BaseModel):
    id: str
    niveau: str
    etat: str
    theme: str
    source: str
    manquants: list[str] = []


class PreparationResponse(BaseModel):
    etapes: list[EtapeDePreparation]


class ReglageHerite(BaseModel):
    origine: str
    valeur: Any = None
    valeur_heritee: Any = None
    propre: bool
    modifiable: bool
    masquee: bool


class HeritageReglagesResponse(BaseModel):
    reglages: dict[str, ReglageHerite]


@router.get("/{workflow_id}/preparation")
async def lire_la_preparation(workflow_id: int, user: UserModel = Depends(get_user)) -> PreparationResponse:
    try:
        etapes = await preparation.lire(user.selected_organization_id, workflow_id)
    except ModeleRefuse as erreur:
        raise HTTPException(status_code=erreur.statut, detail=erreur.message) from None
    return PreparationResponse(etapes=[EtapeDePreparation(**e) for e in preparation.en_dicts(etapes)])


@router.get("/{workflow_id}/heritage-reglages")
async def lire_l_heritage_des_reglages(workflow_id: int, user: UserModel = Depends(get_user)) -> HeritageReglagesResponse:
    try:
        reglages = await heritage_reglages.lire(user.selected_organization_id, workflow_id)
    except ModeleRefuse as erreur:
        raise HTTPException(status_code=erreur.statut, detail=erreur.message) from None
    return HeritageReglagesResponse(reglages={c: ReglageHerite(**v) for c, v in reglages.items()})


class JugeDesVraisAppels(BaseModel):
    actif: bool = False


async def _agent_de_l_organisation(workflow_id: int, user: UserModel) -> None:
    if await db_client.get_workflow(workflow_id, organization_id=user.selected_organization_id) is None:
        raise HTTPException(status_code=404, detail="Agent not found")


@router.get("/{workflow_id}/juge-vrais-appels")
async def lire_le_juge_des_vrais_appels(workflow_id: int, user: UserModel = Depends(get_user)) -> JugeDesVraisAppels:
    await _agent_de_l_organisation(workflow_id, user)
    return JugeDesVraisAppels(actif=await file_du_juge.juge_des_vrais_appels(user.selected_organization_id, workflow_id))


@router.put("/{workflow_id}/juge-vrais-appels")
async def regler_le_juge_des_vrais_appels(
    workflow_id: int, requete: JugeDesVraisAppels, user: UserModel = Depends(get_user)
) -> JugeDesVraisAppels:
    await _agent_de_l_organisation(workflow_id, user)
    return JugeDesVraisAppels(actif=await file_du_juge.regler(user.selected_organization_id, workflow_id, requete.actif))
