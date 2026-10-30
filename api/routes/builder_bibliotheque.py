"""[.mark] La bibliothèque du builder (``/builder/bibliotheque``). Chantier builder-agent-vocal, lot 2.

LECTURE : toute personne connectée, quelle que soit son organisation (la bibliothèque vit dans l'organisation
.mark, B9/Q4). ÉCRITURE : les membres de l'organisation .mark seulement (``droits``). Les gestes qui engagent tous
les clients sont des clics humains et n'existent QUE ici : passer en Recette, rejeter, revenir en arrière,
accepter ou refuser une proposition.

- ``GET  /familles``                                      les familles (B44) ;
- ``GET  ?famille=&statut=``                              les éléments (résumés) ;
- ``GET  /{famille}/{slug}``                              un élément, toutes ses versions ;
- ``POST /{famille}``                                     crée un élément ;
- ``POST /{famille}/{slug}/versions``                     ajoute une version (toujours Candidat) ;
- ``POST /{famille}/{slug}/retour``                       retour arrière (ajoute une version qui reprend l'ancienne) ;
- ``POST /{famille}/{slug}/statut``                       Recette (banc exigé) ou Rejeté (raison exigée) ;
- ``GET  /{famille}/{slug}/utilisation``                  « utilisée par N agents » ;
- ``POST /import`` · ``POST /import/adresse``             importer avec origine, licence, date ; comparatif au réimport ;
- ``GET  /propositions`` · ``POST /propositions`` · ``POST /propositions/{id}/accepter|refuser``.
"""

from __future__ import annotations

from typing import Any, Literal

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from api.db.models import UserModel
from api.services.auth.depends import get_user_with_selected_organization
from api.services.builder.bibliotheque import droits, importation, propositions, service
from api.services.builder.bibliotheque.familles import FAMILLES
from api.services.builder.bibliotheque.modele import Banc, Element, Origine, Proposition, Resume, Statut
from api.services.builder.bibliotheque.service import ErreurBibliotheque

router = APIRouter(prefix="/bibliotheque", tags=["builder"])


def _refus(erreur: ErreurBibliotheque) -> HTTPException:
    return HTTPException(status_code=erreur.statut, detail=str(erreur))


async def _equipe(user: UserModel) -> str:
    """Exige l'équipe .mark ; rend le nom d'auteur pour l'historique."""
    try:
        await droits.exiger_l_equipe(user)
    except ErreurBibliotheque as erreur:
        raise _refus(erreur) from None
    return droits.nom_de_l_auteur(user)


class VueFamille(BaseModel):
    slug: str
    libelle: str
    groupe: str
    cible: str
    mode: str


@router.get("/familles", response_model=list[VueFamille])
async def lister_les_familles(user: UserModel = Depends(get_user_with_selected_organization)):
    return [VueFamille(slug=f.slug, libelle=f.libelle, groupe=f.groupe, cible=f.cible, mode=f.mode) for f in FAMILLES.values()]


@router.get("", response_model=list[Resume])
async def lister_les_elements(
    famille: str | None = None,
    statut: Statut | None = None,
    user: UserModel = Depends(get_user_with_selected_organization),
):
    try:
        return await service.lister(famille, statut)
    except ErreurBibliotheque as erreur:
        raise _refus(erreur) from None


# Les chemins fixes passent AVANT les chemins à paramètres.


@router.get("/propositions", response_model=list[Proposition])
async def lister_les_propositions(
    etat: Literal["en_attente", "acceptee", "refusee"] | None = "en_attente",
    user: UserModel = Depends(get_user_with_selected_organization),
):
    try:
        return await propositions.lister(etat)
    except ErreurBibliotheque as erreur:
        raise _refus(erreur) from None


class NouvelleProposition(BaseModel):
    type: Literal["version", "passage_recette", "rejet"]
    famille: str
    slug: str
    justification: str = Field(min_length=1, max_length=2000)
    titre: str = ""
    contenu: dict[str, Any] | None = None
    version: int | None = None
    banc: Banc | None = None


@router.post("/propositions", response_model=Proposition, status_code=201)
async def proposer(demande: NouvelleProposition, user: UserModel = Depends(get_user_with_selected_organization)):
    auteur = await _equipe(user)
    try:
        return await propositions.creer(
            demande.type,
            demande.famille,
            demande.slug,
            demande.justification,
            auteur,
            titre=demande.titre,
            contenu=demande.contenu,
            version=demande.version,
            banc=demande.banc,
        )
    except ErreurBibliotheque as erreur:
        raise _refus(erreur) from None


class Acceptation(BaseModel):
    banc: Banc | None = None
    motif: str | None = Field(default=None, max_length=1000)


@router.post("/propositions/{identifiant}/accepter", response_model=Proposition)
async def accepter(identifiant: str, demande: Acceptation, user: UserModel = Depends(get_user_with_selected_organization)):
    auteur = await _equipe(user)
    try:
        return await propositions.accepter(identifiant, auteur, banc=demande.banc, motif=demande.motif)
    except ErreurBibliotheque as erreur:
        raise _refus(erreur) from None


class Refus(BaseModel):
    motif: str = Field(min_length=1, max_length=1000)


@router.post("/propositions/{identifiant}/refuser", response_model=Proposition)
async def refuser(identifiant: str, demande: Refus, user: UserModel = Depends(get_user_with_selected_organization)):
    auteur = await _equipe(user)
    try:
        return await propositions.refuser(identifiant, auteur, demande.motif)
    except ErreurBibliotheque as erreur:
        raise _refus(erreur) from None


class Importation(BaseModel):
    famille: str
    slug: str = Field(pattern=r"^[a-z0-9][a-z0-9-]{0,63}$")
    titre: str = Field(min_length=1, max_length=200)
    contenu: dict[str, Any]
    origine: Origine


class ResultatImport(BaseModel):
    element: Element
    cree: bool
    comparatif: dict[str, Any] | None


@router.post("/import", response_model=ResultatImport)
async def importer(demande: Importation, user: UserModel = Depends(get_user_with_selected_organization)):
    auteur = await _equipe(user)
    try:
        resultat = await importation.importer(demande.famille, demande.slug, demande.titre, demande.contenu, demande.origine, auteur)
    except ErreurBibliotheque as erreur:
        raise _refus(erreur) from None
    return ResultatImport(**resultat)


class ImportationParAdresse(BaseModel):
    famille: str
    slug: str = Field(pattern=r"^[a-z0-9][a-z0-9-]{0,63}$")
    titre: str = Field(min_length=1, max_length=200)
    adresse: str = Field(max_length=1000)
    licence: str = Field(min_length=1, max_length=100, description="The licence, or 'inconnue'.")
    date: str = Field(pattern=r"^\d{4}-\d{2}-\d{2}$")
    cle_du_contenu: str = Field(default="texte", max_length=50, description="The content is stored as {cle_du_contenu: text}.")


@router.post("/import/adresse", response_model=ResultatImport)
async def importer_depuis_une_adresse(
    demande: ImportationParAdresse, user: UserModel = Depends(get_user_with_selected_organization)
):
    """Lit la page publique côté serveur (https, adresse publique, texte, taille bornée), puis importe."""
    auteur = await _equipe(user)
    try:
        texte = await importation.lire_adresse(demande.adresse)
        origine = Origine(source=demande.adresse, licence=demande.licence, date=demande.date)
        resultat = await importation.importer(
            demande.famille, demande.slug, demande.titre, {demande.cle_du_contenu: texte}, origine, auteur
        )
    except ErreurBibliotheque as erreur:
        raise _refus(erreur) from None
    return ResultatImport(**resultat)


@router.get("/{famille}/{slug}", response_model=Element)
async def lire_un_element(famille: str, slug: str, user: UserModel = Depends(get_user_with_selected_organization)):
    try:
        return await service.lire_element(famille, slug)
    except ErreurBibliotheque as erreur:
        raise _refus(erreur) from None


@router.get("/{famille}/{slug}/utilisation")
async def lire_l_utilisation(famille: str, slug: str, user: UserModel = Depends(get_user_with_selected_organization)):
    """Les agents qui utilisent l'élément (organisation, agent, version). Les noms restent à l'écran de chaque client."""
    try:
        await service.lire_element(famille, slug)
        liste = await service.utilisation(famille, slug)
    except ErreurBibliotheque as erreur:
        raise _refus(erreur) from None
    return {"nombre": len(liste), "agents": liste}


class NouvelElement(BaseModel):
    slug: str = Field(pattern=r"^[a-z0-9][a-z0-9-]{0,63}$")
    titre: str = Field(min_length=1, max_length=200)
    contenu: dict[str, Any]
    notes: str = Field(default="", max_length=2000)


@router.post("/{famille}", response_model=Element, status_code=201)
async def creer_un_element(famille: str, demande: NouvelElement, user: UserModel = Depends(get_user_with_selected_organization)):
    auteur = await _equipe(user)
    try:
        return await service.creer(famille, demande.slug, demande.titre, demande.contenu, auteur, notes=demande.notes)
    except ErreurBibliotheque as erreur:
        raise _refus(erreur) from None


class NouvelleVersion(BaseModel):
    contenu: dict[str, Any]
    titre: str | None = Field(default=None, max_length=200)
    notes: str = Field(default="", max_length=2000)


@router.post("/{famille}/{slug}/versions", response_model=Element)
async def ajouter_une_version(
    famille: str, slug: str, demande: NouvelleVersion, user: UserModel = Depends(get_user_with_selected_organization)
):
    auteur = await _equipe(user)
    try:
        return await service.ajouter_version(famille, slug, demande.contenu, auteur, notes=demande.notes, titre=demande.titre)
    except ErreurBibliotheque as erreur:
        raise _refus(erreur) from None


class RetourArriere(BaseModel):
    version: int = Field(ge=1)


@router.post("/{famille}/{slug}/retour", response_model=Element)
async def revenir_en_arriere(
    famille: str, slug: str, demande: RetourArriere, user: UserModel = Depends(get_user_with_selected_organization)
):
    auteur = await _equipe(user)
    try:
        return await service.retour_arriere(famille, slug, demande.version, auteur)
    except ErreurBibliotheque as erreur:
        raise _refus(erreur) from None


class ChangementDeStatut(BaseModel):
    version: int = Field(ge=1)
    statut: Literal["recette", "rejete", "candidat"]
    banc: Banc | None = None
    raison: str | None = Field(default=None, max_length=1000)


@router.post("/{famille}/{slug}/statut", response_model=Element)
async def changer_le_statut(
    famille: str, slug: str, demande: ChangementDeStatut, user: UserModel = Depends(get_user_with_selected_organization)
):
    """Le clic humain : Recette (le banc qui la prouve est exigé), Rejeté (la raison est gardée), ou retour à Candidat."""
    auteur = await _equipe(user)
    try:
        return await service.marquer(
            famille, slug, demande.version, Statut(demande.statut), auteur, banc=demande.banc, raison=demande.raison
        )
    except ErreurBibliotheque as erreur:
        raise _refus(erreur) from None
