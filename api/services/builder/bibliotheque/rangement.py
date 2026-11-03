"""[.mark] Bibliothèque : le rangement, c'est-à-dire les étiquettes libres et les sous-dossiers d'une famille (E49).

* **Étiquettes** : une liste libre pour toute la bibliothèque (``MARK_BIBLIO_ETIQUETTES``). Créées, posées, retirées,
  renommées (le nouveau nom s'applique partout, refusé s'il existe déjà) et supprimées (retirée de tous ses éléments,
  **jamais un élément supprimé**).
* **Sous-dossiers** : un chemin (``restauration/rendez-vous``) par élément ; la liste d'une famille réunit les chemins
  déclarés (même vides, ``MARK_BIBLIO_DOSSIERS``) et ceux que portent ses éléments. Un dossier se supprime quand il est vide.

Aucune migration : lignes de l'organisation .mark.
"""

from __future__ import annotations

import re
from typing import Any

from pydantic import ValidationError

from api.services.builder import stock
from api.services.builder.bibliotheque import service
from api.services.builder.bibliotheque.modele import DOSSIER_MOTIF, Element
from api.services.builder.bibliotheque.service import ErreurBibliotheque
from api.services.builder.constantes import CLE_DOSSIERS, CLE_ETIQUETTES, PREFIXE_BIBLIO, organisation_bibliotheque

ETIQUETTES_MAX = 200
NOM_MAX = 40


def _org() -> int:
    org = organisation_bibliotheque()
    if org is None:
        raise ErreurBibliotheque("The library organization is not configured (MARK_BIBLIOTHEQUE_ORGANISATION_ID).", 503)
    return org


def _nom(nom: str) -> str:
    propre = " ".join((nom or "").split())
    if not propre or len(propre) > NOM_MAX:
        raise ErreurBibliotheque(f"A label is 1 to {NOM_MAX} characters.")
    return propre


# --- étiquettes ---------------------------------------------------------------------------------------------------


async def etiquettes() -> list[dict[str, Any]]:
    """Chaque étiquette de la liste avec le nombre d'éléments qui la portent."""
    org = organisation_bibliotheque()
    if org is None:
        return []
    liste = list(((await stock.lire(org, CLE_ETIQUETTES)) or {}).get("etiquettes") or [])
    comptes: dict[str, int] = {}
    for _cle, brut in await stock.lister(org, PREFIXE_BIBLIO):
        for e in brut.get("etiquettes") or []:
            comptes[str(e).casefold()] = comptes.get(str(e).casefold(), 0) + 1
    return [{"nom": nom, "elements": comptes.get(nom.casefold(), 0)} for nom in sorted(liste, key=str.casefold)]


async def _modifier_liste(transformer) -> None:
    try:
        await stock.modifier(_org(), CLE_ETIQUETTES, transformer)
    except stock.ConflitDEcriture:
        raise ErreurBibliotheque("The labels keep changing: try again.", 409) from None


async def creer_etiquette(nom: str) -> str:
    """Crée l'étiquette si elle manque ; rend le nom tel qu'il est rangé (la casse de l'existante)."""
    nom = _nom(nom)
    existante: list[str] = []

    def ajouter(brut):
        liste = list((brut or {}).get("etiquettes") or [])
        deja = next((e for e in liste if e.casefold() == nom.casefold()), None)
        if deja is not None:
            existante[:] = [deja]
            return None  # déjà là : rien à écrire
        if len(liste) >= ETIQUETTES_MAX:
            raise ErreurBibliotheque(f"At most {ETIQUETTES_MAX} labels.")
        existante[:] = [nom]
        return {"etiquettes": [*liste, nom]}

    await _modifier_liste(ajouter)
    return existante[0]


async def _elements_portant(nom: str) -> list[Element]:
    portes = []
    for _cle, brut in await stock.lister(_org(), PREFIXE_BIBLIO):
        try:
            element = Element.model_validate(brut)
        except ValidationError:
            continue
        if any(e.casefold() == nom.casefold() for e in element.etiquettes):
            portes.append(element)
    return portes


async def _nom_range(nom: str) -> str:
    trouve = next((e["nom"] for e in await etiquettes() if e["nom"].casefold() == nom.casefold()), None)
    if trouve is None:
        raise ErreurBibliotheque(f"Unknown label: {nom}.", 404)
    return trouve


async def renommer_etiquette(ancien: str, nouveau: str) -> str:
    nouveau = _nom(nouveau)
    trouve = await _nom_range(ancien)
    if nouveau.casefold() != trouve.casefold() and any(e["nom"].casefold() == nouveau.casefold() for e in await etiquettes()):
        raise ErreurBibliotheque(f"A label is already named « {nouveau} ».", 409)

    def renommer(brut):
        return {"etiquettes": [nouveau if e.casefold() == trouve.casefold() else e for e in (brut or {}).get("etiquettes") or []]}

    await _modifier_liste(renommer)
    for element in await _elements_portant(trouve):
        await service.classer(
            element.famille,
            element.slug,
            etiquettes=[nouveau if e.casefold() == trouve.casefold() else e for e in element.etiquettes],
        )
    return nouveau


async def supprimer_etiquette(nom: str) -> int:
    """Retire l'étiquette de la liste et de tous ses éléments (jamais un élément). Rend le nombre d'éléments concernés."""
    trouve = await _nom_range(nom)
    portes = await _elements_portant(trouve)
    for element in portes:
        await service.classer(
            element.famille, element.slug, etiquettes=[e for e in element.etiquettes if e.casefold() != trouve.casefold()]
        )

    def retirer(brut):
        return {"etiquettes": [e for e in (brut or {}).get("etiquettes") or [] if e.casefold() != trouve.casefold()]}

    await _modifier_liste(retirer)
    return len(portes)


# --- sous-dossiers ------------------------------------------------------------------------------------------------


def _chemin(chemin: str) -> str:
    propre = (chemin or "").strip().strip("/")
    if not propre or not re.match(DOSSIER_MOTIF, propre):
        raise ErreurBibliotheque("A folder is lowercase letters, digits and dashes, up to 4 levels separated by « / ».")
    return propre


async def dossiers_de(famille: str) -> list[str]:
    """Les sous-dossiers d'une famille : déclarés ou portés par un élément, avec leurs parents, triés."""
    await service._verifier_famille(famille)
    org = organisation_bibliotheque()
    if org is None:
        return []
    chemins = set((((await stock.lire(org, CLE_DOSSIERS)) or {}).get("dossiers") or {}).get(famille) or [])
    for _cle, brut in await stock.lister(org, f"{PREFIXE_BIBLIO}{famille}:"):
        if brut.get("dossier"):
            chemins.add(brut["dossier"])
    tous: set[str] = set()
    for c in chemins:
        morceaux = c.split("/")
        tous.update("/".join(morceaux[: i + 1]) for i in range(len(morceaux)))
    return sorted(tous)


async def creer_dossier(famille: str, chemin: str) -> str:
    await service._verifier_famille(famille)
    chemin = _chemin(chemin)

    def ajouter(brut):
        dossiers = dict((brut or {}).get("dossiers") or {})
        liste = list(dossiers.get(famille) or [])
        if chemin in liste:
            return None
        dossiers[famille] = [*liste, chemin]
        return {"dossiers": dossiers}

    try:
        await stock.modifier(_org(), CLE_DOSSIERS, ajouter)
    except stock.ConflitDEcriture:
        raise ErreurBibliotheque("The folders keep changing: try again.", 409) from None
    return chemin


async def supprimer_dossier(famille: str, chemin: str) -> None:
    """Seulement un dossier vide (sans élément, sans sous-dossier) : un élément ne se perd jamais avec son dossier."""
    await service._verifier_famille(famille)
    chemin = _chemin(chemin)
    connus = await dossiers_de(famille)
    if chemin not in connus:
        raise ErreurBibliotheque(f"Unknown folder: {chemin}.", 404)
    for _cle, brut in await stock.lister(_org(), f"{PREFIXE_BIBLIO}{famille}:"):
        porte = str(brut.get("dossier") or "")
        if porte == chemin or porte.startswith(f"{chemin}/"):
            raise ErreurBibliotheque("The folder still holds elements: move them first.", 409)
    if any(d.startswith(f"{chemin}/") for d in connus):
        raise ErreurBibliotheque("The folder still holds sub-folders: remove them first.", 409)

    def retirer(brut):
        dossiers = dict((brut or {}).get("dossiers") or {})
        dossiers[famille] = [d for d in dossiers.get(famille) or [] if d != chemin]
        return {"dossiers": dossiers}

    await stock.modifier(_org(), CLE_DOSSIERS, retirer)


# --- ranger un élément --------------------------------------------------------------------------------------------


async def ranger(famille: str, slug: str, *, dossier: str | None = None, etiquettes_posees: list[str] | None = None) -> Element:
    """Pose le sous-dossier et/ou les étiquettes d'un élément (« » vide le sous-dossier). Une étiquette inconnue est créée au passage."""
    if dossier:
        dossier = _chemin(dossier)
        await creer_dossier(famille, dossier)
    noms = None
    if etiquettes_posees is not None:
        noms = [await creer_etiquette(n) for n in etiquettes_posees]
    return await service.classer(famille, slug, dossier=dossier, etiquettes=noms)
