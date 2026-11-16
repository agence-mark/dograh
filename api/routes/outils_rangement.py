"""[.mark] Lot 11 du chantier module (E-22, E-46) : les dossiers et les kits de l'écran Outils.

Montées AVANT ``/tools/{tool_uuid}`` (comme ``outils_mark``) : ``/tools/dossiers`` et ``/tools/kits`` ne sont pas des identifiants d'outil.

- dossiers (par organisation, jamais celle de la requête) : ``GET/POST /tools/dossiers``, ``PATCH /tools/dossiers/{id}`` (renommer),
  ``PUT /tools/dossiers/{id}/parent``, ``DELETE /tools/dossiers/{id}``, ``PUT /tools/{uuid}/dossier`` (ranger ou sortir un outil) ;
- kits du fork (lus par tout membre ; écrits par l'équipe .mark, depuis le Labo) : ``GET/POST /tools/kits``, ``PATCH/DELETE /tools/kits/{id}``,
  ``POST /tools/kits/{id}/outils`` (depuis la ligne d'un outil), ``PATCH/DELETE /tools/kits/{id}/outils/{item}`` ;
- une organisation reçoit un kit : ``POST /tools/kits/{id}/appliquer`` ; ``GET /tools/kits/propositions`` et ``POST .../propositions/accepter``.

Le rangement n'est jamais envoyé au modèle : il ne vit ni dans la définition d'un outil ni dans ce que l'agent lit.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException

from api.db import db_client
from api.db.models import UserModel
from api.db.outils_rangement_client import ErreurRangement
from api.schemas.outils_rangement import (
    AccepterUneProposition,
    AjouterUnOutilAuKit,
    AppliquerUnKit,
    ApplicationDuKit,
    DossierOutilsCreation,
    DossierOutilsDeplacer,
    DossierOutilsRenommer,
    DossierOutilsReponse,
    KitCreation,
    KitModification,
    KitReponse,
    ModifierUnOutilDuKit,
    PropositionDeKit,
    RangerUnOutil,
)
from api.services.auth.depends import get_user_with_selected_organization

router = APIRouter(prefix="/tools", tags=["outils-rangement"])

CODES_HTTP = {"introuvable": 404, "conflit": 409, "invalide": 422}


def _http(erreur: ErreurRangement) -> HTTPException:
    return HTTPException(status_code=CODES_HTTP.get(erreur.code, 422), detail=str(erreur))


async def _equipe_au_labo(user: UserModel) -> None:
    """Écrire dans un kit du fork est un geste de l'équipe .mark, depuis le Labo (comme la bibliothèque)."""
    from api.services.builder.bibliotheque import droits
    from api.services.builder.bibliotheque.service import ErreurBibliotheque

    try:
        await droits.exiger_l_equipe_au_labo(user)
    except ErreurBibliotheque as erreur:
        raise HTTPException(status_code=erreur.statut, detail=str(erreur)) from None


def _vue_dossier(d) -> DossierOutilsReponse:
    return DossierOutilsReponse(id=d.id, name=d.name, parent_id=d.parent_id, created_at=d.created_at)


# ---- dossiers ---------------------------------------------------------------------------------------------------------------


@router.get("/dossiers", response_model=list[DossierOutilsReponse])
async def lister_les_dossiers(user: UserModel = Depends(get_user_with_selected_organization)):
    return await db_client.lister_dossiers_d_outils(user.selected_organization_id)


@router.post("/dossiers", response_model=DossierOutilsReponse)
async def creer_un_dossier(corps: DossierOutilsCreation, user: UserModel = Depends(get_user_with_selected_organization)):
    try:
        return _vue_dossier(await db_client.creer_dossier_d_outils(user.selected_organization_id, corps.name, corps.parent_id))
    except ErreurRangement as erreur:
        raise _http(erreur) from None


@router.patch("/dossiers/{dossier_id}", response_model=DossierOutilsReponse)
async def renommer_un_dossier(
    dossier_id: int, corps: DossierOutilsRenommer, user: UserModel = Depends(get_user_with_selected_organization)
):
    try:
        return _vue_dossier(await db_client.renommer_dossier_d_outils(user.selected_organization_id, dossier_id, corps.name))
    except ErreurRangement as erreur:
        raise _http(erreur) from None


@router.put("/dossiers/{dossier_id}/parent", response_model=DossierOutilsReponse)
async def deplacer_un_dossier(
    dossier_id: int, corps: DossierOutilsDeplacer, user: UserModel = Depends(get_user_with_selected_organization)
):
    try:
        return _vue_dossier(await db_client.deplacer_dossier_d_outils(user.selected_organization_id, dossier_id, corps.parent_id))
    except ErreurRangement as erreur:
        raise _http(erreur) from None


@router.delete("/dossiers/{dossier_id}")
async def supprimer_un_dossier(dossier_id: int, user: UserModel = Depends(get_user_with_selected_organization)):
    try:
        return {"ok": True, **await db_client.supprimer_dossier_d_outils(user.selected_organization_id, dossier_id)}
    except ErreurRangement as erreur:
        raise _http(erreur) from None


@router.put("/{tool_uuid}/dossier")
async def ranger_un_outil(tool_uuid: str, corps: RangerUnOutil, user: UserModel = Depends(get_user_with_selected_organization)):
    try:
        outil = await db_client.ranger_un_outil(user.selected_organization_id, tool_uuid, corps.dossier_id)
    except ErreurRangement as erreur:
        raise _http(erreur) from None
    return {"tool_uuid": outil.tool_uuid, "dossier_id": outil.folder_id}


# ---- kits -------------------------------------------------------------------------------------------------------------------


@router.get("/kits", response_model=list[KitReponse])
async def lister_les_kits(user: UserModel = Depends(get_user_with_selected_organization)):
    return await db_client.lister_les_kits()


@router.get("/kits/propositions", response_model=list[PropositionDeKit])
async def lister_les_propositions(user: UserModel = Depends(get_user_with_selected_organization)):
    return await db_client.propositions_de_kit(user.selected_organization_id)


@router.post("/kits/propositions/accepter")
async def accepter_une_proposition(
    corps: AccepterUneProposition, user: UserModel = Depends(get_user_with_selected_organization)
):
    try:
        return {"ok": True, **await db_client.accepter_une_proposition_de_kit(user.selected_organization_id, user.id, corps.tool_uuid)}
    except ErreurRangement as erreur:
        raise _http(erreur) from None


@router.post("/kits", response_model=KitReponse)
async def creer_un_kit(corps: KitCreation, user: UserModel = Depends(get_user_with_selected_organization)):
    await _equipe_au_labo(user)
    try:
        return await db_client.creer_un_kit(corps.name, corps.description)
    except ErreurRangement as erreur:
        raise _http(erreur) from None


@router.get("/kits/{kit_id}", response_model=KitReponse)
async def lire_un_kit(kit_id: int, user: UserModel = Depends(get_user_with_selected_organization)):
    try:
        return await db_client.lire_un_kit(kit_id)
    except ErreurRangement as erreur:
        raise _http(erreur) from None


@router.patch("/kits/{kit_id}", response_model=KitReponse)
async def modifier_un_kit(kit_id: int, corps: KitModification, user: UserModel = Depends(get_user_with_selected_organization)):
    await _equipe_au_labo(user)
    try:
        return await db_client.modifier_un_kit(kit_id, corps.name, corps.description)
    except ErreurRangement as erreur:
        raise _http(erreur) from None


@router.delete("/kits/{kit_id}")
async def supprimer_un_kit(kit_id: int, user: UserModel = Depends(get_user_with_selected_organization)):
    await _equipe_au_labo(user)
    try:
        await db_client.supprimer_un_kit(kit_id)
    except ErreurRangement as erreur:
        raise _http(erreur) from None
    return {"ok": True}


@router.post("/kits/{kit_id}/outils", response_model=KitReponse)
async def ajouter_un_outil_au_kit(
    kit_id: int, corps: AjouterUnOutilAuKit, user: UserModel = Depends(get_user_with_selected_organization)
):
    await _equipe_au_labo(user)
    outil = await db_client.get_tool_by_uuid(corps.tool_uuid, user.selected_organization_id)
    if outil is None:
        raise HTTPException(status_code=404, detail="Tool not found")
    try:
        return await db_client.ajouter_un_outil_au_kit(
            kit_id,
            name=outil.name,
            description=outil.description,
            category=outil.category,
            definition=outil.definition,
            icon=outil.icon,
            icon_color=outil.icon_color,
        )
    except ErreurRangement as erreur:
        raise _http(erreur) from None


@router.patch("/kits/{kit_id}/outils/{item_id}", response_model=KitReponse)
async def modifier_un_outil_du_kit(
    kit_id: int, item_id: int, corps: ModifierUnOutilDuKit, user: UserModel = Depends(get_user_with_selected_organization)
):
    await _equipe_au_labo(user)
    try:
        return await db_client.modifier_un_outil_du_kit(
            kit_id, item_id, name=corps.name, description=corps.description, definition=corps.definition
        )
    except ErreurRangement as erreur:
        raise _http(erreur) from None


@router.delete("/kits/{kit_id}/outils/{item_id}", response_model=KitReponse)
async def retirer_un_outil_du_kit(kit_id: int, item_id: int, user: UserModel = Depends(get_user_with_selected_organization)):
    await _equipe_au_labo(user)
    try:
        return await db_client.retirer_un_outil_du_kit(kit_id, item_id)
    except ErreurRangement as erreur:
        raise _http(erreur) from None


@router.post("/kits/{kit_id}/appliquer", response_model=ApplicationDuKit)
async def appliquer_un_kit(kit_id: int, corps: AppliquerUnKit, user: UserModel = Depends(get_user_with_selected_organization)):
    try:
        return await db_client.appliquer_un_kit(user.selected_organization_id, user.id, kit_id, corps.dossier_id)
    except ErreurRangement as erreur:
        raise _http(erreur) from None
