"""[.mark] Builder partie 3, sous-lot 6 (SE-11 = D-3) : les alertes d'un agent et son rejeu planifié.

- ``GET  /builder/alertes/{workflow_id}``                 les réglages d'alerte de l'agent (types, seuils, mail) et les alertes levées ;
- ``PUT  /builder/alertes/{workflow_id}``                 règle le mail et/ou un type (actif, seuils) ;
- ``POST /builder/alertes/{workflow_id}/evaluer``         « Vérifier maintenant » : la même évaluation que la tâche de nuit ;
- ``GET  /builder/planification/{workflow_id}``           le rejeu planifié de l'agent (éteint par défaut) et son dernier résultat ;
- ``PUT  /builder/planification/{workflow_id}``           l'allume, l'éteint (ce qui l'arrête), règle fréquence, heure et essais.

⛔ L'agent est lu avec l'organisation de la personne (404 sinon) ; jamais de bascule automatique : rien ici ne publie ni ne retire.
Le rejeu planifié DÉPENSE : le PUT qui l'allume exige le droit de jouer les tests (registre des routes).
"""

from __future__ import annotations

from typing import Any, Literal

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from api.db import db_client
from api.db.models import UserModel
from api.services.alertes_agent import planifie, reglages, service, types
from api.services.auth.depends import get_user_with_selected_organization

router = APIRouter(prefix="/builder", tags=["builder-alertes"])


async def _agent_ou_404(user: UserModel, workflow_id: int):
    workflow = await db_client.get_workflow(workflow_id, organization_id=user.selected_organization_id)
    if workflow is None:
        raise HTTPException(status_code=404, detail="Workflow not found")
    return workflow


class ReglageDUnType(BaseModel):
    actif: bool | None = None
    seuils: dict[str, float] | None = None


class ReglageDesAlertes(BaseModel):
    mail: bool | None = None
    types: dict[str, ReglageDUnType] | None = None


class ReglageDuRejeu(BaseModel):
    actif: bool | None = None
    frequence: Literal["quotidien", "hebdomadaire"] | None = None
    jour: int | None = Field(default=None, ge=0, le=6)
    heure: int | None = Field(default=None, ge=0, le=23)
    repetitions: int | None = Field(default=None, ge=1, le=planifie.REPETITIONS_MAX)


def _vue_des_alertes(courant: dict[str, Any]) -> dict[str, Any]:
    return {
        **courant,
        "catalogue": {
            code: {
                "titre": t.titre,
                "explication": t.explication,
                "seuils": {nom: {"defaut": s.defaut, "bas": s.bas, "haut": s.haut} for nom, s in t.seuils.items()},
            }
            for code, t in types.TYPES.items()
        },
    }


@router.get("/alertes/{workflow_id}")
async def lire_les_alertes(workflow_id: int, user: UserModel = Depends(get_user_with_selected_organization)):
    await _agent_ou_404(user, workflow_id)
    return _vue_des_alertes(await reglages.lire(user.selected_organization_id, workflow_id))


@router.put("/alertes/{workflow_id}")
async def regler_les_alertes(workflow_id: int, corps: ReglageDesAlertes, user: UserModel = Depends(get_user_with_selected_organization)):
    await _agent_ou_404(user, workflow_id)
    try:
        courant = await reglages.regler(
            user.selected_organization_id,
            workflow_id,
            mail=corps.mail,
            par_type={code: r.model_dump(exclude_none=True) for code, r in (corps.types or {}).items()},
        )
    except ValueError as erreur:
        raise HTTPException(status_code=422, detail=str(erreur)) from None
    return _vue_des_alertes(courant)


@router.post("/alertes/{workflow_id}/evaluer")
async def evaluer_les_alertes(workflow_id: int, user: UserModel = Depends(get_user_with_selected_organization)):
    await _agent_ou_404(user, workflow_id)
    rendu = await service.evaluer_un_agent(user.selected_organization_id, workflow_id)
    return {**rendu, **_vue_des_alertes(await reglages.lire(user.selected_organization_id, workflow_id))}


@router.get("/planification/{workflow_id}")
async def lire_le_rejeu_planifie(workflow_id: int, user: UserModel = Depends(get_user_with_selected_organization)):
    await _agent_ou_404(user, workflow_id)
    return await planifie.lire(user.selected_organization_id, workflow_id)


@router.put("/planification/{workflow_id}")
async def regler_le_rejeu_planifie(workflow_id: int, corps: ReglageDuRejeu, user: UserModel = Depends(get_user_with_selected_organization)):
    await _agent_ou_404(user, workflow_id)
    try:
        return await planifie.regler(
            user.selected_organization_id,
            workflow_id,
            actif=corps.actif,
            frequence=corps.frequence,
            jour=corps.jour,
            heure=corps.heure,
            repetitions=corps.repetitions,
        )
    except ValueError as erreur:
        raise HTTPException(status_code=422, detail=str(erreur)) from None
