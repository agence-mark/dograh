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

import json
from typing import Any

from pydantic import ValidationError

from api.services.builder import stock
from api.services.builder.bibliotheque import familles_libres, schemas
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


async def _verifier_famille(famille: str) -> None:
    """Une famille du code, ou créée à l'écran (``familles_libres``). 404 sinon."""
    if famille not in FAMILLES and famille not in await familles_libres.libres():
        raise ErreurBibliotheque(f"Unknown family: {famille}.", 404)


def _contenu_de_la_famille(famille: str, contenu: dict[str, Any]) -> dict[str, Any]:
    """Le contenu doit avoir la forme de sa famille (``schemas``) : un contenu hors schéma est refusé avec la raison."""
    return _valider(lambda: schemas.verifier(famille, contenu))


def _valider(construire):
    try:
        return construire()
    except (ValidationError, ValueError) as erreur:
        premier = erreur.errors()[0].get("msg", "invalid") if isinstance(erreur, ValidationError) else str(erreur)
        raise ErreurBibliotheque(f"Invalid library content: {premier}") from None


async def lire_element(famille: str, slug: str) -> Element:
    """L'élément entier (toutes ses versions). 404 s'il n'existe pas ; vide si la bibliothèque n'est pas réglée."""
    await _verifier_famille(famille)
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


def _borner(element: Element) -> Element:
    # Au-delà du plafond, les plus anciennes partent (sauf la courante et celles qui portent un banc).
    versions = list(element.versions)
    protegees = {element.version_courante} | {v.numero for v in versions if v.banc is not None}
    while len(versions) > VERSIONS_MAX:
        ancienne = next((v for v in versions if v.numero not in protegees), None)
        if ancienne is None:
            raise ErreurBibliotheque(f"Too many proven versions (more than {VERSIONS_MAX}).")
        versions.remove(ancienne)
    return element.model_copy(update={"versions": versions})


async def _modifier(famille: str, slug: str, construire) -> Element:
    """Lit l'élément, applique ``construire(element | None) -> Element`` (pure : elle peut être rejouée) et écrit seulement si la
    ligne n'a pas bougé entre-temps (revue R6) : deux versions ajoutées en même temps gardent chacune leur numéro."""
    org = _organisation()
    rendu: list[Element] = []

    def transformer(brut):
        element = _valider(lambda: Element.model_validate(brut)) if brut is not None else None
        nouveau = _borner(construire(element))
        rendu[:] = [nouveau]
        return nouveau.model_dump(mode="json")

    try:
        await stock.modifier(org, cle_de(famille, slug), transformer)
    except stock.ConflitDEcriture:
        raise ErreurBibliotheque("The library element keeps changing: try again.", 409) from None
    return rendu[0]


def _existant(element: Element | None, famille: str, slug: str) -> Element:
    if element is None:
        raise ErreurBibliotheque(f"Library element not found: {famille}/{slug}.", 404)
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
    dossier: str = "",
    etiquettes: list[str] | None = None,
) -> Element:
    await _verifier_famille(famille)
    _organisation()
    _contenu_de_la_famille(famille, contenu)

    def construire(existant: Element | None) -> Element:
        if existant is not None:
            raise ErreurBibliotheque(f"Library element already exists: {famille}/{slug}.", 409)
        return _valider(
            lambda: Element(
                famille=famille,
                slug=slug,
                titre=titre,
                version_courante=1,
                versions=[Version(numero=1, auteur=auteur, notes=notes, contenu=contenu, origine=origine)],
                dossier=dossier,
                etiquettes=list(etiquettes or []),
            )
        )

    return await _modifier(famille, slug, construire)


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
    await _verifier_famille(famille)
    _contenu_de_la_famille(famille, contenu)

    def construire(brut: Element | None) -> Element:
        element = _existant(brut, famille, slug)
        numero = max(v.numero for v in element.versions) + 1
        version = _valider(
            lambda: Version(numero=numero, auteur=auteur, notes=notes, contenu=contenu, banc=banc, origine=origine)
        )
        return element.model_copy(
            update={
                "versions": [*element.versions, version],
                "version_courante": numero,
                "titre": titre or element.titre,
            }
        )

    return await _modifier(famille, slug, construire)


async def retour_arriere(famille: str, slug: str, numero: int, auteur: str) -> Element:
    """Revient à une version : en ajoute une qui reprend contenu, statut et banc de l'ancienne."""
    await _verifier_famille(famille)

    def construire(brut: Element | None) -> Element:
        element = _existant(brut, famille, slug)
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
        return element.model_copy(update={"versions": [*element.versions, restauree], "version_courante": nouveau_numero})

    return await _modifier(famille, slug, construire)


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
    await _verifier_famille(famille)
    if statut is Statut.RECETTE and banc is None:
        raise ErreurBibliotheque("A recipe is proven on a bench: give what proves it.")
    if statut is Statut.REJETE and not (raison or "").strip():
        raise ErreurBibliotheque("A rejection keeps its reason: give it.")

    def construire(brut: Element | None) -> Element:
        element = _existant(brut, famille, slug)
        cible = next((v for v in element.versions if v.numero == numero), None)
        if cible is None:
            raise ErreurBibliotheque(f"Version {numero} not found.", 404)
        mise_a_jour = {
            "statut": statut,
            "banc": banc if statut is Statut.RECETTE else cible.banc,
            "raison_rejet": (raison or "").strip() or None if statut is Statut.REJETE else None,
        }
        versions = [v.model_copy(update=mise_a_jour) if v.numero == numero else v for v in element.versions]
        return element.model_copy(update={"versions": versions})

    return await _modifier(famille, slug, construire)


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


async def elements_de(famille: str) -> list[Element]:
    """Tous les éléments d'une famille, entiers (contenu compris), dans l'ordre des identifiants. Un élément illisible est sauté.
    Pour les familles dont l'écran lit le contenu de chaque ligne (modèles de réglages) ; la liste courante ne le rend pas."""
    await _verifier_famille(famille)
    org = organisation_bibliotheque()
    if org is None:
        return []
    elements: list[Element] = []
    for _cle, brut in await stock.lister(org, f"{PREFIXE_BIBLIO}{famille}:"):
        try:
            elements.append(Element.model_validate(brut))
        except ValidationError:
            continue
    return elements


async def renommer(famille: str, slug: str, titre: str) -> Element:
    """Change le TITRE seul : ni nouvelle version ni changement de statut (renommer ne défait pas une recette)."""
    await _verifier_famille(famille)

    def construire(brut: Element | None) -> Element:
        return _valider(lambda: _existant(brut, famille, slug).model_copy(update={"titre": titre}))

    return await _modifier(famille, slug, construire)


async def supprimer(famille: str, slug: str) -> None:
    """Retire l'élément et son historique. Geste volontaire d'une personne, confirmé à l'écran ; 404 s'il n'existe pas."""
    await _verifier_famille(famille)
    org = _organisation()
    if not await stock.supprimer(org, cle_de(famille, slug)):
        raise ErreurBibliotheque(f"Library element not found: {famille}/{slug}.", 404)


def _resume(element: Element, nombres: dict[str, int], extrait: str | None = None) -> Resume:
    courante = element.courante
    return Resume(
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
        dossier=element.dossier,
        etiquettes=list(element.etiquettes),
        extrait=extrait,
    )


def _extrait(element: Element, requete: str) -> str | None:
    """Le passage du contenu courant qui contient la requête (une cinquantaine de caractères autour), ou ``None``."""
    texte = json.dumps(element.courante.contenu, ensure_ascii=False)
    place = texte.casefold().find(requete)
    if place < 0:
        return None
    debut = max(0, place - 50)
    return ("…" if debut else "") + texte[debut : place + len(requete) + 50] + ("…" if place + len(requete) + 50 < len(texte) else "")


def _correspond(element: Element, requete: str) -> tuple[bool, str | None]:
    if not requete:
        return True, None
    for champ in (element.titre, element.slug, element.dossier, *element.etiquettes):
        if requete in champ.casefold():
            return True, None
    extrait = _extrait(element, requete)
    return extrait is not None, extrait


async def parcourir(
    famille: str | None = None,
    statut: Statut | None = None,
    *,
    dossier: str | None = None,
    etiquettes: list[str] | None = None,
    recherche: str = "",
    limite: int = 25,
    decalage: int = 0,
) -> tuple[int, list[Resume]]:
    """Les éléments filtrés (famille, statut, sous-dossier et ses descendants, étiquettes toutes posées, recherche dans le titre,
    les étiquettes et le contenu), triés famille puis titre, **par page** (E61). Rend ``(total, page)``."""
    org = organisation_bibliotheque()
    if org is None:
        return 0, []
    if famille is not None:
        await _verifier_famille(famille)
    prefixe = f"{PREFIXE_BIBLIO}{famille}:" if famille else PREFIXE_BIBLIO
    requete = " ".join((recherche or "").split()).casefold()
    voulues = {e.casefold() for e in (etiquettes or [])}
    trouves: list[tuple[Element, str | None]] = []
    for _cle, brut in await stock.lister(org, prefixe):
        try:
            element = Element.model_validate(brut)
        except ValidationError:
            continue
        if statut is not None and element.statut is not statut:
            continue
        if dossier is not None and not (element.dossier == dossier or element.dossier.startswith(f"{dossier}/")):
            continue
        if voulues and not voulues <= {e.casefold() for e in element.etiquettes}:
            continue
        ok, extrait = _correspond(element, requete)
        if ok:
            trouves.append((element, extrait))
    trouves.sort(key=lambda paire: (paire[0].famille, paire[0].titre.casefold(), paire[0].slug))
    nombres = await _nombres_d_agents()
    page = trouves[max(0, decalage) : max(0, decalage) + max(1, limite)]
    return len(trouves), [_resume(e, nombres, x) for e, x in page]


async def lister(famille: str | None = None, statut: Statut | None = None) -> list[Resume]:
    """Tous les éléments (sans page) : pour le builder et les écrans qui lisent une famille entière."""
    org = organisation_bibliotheque()
    if org is None:
        return []
    if famille is not None:
        await _verifier_famille(famille)
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
        resumes.append(_resume(element, nombres))
    return resumes


async def classer(famille: str, slug: str, *, dossier: str | None = None, etiquettes: list[str] | None = None) -> Element:
    """Range un élément : son sous-dossier et/ou ses étiquettes. Ni nouvelle version, ni changement de statut."""
    await _verifier_famille(famille)

    def construire(brut: Element | None) -> Element:
        element = _existant(brut, famille, slug)
        maj: dict[str, Any] = {}
        if dossier is not None:
            maj["dossier"] = dossier
        if etiquettes is not None:
            propres: list[str] = []
            for e in etiquettes:
                if e.casefold() not in {p.casefold() for p in propres}:
                    propres.append(e)
            maj["etiquettes"] = propres
        return _valider(lambda: Element.model_validate({**element.model_dump(), **maj}))

    return await _modifier(famille, slug, construire)


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
    date = maintenant().isoformat()

    def noter(ligne: dict[str, Any] | None) -> dict[str, Any]:
        # Revue R6 : lu et réécrit sous condition, deux agents qui appliquent le même élément ensemble s'ajoutent tous les deux.
        agents = dict((ligne or {}).get("agents") or {})
        agents[f"{organization_id}:{workflow_id}"] = {"version": version, "date": date}
        return {"agents": agents}

    await stock.modifier(org, _cle_usage(famille, slug), noter)


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
