"""[.mark] Le builder, lot 3 : les gestes HUMAINS du contexte client (``/builder``, avec ``builder.py``).

- ``GET    /builder/contexte/{agent}``                    dépôts, fiche (avec le classement de chaque fait), base proposée ;
- ``POST   /builder/depot/{agent}``                       dépose un fichier (PDF, Word, Markdown, texte) ;
- ``POST   /builder/depot/{agent}/site``                  dépose l'adresse d'un site (pages publiques) ;
- ``DELETE /builder/depot/{agent}/{depot}``               retire un dépôt ;
- ``PUT    /builder/fiche/{agent}/ligne``                 une personne corrige une ligne ou répond à un trou (source : elle) ;
- ``POST   /builder/base/{agent}/{doc}/valider``          valide un document de base : il entre dans la base de connaissances ;
- ``POST   /builder/base/{agent}/{doc}/rejeter``          le rejette, avec un motif.

La validation de la fiche est dans ``builder.py``. Ces routes sont les seuls chemins qui valident : le builder n'a
pas ces actions. Tout est lu et écrit AVEC l'organisation de l'utilisateur (un agent d'une autre organisation = 404).
"""

from __future__ import annotations

from typing import Any, Literal

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from pydantic import BaseModel, Field

from api.db import db_client
from api.db.models import UserModel
from api.services.auth.depends import get_user_with_selected_organization
from api.services.builder import fiche as service_fiche
from api.services.builder.bibliotheque import droits
from api.services.builder.dossiers import base, classement, depot, extraction

router = APIRouter(tags=["builder"])


async def _agent_ou_404(user: UserModel, workflow_id: int):
    workflow = await db_client.get_workflow(workflow_id, organization_id=user.selected_organization_id)
    if not workflow:
        raise HTTPException(status_code=404, detail="Agent not found")
    return workflow


class VueDepot(BaseModel):
    id: str
    nom: str
    genre: Literal["fichier", "site"]
    statut: Literal["lu", "illisible"]
    raison: str | None = None
    pages: int = 0
    caracteres: int = 0
    tronque: bool = False
    octets: int | None = None
    ajoute_par: str = ""
    ajoute_le: str = ""
    refusees: list[dict[str, str]] = Field(default_factory=list)


class VueContexte(BaseModel):
    depots: list[VueDepot]
    fiche: dict[str, Any]
    classements: dict[str, str]
    base: list[dict[str, Any]]


async def _vue(organisation: int, workflow_id: int) -> VueContexte:
    fiche = await service_fiche.lire(organisation, workflow_id)
    return VueContexte(
        depots=[VueDepot.model_validate(depot.vue(d)) for d in await depot.lister(organisation, workflow_id)],
        fiche=fiche.model_dump(mode="json"),
        classements={n: classement.classement_effectif(n, c.classement, c.valeur) for n, c in fiche.champs.items()},
        base=[d.model_dump(mode="json") for d in await base.lister(organisation, workflow_id)],
    )


@router.get("/contexte/{workflow_id}", response_model=VueContexte)
async def lire_le_contexte(workflow_id: int, user: UserModel = Depends(get_user_with_selected_organization)):
    await _agent_ou_404(user, workflow_id)
    return await _vue(user.selected_organization_id, workflow_id)


@router.post("/depot/{workflow_id}", response_model=VueDepot)
async def deposer_un_fichier(
    workflow_id: int, fichier: UploadFile = File(...), user: UserModel = Depends(get_user_with_selected_organization)
):
    await _agent_ou_404(user, workflow_id)
    # Lu par morceaux bornés : un fichier géant n'est jamais chargé en entier.
    contenu = await fichier.read(extraction.OCTETS_MAX + 1)
    try:
        return VueDepot.model_validate(
            await depot.deposer_fichier(
                user.selected_organization_id, workflow_id, fichier.filename or "document", contenu, droits.nom_de_l_auteur(user)
            )
        )
    except depot.ErreurDepot as erreur:
        raise HTTPException(status_code=422, detail=str(erreur)) from None


class AdresseDuSite(BaseModel):
    adresse: str = Field(min_length=3, max_length=2000)


def _lire_un_site(**options: Any) -> dict[str, Any]:
    """Les tests remplacent cette fonction pour ne jamais atteindre le réseau."""
    return options


@router.post("/depot/{workflow_id}/site", response_model=VueDepot)
async def deposer_un_site(
    workflow_id: int, demande: AdresseDuSite, user: UserModel = Depends(get_user_with_selected_organization)
):
    await _agent_ou_404(user, workflow_id)
    try:
        return VueDepot.model_validate(
            await depot.deposer_site(
                user.selected_organization_id, workflow_id, demande.adresse, droits.nom_de_l_auteur(user), **_lire_un_site()
            )
        )
    except depot.ErreurDepot as erreur:
        raise HTTPException(status_code=422, detail=str(erreur)) from None


@router.delete("/depot/{workflow_id}/{depot_id}")
async def retirer_un_depot(workflow_id: int, depot_id: str, user: UserModel = Depends(get_user_with_selected_organization)):
    await _agent_ou_404(user, workflow_id)
    if not await depot.retirer(user.selected_organization_id, workflow_id, depot_id):
        raise HTTPException(status_code=404, detail="Deposit not found")
    return {"ok": True}


class LigneDeLaFiche(BaseModel):
    champ: str = Field(min_length=1, max_length=100)
    valeur: str = Field(min_length=1, max_length=5000)
    classement: Literal["objet", "base", "regle"] | None = None


@router.put("/fiche/{workflow_id}/ligne")
async def ecrire_une_ligne_de_la_fiche(
    workflow_id: int, ligne: LigneDeLaFiche, user: UserModel = Depends(get_user_with_selected_organization)
):
    """Une personne corrige une ligne ou répond à un trou. La source de la ligne EST la personne ; la validation de
    la fiche est retirée (elle change), et le trou de ce champ se ferme."""
    await _agent_ou_404(user, workflow_id)
    auteur = droits.nom_de_l_auteur(user)
    organisation = user.selected_organization_id
    existante = (await service_fiche.lire(organisation, workflow_id)).champs.get(ligne.champ)
    champ = service_fiche.ChampFiche(
        valeur=ligne.valeur, source=f"Réponse de {auteur}", classement=ligne.classement or (existante.classement if existante else None)
    )
    try:
        await service_fiche.ecrire(organisation, workflow_id, {ligne.champ: champ})
    except service_fiche.ErreurFiche as erreur:
        raise HTTPException(status_code=422, detail=str(erreur)) from None
    return (await _vue(organisation, workflow_id)).model_dump(mode="json")


@router.post("/base/{workflow_id}/{document_id}/valider")
async def valider_un_document_de_base(
    workflow_id: int, document_id: str, user: UserModel = Depends(get_user_with_selected_organization)
):
    await _agent_ou_404(user, workflow_id)
    try:
        document = await base.valider(user, workflow_id, document_id, droits.nom_de_l_auteur(user))
    except base.ErreurBase as erreur:
        raise HTTPException(status_code=404 if erreur.code == "introuvable" else 422, detail=str(erreur)) from None
    return {"document": document.model_dump(mode="json")}


class RejetDeBase(BaseModel):
    motif: str | None = Field(default=None, max_length=500)


@router.post("/base/{workflow_id}/{document_id}/rejeter")
async def rejeter_un_document_de_base(
    workflow_id: int, document_id: str, demande: RejetDeBase, user: UserModel = Depends(get_user_with_selected_organization)
):
    await _agent_ou_404(user, workflow_id)
    try:
        document = await base.rejeter(user.selected_organization_id, workflow_id, document_id, droits.nom_de_l_auteur(user), demande.motif)
    except base.ErreurBase as erreur:
        raise HTTPException(status_code=404 if erreur.code == "introuvable" else 422, detail=str(erreur)) from None
    return {"document": document.model_dump(mode="json")}
