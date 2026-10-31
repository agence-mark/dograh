"""[.mark] Bibliothèque : créer, versionner, lire, revenir en arrière, changer de statut.

Une ligne par élément (``MARK_BIBLIO:<famille>:<slug>``) dans l'organisation .mark. Toute personne peut LIRE
(l'écran ne vérifie rien d'autre que la connexion) ; ``droits`` décide qui écrit. Les erreurs de règle sont
des ``ErreurBibliotheque`` avec un code HTTP que la route traduit.

Règles tenues ici, pas dans la route :

* un retour arrière **ajoute** une version qui reprend le contenu (et le statut, le banc) de l'ancienne :
  l'historique ne perd rien ;
* le passage en **Recette** exige un banc écrit (« banc réussi + clic humain », B35) ;
* un **Rejet** exige une raison, gardée ;
* au-delà de ``VERSIONS_MAX`` versions, les plus anciennes partent, sauf la courante et celles qui portent
  un banc ;
* un candidat ou une recette modifiée devient une NOUVELLE version, toujours Candidat : une recette
  modifiée n'est plus prouvée.
"""

from __future__ import annotations

from typing import Any

from pydantic import ValidationError

from api.services.builder import stock
from api.services.builder.bibliotheque.familles import FAMILLES
from api.services.builder.bibliotheque.modele import (
    Banc,
    Element,
    Origine,
    Resume,
    Statut,
    Version,
    maintenant,
)
from api.services.builder.constantes import (
    PREFIXE_BIBLIO,
    PREFIXE_USAGE,
    VERSIONS_MAX,
    organisation_bibliotheque,
)


class ErreurBibliotheque(Exception):
    def __init__(self, message: str, statut: int = 422):
        super().__init__(message)
        self.statut = statut


def cle_de(famille: str, slug: str) -> str:
    return f"{PREFIXE_BIBLIO}{famille}:{slug}"


def _organisation() -> int:
    org = organisation_bibliotheque()
    if org is None:
        raise ErreurBibliotheque("The library organization is not configured (MARK_BIBLIOTHEQUE_ORGANISATION_ID).", 503)
    return org


def _verifier_famille(famille: str) -> None:
    if famille not in FAMILLES:
        raise ErreurBibliotheque(f"Unknown family: {famille}.", 404)


def _valider(construire):
    try:
        return construire()
    except (ValidationError, ValueError) as erreur:
        premier = erreur.errors()[0].get("msg", "invalid") if isinstance(erreur, ValidationError) else str(erreur)
        raise ErreurBibliotheque(f"Invalid library content: {premier}") from None


async def lire_element(famille: str, slug: str) -> Element:
    """L'élément entier (toutes ses versions). 404 s'il n'existe pas ; vide si la bibliothèque n'est pas réglée."""
    _verifier_famille(famille)
    org = organisation_bibliotheque()
    brut = await stock.lire(org, cle_de(famille, slug)) if org is not None else None
    if brut is None:
        raise ErreurBibliotheque(f"Library element not found: {famille}/{slug}.", 404)
    return _valider(lambda: Element.model_validate(brut))


async def element_ou_none(famille: str, slug: str) -> Element | None:
    try:
        return await lire_element(famille, slug)
    except ErreurBibliotheque as erreur:
        if erreur.statut == 404:
            return None
        raise


async def _ecrire(element: Element) -> Element:
    # Au-delà du plafond, les plus anciennes partent (sauf la courante et celles qui portent un banc).
    versions = list(element.versions)
    protegees = {element.version_courante} | {v.numero for v in versions if v.banc is not None}
    while len(versions) > VERSIONS_MAX:
        ancienne = next((v for v in versions if v.numero not in protegees), None)
        if ancienne is None:
            raise ErreurBibliotheque(f"Too many proven versions (more than {VERSIONS_MAX}).")
        versions.remove(ancienne)
    element = element.model_copy(update={"versions": versions})
    await stock.ecrire(_organisation(), cle_de(element.famille, element.slug), element.model_dump(mode="json"))
    return element


async def creer(
    famille: str,
    slug: str,
    titre: str,
    contenu: dict[str, Any],
    auteur: str,
    *,
    notes: str = "",
    origine: Origine | None = None,
) -> Element:
    _verifier_famille(famille)
    _organisation()
    if await element_ou_none(famille, slug) is not None:
        raise ErreurBibliotheque(f"Library element already exists: {famille}/{slug}.", 409)
    element = _valider(
        lambda: Element(
            famille=famille,
            slug=slug,
            titre=titre,
            version_courante=1,
            versions=[Version(numero=1, auteur=auteur, notes=notes, contenu=contenu, origine=origine)],
        )
    )
    return await _ecrire(element)


async def ajouter_version(
    famille: str,
    slug: str,
    contenu: dict[str, Any],
    auteur: str,
    *,
    notes: str = "",
    banc: Banc | None = None,
    origine: Origine | None = None,
    titre: str | None = None,
) -> Element:
    """Une nouvelle version, toujours Candidat (ou Recette si un banc est donné ET demandé via ``marquer``)."""
    element = await lire_element(famille, slug)
    numero = max(v.numero for v in element.versions) + 1
    version = _valider(
        lambda: Version(numero=numero, auteur=auteur, notes=notes, contenu=contenu, banc=banc, origine=origine)
    )
    nouveau = element.model_copy(
        update={
            "versions": [*element.versions, version],
            "version_courante": numero,
            "titre": titre or element.titre,
        }
    )
    return await _ecrire(nouveau)


async def retour_arriere(famille: str, slug: str, numero: int, auteur: str) -> Element:
    """Revient à une version : en ajoute une qui reprend contenu, statut et banc de l'ancienne."""
    element = await lire_element(famille, slug)
    ancienne = next((v for v in element.versions if v.numero == numero), None)
    if ancienne is None:
        raise ErreurBibliotheque(f"Version {numero} not found.", 404)
    nouveau_numero = max(v.numero for v in element.versions) + 1
    restauree = ancienne.model_copy(
        update={
            "numero": nouveau_numero,
            "auteur": auteur,
            "date": maintenant(),
            "notes": f"Retour à la version {numero}.",
            "restaure_de": numero,
        }
    )
    nouveau = element.model_copy(
        update={"versions": [*element.versions, restauree], "version_courante": nouveau_numero}
    )
    return await _ecrire(nouveau)


async def marquer(
    famille: str,
    slug: str,
    numero: int,
    statut: Statut,
    auteur: str,
    *,
    banc: Banc | None = None,
    raison: str | None = None,
) -> Element:
    """Passe une version en Recette (banc exigé) ou Rejeté (raison exigée). Geste humain : le builder ne l'a pas."""
    element = await lire_element(famille, slug)
    cible = next((v for v in element.versions if v.numero == numero), None)
    if cible is None:
        raise ErreurBibliotheque(f"Version {numero} not found.", 404)
    if statut is Statut.RECETTE and banc is None:
        raise ErreurBibliotheque("A recipe is proven on a bench: give what proves it.")
    if statut is Statut.REJETE and not (raison or "").strip():
        raise ErreurBibliotheque("A rejection keeps its reason: give it.")
    mise_a_jour = {
        "statut": statut,
        "banc": banc if statut is Statut.RECETTE else cible.banc,
        "raison_rejet": (raison or "").strip() or None if statut is Statut.REJETE else None,
    }
    versions = [v.model_copy(update=mise_a_jour) if v.numero == numero else v for v in element.versions]
    return await _ecrire(element.model_copy(update={"versions": versions}))


async def ecrire_candidat(
    famille: str,
    slug: str,
    titre: str,
    contenu: dict[str, Any],
    auteur: str,
    *,
    notes: str = "",
) -> Element:
    """Ce que le BUILDER a le droit d'écrire : un candidat neuf, ou une version Candidat d'un candidat.

    Une recette n'est jamais modifiée par le builder (il propose) ; un élément rejeté non plus."""
    existant = await element_ou_none(famille, slug)
    if existant is None:
        return await creer(famille, slug, titre, contenu, auteur, notes=notes)
    if existant.statut is not Statut.CANDIDAT:
        raise ErreurBibliotheque(
            f"« {famille}/{slug} » is a {existant.statut.value}: the builder only edits candidates. Propose a new version.",
            403,
        )
    return await ajouter_version(famille, slug, contenu, auteur, notes=notes, titre=titre)


async def lister(famille: str | None = None, statut: Statut | None = None) -> list[Resume]:
    org = organisation_bibliotheque()
    if org is None:
        return []
    if famille is not None:
        _verifier_famille(famille)
    prefixe = f"{PREFIXE_BIBLIO}{famille}:" if famille else PREFIXE_BIBLIO
    resumes: list[Resume] = []
    nombres = await _nombres_d_agents()  # revue R4 : une seule lecture, plus une par élément
    for _cle, brut in await stock.lister(org, prefixe):
        try:
            element = Element.model_validate(brut)
        except ValidationError:
            continue
        if statut is not None and element.statut is not statut:
            continue
        courante = element.courante
        resumes.append(
            Resume(
                famille=element.famille,
                slug=element.slug,
                titre=element.titre,
                statut=element.statut,
                version_courante=element.version_courante,
                auteur=courante.auteur,
                date=courante.date,
                banc=courante.banc,
                origine=courante.origine,
                utilisee_par=nombres.get(_cle_usage(element.famille, element.slug), 0),
            )
        )
    return resumes


# --- « utilisée par N agents » ------------------------------------------------------------------------------


def _cle_usage(famille: str, slug: str) -> str:
    return f"{PREFIXE_USAGE}{famille}:{slug}"


async def enregistrer_utilisation(
    famille: str, slug: str, version: int, organization_id: int, workflow_id: int
) -> None:
    """Note qu'un agent utilise cette version (appelé quand le builder applique un élément). Écrit par le code,
    dans l'organisation .mark, pour que le compte se lise sans parcourir les organisations des clients."""
    org = organisation_bibliotheque()
    if org is None:
        return
    ligne = await stock.lire(org, _cle_usage(famille, slug)) or {"agents": {}}
    agents = dict(ligne.get("agents") or {})
    agents[f"{organization_id}:{workflow_id}"] = {"version": version, "date": maintenant().isoformat()}
    await stock.ecrire(org, _cle_usage(famille, slug), {"agents": agents})


async def utilisation(famille: str, slug: str) -> list[dict[str, Any]]:
    org = organisation_bibliotheque()
    if org is None:
        return []
    ligne = await stock.lire(org, _cle_usage(famille, slug)) or {}
    return [
        {"organisation": int(cle.split(":")[0]), "agent": int(cle.split(":")[1]), "version": valeur.get("version")}
        for cle, valeur in sorted((ligne.get("agents") or {}).items())
    ]


async def _nombres_d_agents() -> dict[str, int]:
    """Le nombre d'agents de chaque élément, en UNE lecture filtrée par préfixe (clé d'usage -> nombre)."""
    org = organisation_bibliotheque()
    if org is None:
        return {}
    return {cle: len((valeur.get("agents") or {})) for cle, valeur in await stock.lister(org, PREFIXE_USAGE)}


async def nombre_d_agents(famille: str, slug: str) -> int:
    return len(await utilisation(famille, slug))
