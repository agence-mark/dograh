"""[.mark] Settings templates, on screen and without it (cloture-code-avant-migration, lot 5).

All routes are scoped to the user's selected organization; no route takes an organization in its path or
body (M1). Routes (prefix ``/organizations/modeles-de-reglages``):

- ``GET    ""``                  the templates of the organization, and the sections a template is applied by;
- ``POST   ""``                  freeze the active settings of an agent under a name (M7);
- ``POST   "/import"``           bring in a file exported from another organization (refuses what it does not know);
- ``GET    "/agent/{id}"``       the mention an agent keeps of the last template applied (M4);
- ``PATCH  "/{id}"``             rename;  ``DELETE "/{id}"`` delete (no agent already set changes, M4);
- ``GET    "/{id}/export"``      the file of a template: no key of access, ever (M3);
- ``POST   "/{id}/appliquer"``   apply to the DRAFT of an agent, sections ticked (M5); ``a_blanc`` says what would
  happen, and which providers have no key, and writes nothing.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from loguru import logger
from pydantic import ValidationError

from api.db.models import UserModel
from api.schemas.modeles_reglages import (
    DemandeApplication,
    DemandeCreation,
    DemandeRenommer,
    FichierDeModele,
    ListeDesModeles,
    MentionDeLagent,
    ModeleDeReglages,
    ResultatApplication,
    ResumeDuModele,
)
from api.services.auth.depends import get_user_with_selected_organization
from api.services.modeles_reglages import classement as cl
from api.services.modeles_reglages import service

router = APIRouter(prefix="/organizations/modeles-de-reglages", tags=["organizations"])


def _refus(erreur: service.ModeleRefuse) -> HTTPException:
    detail: object = erreur.message
    if erreur.statut == 422 and erreur.cle:
        detail = [{"msg": erreur.message, "loc": ["body", "valeurs", erreur.cle]}]
    return HTTPException(status_code=erreur.statut, detail=detail)


def _stock_illisible(erreur: Exception) -> HTTPException:
    logger.warning(f"[.mark] Settings templates unreadable: {erreur!r}")
    return HTTPException(
        status_code=500,
        detail="The templates saved for this organization cannot be read. Nothing was changed; saving now would replace them.",
    )


def _resume(modele: ModeleDeReglages) -> ResumeDuModele:
    return ResumeDuModele(
        id=modele.id,
        nom=modele.nom,
        cree_le=modele.cree_le,
        origine=modele.origine,
        sections=modele.sections,
        nombre_de_reglages=len(modele.valeurs),
    )


@router.get("", response_model=ListeDesModeles)
async def lister_les_modeles(user: UserModel = Depends(get_user_with_selected_organization)):
    """⛔ Strict: shown empty because unreadable, the next save would replace them."""
    try:
        stock = await service.lire_le_stock(user.selected_organization_id)
    except (ValidationError, ValueError) as erreur:
        raise _stock_illisible(erreur) from None
    return ListeDesModeles(modeles=[_resume(m) for m in stock.modeles], sections=list(cl.SECTIONS))


@router.post("", response_model=ResumeDuModele)
async def creer_un_modele(
    demande: DemandeCreation,
    user: UserModel = Depends(get_user_with_selected_organization),
):
    try:
        return _resume(await service.creer_un_modele(user.selected_organization_id, demande.nom, demande.workflow_id))
    except service.ModeleRefuse as erreur:
        raise _refus(erreur) from None
    except (ValidationError, ValueError) as erreur:
        raise _stock_illisible(erreur) from None


@router.post("/import", response_model=ResumeDuModele)
async def importer_un_modele(
    fichier: FichierDeModele,
    user: UserModel = Depends(get_user_with_selected_organization),
):
    try:
        return _resume(await service.importer_un_fichier(user.selected_organization_id, fichier))
    except service.ModeleRefuse as erreur:
        raise _refus(erreur) from None
    except (ValidationError, ValueError) as erreur:
        raise _stock_illisible(erreur) from None


@router.get("/agent/{workflow_id}", response_model=MentionDeLagent)
async def mention_de_lagent(
    workflow_id: int,
    user: UserModel = Depends(get_user_with_selected_organization),
):
    try:
        return MentionDeLagent(mention=await service.mention_de_l_agent(user.selected_organization_id, workflow_id))
    except service.ModeleRefuse as erreur:
        raise _refus(erreur) from None
    except (ValidationError, ValueError) as erreur:
        raise _stock_illisible(erreur) from None


@router.patch("/{modele_id}", response_model=ResumeDuModele)
async def renommer_un_modele(
    modele_id: str,
    demande: DemandeRenommer,
    user: UserModel = Depends(get_user_with_selected_organization),
):
    try:
        return _resume(await service.renommer_un_modele(user.selected_organization_id, modele_id, demande.nom))
    except service.ModeleRefuse as erreur:
        raise _refus(erreur) from None
    except (ValidationError, ValueError) as erreur:
        raise _stock_illisible(erreur) from None


@router.delete("/{modele_id}", status_code=204)
async def supprimer_un_modele(
    modele_id: str,
    user: UserModel = Depends(get_user_with_selected_organization),
):
    try:
        await service.supprimer_un_modele(user.selected_organization_id, modele_id)
    except service.ModeleRefuse as erreur:
        raise _refus(erreur) from None
    except (ValidationError, ValueError) as erreur:
        raise _stock_illisible(erreur) from None


@router.get("/{modele_id}/export", response_model=FichierDeModele)
async def exporter_un_modele(
    modele_id: str,
    user: UserModel = Depends(get_user_with_selected_organization),
):
    try:
        stock = await service.lire_le_stock(user.selected_organization_id)
        return service.fichier_du_modele(service.trouver(stock, modele_id))
    except service.ModeleRefuse as erreur:
        raise _refus(erreur) from None
    except (ValidationError, ValueError) as erreur:
        raise _stock_illisible(erreur) from None


def _verifier_ce_qui_serait_ecrit(configurations: dict) -> None:
    """The very validators the save of an agent runs (``PUT /workflow/{id}``): what that save would refuse,
    the application refuses too, before anything is written."""
    from api.routes.workflow import UpdateWorkflowRequest

    try:
        UpdateWorkflowRequest(workflow_configurations=configurations)
    except ValidationError as erreur:
        premier = erreur.errors()[0]
        raise service.ModeleRefuse(
            f"The agent's settings would not be accepted with this template: {premier.get('msg', 'invalid')}."
        ) from None


@router.post("/{modele_id}/appliquer", response_model=ResultatApplication)
async def appliquer_un_modele(
    modele_id: str,
    demande: DemandeApplication,
    user: UserModel = Depends(get_user_with_selected_organization),
):
    try:
        return await service.appliquer_un_modele(
            user.selected_organization_id,
            modele_id,
            demande.workflow_id,
            demande.sections,
            a_blanc=demande.a_blanc,
            verifier=_verifier_ce_qui_serait_ecrit,
        )
    except service.ModeleRefuse as erreur:
        raise _refus(erreur) from None
    except (ValidationError, ValueError) as erreur:
        raise _stock_illisible(erreur) from None
