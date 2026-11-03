"""[.mark] Builder partie 2, lot M (méthodes de Cognigy, § 17) : les routes de l'aperçu avant restauration, des options de la construction
et des recettes d'agent.

- ``GET /builder/agents/{id}/versions/{n}/apercu``  ce qui sera perdu et retrouvé en revenant à cette version (aucun effet) ;
- ``GET|PUT /builder/options``                      la sauvegarde avant modification (éteinte) et la recette par défaut (équipe .mark) ;
- ``GET /builder/recettes``                         les recettes proposées à la création (hors Rejeté, Recette d'abord) et le défaut ;
- ``GET|PUT /builder/agents/{id}/recette``          la recette d'un agent ; elle ne change plus une fois une version publiée.

Tout est lu et écrit AVEC l'organisation de l'utilisateur (R0).
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from api.db import db_client
from api.db.models import UserModel
from api.services.auth.depends import get_user_with_selected_organization
from api.services.builder import apercu, options, recettes, revue
from api.services.builder.bibliotheque import droits
from api.services.builder.bibliotheque.service import ErreurBibliotheque

router = APIRouter(tags=["builder"])


async def _agent_ou_404(user: UserModel, workflow_id: int):
    workflow = await db_client.get_workflow(workflow_id, organization_id=user.selected_organization_id)
    if not workflow:
        raise HTTPException(status_code=404, detail="Agent not found")
    return workflow


@router.get("/agents/{workflow_id}/versions/{numero}/apercu")
async def apercu_avant_de_revenir(workflow_id: int, numero: int, user: UserModel = Depends(get_user_with_selected_organization)):
    workflow = await _agent_ou_404(user, workflow_id)
    try:
        return await apercu.apercu_de_la_restauration(user.selected_organization_id, workflow, numero)
    except revue.ErreurRevue as erreur:
        raise HTTPException(status_code=404, detail=str(erreur)) from None


class VueOptions(BaseModel):
    sauvegarde_avant_modification: bool = False
    recette_par_defaut: str = Field(default="", max_length=64)


@router.get("/options", response_model=VueOptions)
async def lire_les_options(user: UserModel = Depends(get_user_with_selected_organization)):
    try:
        await droits.exiger_l_equipe(user)
    except ErreurBibliotheque as erreur:
        raise HTTPException(status_code=erreur.statut, detail=str(erreur)) from None
    return await options.lire(await options.organisation_des_options(user))


@router.put("/options", response_model=VueOptions)
async def regler_les_options(demande: VueOptions, user: UserModel = Depends(get_user_with_selected_organization)):
    """Réservé à l'équipe .mark. Une recette par défaut doit exister en bibliothèque (ou rester vide)."""
    try:
        await droits.exiger_l_equipe(user)
    except ErreurBibliotheque as erreur:
        raise HTTPException(status_code=erreur.statut, detail=str(erreur)) from None
    if demande.recette_par_defaut:
        choisie = await recettes.lire(demande.recette_par_defaut)
        if choisie is None or choisie.statut == "rejete":
            raise HTTPException(status_code=422, detail="Unknown recipe.")
    nouvelles = options.Options(**demande.model_dump())
    await options.ecrire(await options.organisation_des_options(user), nouvelles)
    return nouvelles


class VueRecettes(BaseModel):
    defaut: str | None
    recettes: list[dict[str, Any]]


@router.get("/recettes", response_model=VueRecettes)
async def lister_les_recettes(user: UserModel = Depends(get_user_with_selected_organization)):
    liste = await recettes.lister()
    defaut = await recettes.par_defaut(user.selected_organization_id)
    return VueRecettes(defaut=defaut.slug if defaut else None, recettes=[r.en_json() for r in liste])


class VueRecetteDeLAgent(BaseModel):
    recette: dict[str, Any] | None
    indiquee: bool
    modifiable: bool


async def _vue_de_l_agent(user: UserModel, workflow) -> VueRecetteDeLAgent:
    recette, indiquee = await recettes.de_l_agent(user.selected_organization_id, workflow.id)
    return VueRecetteDeLAgent(
        recette=recette.en_json() if recette else None,
        indiquee=indiquee,
        modifiable=not await db_client.workflow_a_ete_publie(workflow.id),
    )


@router.get("/agents/{workflow_id}/recette", response_model=VueRecetteDeLAgent)
async def lire_la_recette_de_l_agent(workflow_id: int, user: UserModel = Depends(get_user_with_selected_organization)):
    return await _vue_de_l_agent(user, await _agent_ou_404(user, workflow_id))


class ChoixDeRecette(BaseModel):
    recette: str = Field(min_length=1, max_length=64)


@router.put("/agents/{workflow_id}/recette", response_model=VueRecetteDeLAgent)
async def changer_la_recette_de_l_agent(
    workflow_id: int, demande: ChoixDeRecette, user: UserModel = Depends(get_user_with_selected_organization)
):
    workflow = await _agent_ou_404(user, workflow_id)
    try:
        await recettes.definir(
            user.selected_organization_id,
            workflow.id,
            demande.recette,
            deja_publie=await db_client.workflow_a_ete_publie(workflow.id),
            par=getattr(user, "email", "") or "",
        )
    except recettes.ErreurRecette as erreur:
        raise HTTPException(status_code=erreur.statut, detail=str(erreur)) from None
    return await _vue_de_l_agent(user, workflow)
