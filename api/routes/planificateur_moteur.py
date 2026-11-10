"""[.mark] Clôture, SA-3 (D18) : les limites du moteur du planificateur d'une organisation (niveau « avancé »).

- ``GET /organizations/planificateur-moteur``  les réglages (les valeurs d'avant quand rien n'est posé)
- ``PUT /organizations/planificateur-moteur``  enregistrés, bornés par le schéma

L'organisation est toujours celle du compte connecté (cloisonnement). Les droits sont ceux de ``/organizations/*``.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends

from api.db.models import UserModel
from api.schemas.planificateur import ReglagesMoteurPlanificateur
from api.services.auth.depends import get_user_with_selected_organization
from api.services.planificateur.moteur import ecrire_reglages, lire_reglages

router = APIRouter(prefix="/organizations/planificateur-moteur", tags=["organizations"])


@router.get("", response_model=ReglagesMoteurPlanificateur)
async def get_planificateur_moteur(user: UserModel = Depends(get_user_with_selected_organization)):
    return await lire_reglages(user.selected_organization_id)


@router.put("", response_model=ReglagesMoteurPlanificateur)
async def put_planificateur_moteur(
    request: ReglagesMoteurPlanificateur, user: UserModel = Depends(get_user_with_selected_organization)
):
    return await ecrire_reglages(user.selected_organization_id, request)
