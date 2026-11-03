"""[.mark] builder partie 2, U4 : la préparation d'un agent et l'origine de ses réglages (lecture seule, rien de stocké).

* ``GET /workflow/{id}/preparation``      la liste de préparation calculée (``services/preparation``) ;
* ``GET /workflow/{id}/heritage-reglages`` pour chaque réglage : valeur effective et origine (``services/heritage_reglages``).

Toute lecture est bornée à l'organisation de l'appelant : l'agent d'une autre organisation répond 404.
"""

from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from api.db.models import UserModel
from api.services import heritage_reglages, preparation
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
