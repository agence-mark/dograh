"""[.mark] Bibliothèque : la fiche d'une famille, lue par le builder avant de chercher ou d'écrire (E49).

Trois champs : ``description`` (ce que c'est), ``quand`` (quand s'en servir), ``comment`` (comment écrire un élément).
Stockée comme donnée (``MARK_BIBLIO_FICHES``, organisation .mark, aucune migration) pour TOUTES les familles, celles du code
comme celles créées à l'écran. Versée au départ depuis ``versement/fiches-familles.json`` ; la modifier (à l'écran, ou par
une proposition du builder qu'une personne accepte) ne touche ni l'identité de la famille ni la forme lue par le code.
"""

from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field

from api.services.builder import stock
from api.services.builder.constantes import CLE_FICHES, organisation_bibliotheque

FICHIER_DE_DEPART = Path(__file__).resolve().parent.parent / "versement" / "fiches-familles.json"


class Fiche(BaseModel):
    description: str = Field(default="", max_length=1000)
    quand: str = Field(default="", max_length=600)
    comment: str = Field(default="", max_length=1500)


class ErreurFiche(Exception):
    def __init__(self, message: str, statut: int = 422):
        super().__init__(message)
        self.statut = statut


@lru_cache(maxsize=1)
def fiches_de_depart() -> dict[str, dict[str, str]]:
    return dict(json.loads(FICHIER_DE_DEPART.read_text(encoding="utf-8"))["fiches"])


async def _stockees() -> dict[str, Any]:
    org = organisation_bibliotheque()
    brut = await stock.lire(org, CLE_FICHES) if org is not None else None
    return dict((brut or {}).get("fiches") or {})


async def toutes() -> dict[str, Fiche]:
    """La fiche de chaque famille connue d'un côté ou de l'autre : la fiche écrite d'abord, celle de départ sinon."""
    stockees = await _stockees()
    sortie = {slug: Fiche.model_validate(f) for slug, f in fiches_de_depart().items()}
    for slug, f in stockees.items():
        sortie[slug] = Fiche.model_validate(f)
    return sortie


async def lire(slug: str) -> Fiche:
    return (await toutes()).get(slug, Fiche())


async def ecrire(slug: str, fiche: Fiche) -> Fiche:
    org = organisation_bibliotheque()
    if org is None:
        raise ErreurFiche("The library organization is not configured (MARK_BIBLIOTHEQUE_ORGANISATION_ID).", 503)

    def poser(brut: dict[str, Any] | None) -> dict[str, Any]:
        fiches = dict((brut or {}).get("fiches") or {})
        fiches[slug] = fiche.model_dump()
        return {"fiches": fiches}

    try:
        await stock.modifier(org, CLE_FICHES, poser)
    except stock.ConflitDEcriture:
        raise ErreurFiche("The sheets keep changing: try again.", 409) from None
    return fiche


async def supprimer(slug: str) -> None:
    org = organisation_bibliotheque()
    if org is None:
        return

    def retirer(brut: dict[str, Any] | None) -> dict[str, Any] | None:
        fiches = dict((brut or {}).get("fiches") or {})
        if slug not in fiches:
            return None
        del fiches[slug]
        return {"fiches": fiches}

    await stock.modifier(org, CLE_FICHES, retirer)


async def verser_celles_de_depart() -> list[str]:
    """Écrit la fiche de départ des familles qui n'en ont pas encore de stockée. Une fiche déjà écrite (ou corrigée par une
    personne) n'est JAMAIS remplacée. Rend les familles écrites. Idempotent."""
    org = organisation_bibliotheque()
    if org is None:
        return []
    ecrites: list[str] = []

    def completer(brut: dict[str, Any] | None) -> dict[str, Any] | None:
        fiches = dict((brut or {}).get("fiches") or {})
        manquantes = [slug for slug in fiches_de_depart() if slug not in fiches]
        ecrites[:] = manquantes
        if not manquantes:
            return None
        for slug in manquantes:
            fiches[slug] = Fiche.model_validate(fiches_de_depart()[slug]).model_dump()
        return {"fiches": fiches}

    await stock.modifier(org, CLE_FICHES, completer)
    return ecrites
