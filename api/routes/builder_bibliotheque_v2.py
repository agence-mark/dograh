"""[.mark] La bibliothèque v2 (``/builder/bibliotheque``), U7 : familles créées à l'écran, fiches, sous-dossiers, étiquettes,
recherche paginée, dépôt de documents.

Montée AVANT les routes à paramètres de ``builder_bibliotheque.py`` (``/{famille}/{slug}``) : les chemins fixes passent d'abord.
LECTURE : toute personne connectée. ÉCRITURE : l'équipe .mark seulement (``droits``), comme le reste de la bibliothèque.

- ``GET /familles`` · ``POST /familles`` · ``PUT /familles/{famille}`` · ``DELETE /familles/{famille}``  les familles et leur fiche ;
- ``GET|POST|DELETE /familles/{famille}/dossiers``                                                          les sous-dossiers ;
- ``GET|POST|PUT|DELETE /etiquettes``                                                                        les étiquettes libres ;
- ``GET /parcourir``                                                                                         la liste paginée et la recherche ;
- ``POST /depot``                                                                                            PDF, Word ou Markdown déposé, en Candidat ;
- ``POST /{famille}/{slug}/rangement``                                                                       sous-dossier et étiquettes d'un élément.
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, UploadFile
from pydantic import BaseModel, Field

from api.db.models import UserModel
from api.services.auth.depends import get_user_with_selected_organization
from api.services.builder.bibliotheque import depot, droits, familles_libres, fiches, rangement, service
from api.services.builder.bibliotheque.modele import Element, Resume, Statut
from api.services.builder.bibliotheque.service import ErreurBibliotheque

router = APIRouter()


def _refus(erreur: Exception) -> HTTPException:
    return HTTPException(status_code=getattr(erreur, "statut", 422), detail=str(erreur))


async def _equipe(user: UserModel) -> str:
    try:
        await droits.exiger_l_equipe_au_labo(user)
    except ErreurBibliotheque as erreur:
        raise _refus(erreur) from None
    return droits.nom_de_l_auteur(user)


# --- les familles et leur fiche ----------------------------------------------------------------------------------


class VueFamille(BaseModel):
    slug: str
    libelle: str
    groupe: str
    cible: str
    mode: str
    du_code: bool = True  # une famille du code a son identité et sa forme verrouillées ; une famille créée à l'écran, non
    fiche: fiches.Fiche = Field(default_factory=fiches.Fiche)


def _vue(famille, fiche: fiches.Fiche) -> VueFamille:
    return VueFamille(
        slug=famille.slug,
        libelle=famille.libelle,
        groupe=famille.groupe,
        cible=famille.cible,
        mode=famille.mode,
        du_code=familles_libres.est_du_code(famille.slug),
        fiche=fiche,
    )


@router.get("/familles", response_model=list[VueFamille])
async def lister_les_familles(user: UserModel = Depends(get_user_with_selected_organization)):
    """Les familles du code, puis celles créées à l'écran, chacune avec sa fiche (lue par le builder)."""
    toutes_les_fiches = await fiches.toutes()
    return [_vue(f, toutes_les_fiches.get(f.slug, fiches.Fiche())) for f in (await familles_libres.toutes()).values()]


class NouvelleFamille(BaseModel):
    slug: str = Field(pattern=r"^[a-z0-9][a-z0-9-]{0,39}$")
    libelle: str = Field(min_length=1, max_length=80)
    groupe: str = "guide"
    cible: str = Field(default="builder", max_length=120)
    fiche: fiches.Fiche | None = None


@router.post("/familles", response_model=VueFamille, status_code=201)
async def creer_une_famille(demande: NouvelleFamille, user: UserModel = Depends(get_user_with_selected_organization)):
    """Une famille de plus, sans toucher au code : toujours en mode « fournit », contenu en texte libre."""
    await _equipe(user)
    try:
        famille = await familles_libres.creer(demande.slug, demande.libelle, demande.groupe, demande.cible)
        fiche = await fiches.ecrire(demande.slug, demande.fiche) if demande.fiche else fiches.Fiche()
    except (familles_libres.ErreurFamille, fiches.ErreurFiche) as erreur:
        raise _refus(erreur) from None
    return _vue(famille, fiche)


class ChangementDeFamille(BaseModel):
    libelle: str | None = Field(default=None, min_length=1, max_length=80)
    fiche: fiches.Fiche | None = None


@router.put("/familles/{famille}", response_model=VueFamille)
async def modifier_une_famille(
    famille: str, demande: ChangementDeFamille, user: UserModel = Depends(get_user_with_selected_organization)
):
    """La fiche d'une famille (toutes) et le nom d'une famille CRÉÉE (celle du code garde son identité)."""
    await _equipe(user)
    try:
        trouvee = await familles_libres.trouver(famille)
        if trouvee is None:
            raise HTTPException(status_code=404, detail=f"Unknown family: {famille}.")
        if demande.libelle is not None:
            trouvee = await familles_libres.renommer(famille, demande.libelle)
        fiche = await fiches.ecrire(famille, demande.fiche) if demande.fiche is not None else await fiches.lire(famille)
    except (familles_libres.ErreurFamille, fiches.ErreurFiche) as erreur:
        raise _refus(erreur) from None
    return _vue(trouvee, fiche)


@router.delete("/familles/{famille}", status_code=204)
async def supprimer_une_famille(famille: str, user: UserModel = Depends(get_user_with_selected_organization)):
    """Une famille créée à l'écran, et seulement quand elle est vide."""
    await _equipe(user)
    try:
        await familles_libres.supprimer(famille)
        await fiches.supprimer(famille)
    except (familles_libres.ErreurFamille, fiches.ErreurFiche) as erreur:
        raise _refus(erreur) from None


# --- les sous-dossiers --------------------------------------------------------------------------------------------


class NomDossier(BaseModel):
    chemin: str = Field(min_length=1, max_length=200)


@router.get("/familles/{famille}/dossiers", response_model=list[str])
async def lister_les_dossiers(famille: str, user: UserModel = Depends(get_user_with_selected_organization)):
    try:
        return await rangement.dossiers_de(famille)
    except ErreurBibliotheque as erreur:
        raise _refus(erreur) from None


@router.post("/familles/{famille}/dossiers", response_model=list[str], status_code=201)
async def creer_un_dossier(famille: str, demande: NomDossier, user: UserModel = Depends(get_user_with_selected_organization)):
    await _equipe(user)
    try:
        await rangement.creer_dossier(famille, demande.chemin)
        return await rangement.dossiers_de(famille)
    except ErreurBibliotheque as erreur:
        raise _refus(erreur) from None


@router.delete("/familles/{famille}/dossiers", response_model=list[str])
async def supprimer_un_dossier(
    famille: str,
    chemin: str = Query(min_length=1, max_length=200),
    user: UserModel = Depends(get_user_with_selected_organization),
):
    """Un dossier vide seulement : un élément ne se perd jamais avec son dossier."""
    await _equipe(user)
    try:
        await rangement.supprimer_dossier(famille, chemin)
        return await rangement.dossiers_de(famille)
    except ErreurBibliotheque as erreur:
        raise _refus(erreur) from None


# --- les étiquettes -----------------------------------------------------------------------------------------------


class VueEtiquette(BaseModel):
    nom: str
    elements: int


class NomEtiquette(BaseModel):
    nom: str = Field(min_length=1, max_length=40)


@router.get("/etiquettes", response_model=list[VueEtiquette])
async def lister_les_etiquettes(user: UserModel = Depends(get_user_with_selected_organization)):
    return await rangement.etiquettes()


@router.post("/etiquettes", response_model=list[VueEtiquette], status_code=201)
async def creer_une_etiquette(demande: NomEtiquette, user: UserModel = Depends(get_user_with_selected_organization)):
    await _equipe(user)
    try:
        await rangement.creer_etiquette(demande.nom)
    except ErreurBibliotheque as erreur:
        raise _refus(erreur) from None
    return await rangement.etiquettes()


@router.put("/etiquettes", response_model=list[VueEtiquette])
async def renommer_une_etiquette(
    demande: NomEtiquette,
    ancien: str = Query(min_length=1, max_length=40),
    user: UserModel = Depends(get_user_with_selected_organization),
):
    """Le nouveau nom s'applique partout ; refusé s'il existe déjà."""
    await _equipe(user)
    try:
        await rangement.renommer_etiquette(ancien, demande.nom)
    except ErreurBibliotheque as erreur:
        raise _refus(erreur) from None
    return await rangement.etiquettes()


@router.delete("/etiquettes", response_model=list[VueEtiquette])
async def supprimer_une_etiquette(
    nom: str = Query(min_length=1, max_length=40), user: UserModel = Depends(get_user_with_selected_organization)
):
    """Retirée de tous ses éléments ; jamais un élément supprimé."""
    await _equipe(user)
    try:
        await rangement.supprimer_etiquette(nom)
    except ErreurBibliotheque as erreur:
        raise _refus(erreur) from None
    return await rangement.etiquettes()


# --- la liste paginée et la recherche -----------------------------------------------------------------------------


class PageDElements(BaseModel):
    total: int
    elements: list[Resume]


@router.get("/parcourir", response_model=PageDElements)
async def parcourir(
    famille: str | None = None,
    statut: Statut | None = None,
    dossier: str | None = None,
    etiquette: list[str] | None = Query(default=None),
    q: str = Query(default="", max_length=200),
    limite: int = Query(default=25, ge=1, le=100),
    decalage: int = Query(default=0, ge=0),
    user: UserModel = Depends(get_user_with_selected_organization),
):
    """La liste paginée (E61) : famille, statut, sous-dossier, étiquettes, et recherche dans toute la bibliothèque."""
    try:
        total, elements = await service.parcourir(
            famille, statut, dossier=dossier, etiquettes=etiquette, recherche=q, limite=limite, decalage=decalage
        )
    except ErreurBibliotheque as erreur:
        raise _refus(erreur) from None
    return PageDElements(total=total, elements=elements)


# --- le dépôt d'un document ---------------------------------------------------------------------------------------


class ResultatDepot(BaseModel):
    element: Element
    cree: bool
    comparatif: dict[str, Any] | None = None


@router.post("/depot", response_model=ResultatDepot)
async def deposer_un_document(
    famille: str = Form(),
    fichier: UploadFile = File(...),
    titre: str | None = Form(default=None),
    licence: str = Form(default="inconnue"),
    dossier: str = Form(default=""),
    etiquettes: str = Form(default="", description="Labels separated by commas."),
    user: UserModel = Depends(get_user_with_selected_organization),
):
    """Un PDF, un Word ou un Markdown déposé : converti sur place, il entre en Candidat avec son origine."""
    auteur = await _equipe(user)
    donnees = await fichier.read(depot.DEPOT_MAX_OCTETS + 1)
    try:
        rendu = await depot.deposer(
            famille,
            fichier.filename or "document",
            donnees,
            auteur,
            titre=titre,
            licence=licence,
            dossier=dossier,
            etiquettes=[e.strip() for e in etiquettes.split(",") if e.strip()],
        )
    except ErreurBibliotheque as erreur:
        raise _refus(erreur) from None
    return ResultatDepot(element=rendu["element"], cree=rendu["cree"], comparatif=rendu["comparatif"])


# --- ranger un élément --------------------------------------------------------------------------------------------


class Rangement(BaseModel):
    dossier: str | None = Field(default=None, max_length=200, description="Empty string takes the element out of its folder.")
    etiquettes: list[str] | None = Field(default=None, max_length=12)


@router.post("/{famille}/{slug}/rangement", response_model=Element)
async def ranger_un_element(
    famille: str, slug: str, demande: Rangement, user: UserModel = Depends(get_user_with_selected_organization)
):
    """Le sous-dossier et les étiquettes d'un élément. Ni nouvelle version ni changement de statut."""
    await _equipe(user)
    try:
        return await rangement.ranger(famille, slug, dossier=demande.dossier, etiquettes_posees=demande.etiquettes)
    except ErreurBibliotheque as erreur:
        raise _refus(erreur) from None


# --- copier un scénario de test type dans un agent ----------------------------------------------------------------


class CopieDeScenario(BaseModel):
    workflow_id: int
    copier_quand_meme: bool = False
    nom: str | None = Field(default=None, max_length=200)


async def _agent_de_l_organisation(user: UserModel, workflow_id: int):
    from api.db import db_client

    workflow = await db_client.get_workflow(workflow_id, organization_id=user.selected_organization_id)
    if not workflow:
        raise HTTPException(status_code=404, detail=f"Agent {workflow_id} not found.")
    return workflow


@router.post("/scenarios-types/{slug}/examiner")
async def examiner_un_scenario(
    slug: str, demande: CopieDeScenario, user: UserModel = Depends(get_user_with_selected_organization)
) -> dict[str, Any]:
    """Ce que le scénario type cite et que l'agent n'a pas (étape, outil, issue, champ de la fiche, personnage)."""
    from api.services.builder.bibliotheque import scenarios_types

    workflow = await _agent_de_l_organisation(user, demande.workflow_id)
    try:
        return await scenarios_types.examiner(workflow, user.selected_organization_id, slug)
    except ErreurBibliotheque as erreur:
        raise _refus(erreur) from None


@router.post("/scenarios-types/{slug}/copier")
async def copier_un_scenario(
    slug: str, demande: CopieDeScenario, user: UserModel = Depends(get_user_with_selected_organization)
) -> dict[str, Any]:
    """Copie le scénario type dans l'agent en test. Rien n'est copié tant que quelque chose manque, sauf « copier quand même »."""
    from api.services.builder.bibliotheque import scenarios_types

    workflow = await _agent_de_l_organisation(user, demande.workflow_id)
    try:
        return await scenarios_types.copier(
            workflow, user.selected_organization_id, slug, droits.nom_de_l_auteur(user), copier_quand_meme=demande.copier_quand_meme, nom=demande.nom
        )
    except ErreurBibliotheque as erreur:
        raise _refus(erreur) from None
