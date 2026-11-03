"""[.mark] Bibliothèque : les familles créées à l'écran (E49), à côté de celles du code.

Une famille du code (``familles.py``) est lue ou appliquée par un mécanisme : son identité et sa forme sont verrouillées. Une
famille **créée** n'est qu'un rayon de plus : toujours en mode « fournit » (le builder lit le contenu et l'écrit lui-même
avec ses actions de construction), contenu en texte libre. Elle se supprime quand elle est vide. Une famille qu'un
mécanisme doit LIRE ou APPLIQUER reste du code : on n'en crée pas ici.

Rangement : ``MARK_BIBLIO_FAMILLES`` dans l'organisation .mark, aucune migration.
"""

from __future__ import annotations

import re
from typing import Any

from api.services.builder import stock
from api.services.builder.bibliotheque.familles import FAMILLES, MODE_FOURNIT, Famille
from api.services.builder.constantes import CLE_FAMILLES, PREFIXE_BIBLIO, organisation_bibliotheque

GROUPES = ("construit", "travaille", "regle", "suit", "site", "prouve", "guide")
SLUG = re.compile(r"^[a-z0-9][a-z0-9-]{0,39}$")


class ErreurFamille(Exception):
    def __init__(self, message: str, statut: int = 422):
        super().__init__(message)
        self.statut = statut


async def libres() -> dict[str, Famille]:
    org = organisation_bibliotheque()
    brut = await stock.lire(org, CLE_FAMILLES) if org is not None else None
    sortie: dict[str, Famille] = {}
    for slug, f in ((brut or {}).get("familles") or {}).items():
        if slug in FAMILLES or not isinstance(f, dict):
            continue
        sortie[slug] = Famille(slug, str(f.get("libelle") or slug), str(f.get("groupe") or "guide"), str(f.get("cible") or "builder"), MODE_FOURNIT)
    return sortie


async def toutes() -> dict[str, Famille]:
    """Les familles du code, puis celles créées à l'écran."""
    return {**FAMILLES, **await libres()}


async def trouver(slug: str) -> Famille | None:
    return FAMILLES.get(slug) or (await libres()).get(slug)


def est_du_code(slug: str) -> bool:
    return slug in FAMILLES


def _verifier(slug: str, libelle: str, groupe: str, cible: str) -> tuple[str, str, str]:
    if not SLUG.match(slug or ""):
        raise ErreurFamille("A family slug is lowercase letters, digits and dashes (40 at most).")
    libelle, cible = " ".join((libelle or "").split()), " ".join((cible or "").split())
    if not libelle or len(libelle) > 80:
        raise ErreurFamille("A family needs a name (80 characters at most).")
    if groupe not in GROUPES:
        raise ErreurFamille(f"Unknown group (expected: {', '.join(GROUPES)}).")
    return libelle, groupe, cible[:120] or "builder"


async def creer(slug: str, libelle: str, groupe: str = "guide", cible: str = "builder") -> Famille:
    org = organisation_bibliotheque()
    if org is None:
        raise ErreurFamille("The library organization is not configured (MARK_BIBLIOTHEQUE_ORGANISATION_ID).", 503)
    if slug in FAMILLES:
        raise ErreurFamille(f"« {slug} » is a family of the code: it already exists.", 409)
    libelle, groupe, cible = _verifier(slug, libelle, groupe, cible)

    def ajouter(brut: dict[str, Any] | None) -> dict[str, Any]:
        familles = dict((brut or {}).get("familles") or {})
        if slug in familles:
            raise ErreurFamille(f"The family « {slug} » already exists.", 409)
        if any(str(f.get("libelle", "")).casefold() == libelle.casefold() for f in familles.values()) or any(
            f.libelle.casefold() == libelle.casefold() for f in FAMILLES.values()
        ):
            raise ErreurFamille(f"A family is already named « {libelle} ».", 409)
        familles[slug] = {"libelle": libelle, "groupe": groupe, "cible": cible}
        return {"familles": familles}

    await _ecrire(org, ajouter)
    return Famille(slug, libelle, groupe, cible, MODE_FOURNIT)


async def renommer(slug: str, libelle: str) -> Famille:
    """Le nom d'une famille CRÉÉE seulement : celle du code garde son identité."""
    if est_du_code(slug):
        raise ErreurFamille(f"« {slug} » is a family of the code: its name and group are locked.", 403)
    org = organisation_bibliotheque()
    if org is None:
        raise ErreurFamille("The library organization is not configured (MARK_BIBLIOTHEQUE_ORGANISATION_ID).", 503)
    nom, _, _ = _verifier(slug, libelle, "guide", "builder")

    def changer(brut: dict[str, Any] | None) -> dict[str, Any]:
        familles = dict((brut or {}).get("familles") or {})
        if slug not in familles:
            raise ErreurFamille(f"Unknown family: {slug}.", 404)
        familles[slug] = {**familles[slug], "libelle": nom}
        return {"familles": familles}

    await _ecrire(org, changer)
    return (await libres())[slug]


async def supprimer(slug: str) -> None:
    if est_du_code(slug):
        raise ErreurFamille(f"« {slug} » is a family of the code: it cannot be deleted.", 403)
    org = organisation_bibliotheque()
    if org is None:
        raise ErreurFamille("The library organization is not configured (MARK_BIBLIOTHEQUE_ORGANISATION_ID).", 503)
    if await stock.lister(org, f"{PREFIXE_BIBLIO}{slug}:"):
        raise ErreurFamille("The family still holds elements: move or delete them first.", 409)

    def retirer(brut: dict[str, Any] | None) -> dict[str, Any]:
        familles = dict((brut or {}).get("familles") or {})
        if slug not in familles:
            raise ErreurFamille(f"Unknown family: {slug}.", 404)
        del familles[slug]
        return {"familles": familles}

    await _ecrire(org, retirer)


async def _ecrire(org: int, transformer) -> None:
    try:
        await stock.modifier(org, CLE_FAMILLES, transformer)
    except stock.ConflitDEcriture:
        raise ErreurFamille("The families keep changing: try again.", 409) from None
