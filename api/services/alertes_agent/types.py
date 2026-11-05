"""[.mark] Les types d'alerte d'agent : le registre unique (sous-lot 6, audit 12 § 3).

Un type = un code, ses mots (français et anglais), ses seuils par défaut et leurs bornes. Ajouter un type ne demande que d'ajouter
une entrée ici et sa fonction de calcul dans ``service.CALCULS`` : réglages, rangement, notification et écran sont communs.
⛔ Zéro vocabulaire métier.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

VERSION_MOINS_BIEN = "version_moins_bien"


@dataclass(frozen=True)
class Seuil:
    """Un seuil réglable : valeur par défaut et bornes (une valeur hors bornes est ramenée aux bornes)."""

    defaut: float
    bas: float
    haut: float
    entier: bool = False


@dataclass(frozen=True)
class TypeDAlerte:
    code: str
    titre: dict[str, str]
    explication: dict[str, str]
    seuils: dict[str, Seuil] = field(default_factory=dict)


TYPES: dict[str, TypeDAlerte] = {
    VERSION_MOINS_BIEN: TypeDAlerte(
        code=VERSION_MOINS_BIEN,
        titre={"fr": "Une version fait moins bien que la précédente", "en": "A version does worse than the previous one"},
        explication={
            "fr": "Compare la dernière version en ligne à celle d'avant, sur les vrais appels : note du juge (sur 5) et part d'appels avec impasse. "
            "Elle dit et pointe vers « À améliorer » ; elle ne retire ni ne change jamais une version.",
            "en": "Compares the latest live version with the one before it, on real calls: the judge's score (out of 5) and the share of calls with a dead end. "
            "It tells and points to « To improve »; it never removes or changes a version.",
        },
        seuils={
            "baisse_note": Seuil(0.5, 0.1, 4.0),
            "hausse_impasses": Seuil(0.05, 0.01, 1.0),
            "appels_min": Seuil(10, 3, 1000, entier=True),
            "jours": Seuil(14, 2, 30, entier=True),
        },
    )
}


def seuils_par_defaut(code: str) -> dict[str, float]:
    return {nom: s.defaut for nom, s in TYPES[code].seuils.items()}


def seuils_valides(code: str, bruts: Any) -> dict[str, float]:
    """Les seuils d'un type : un nom inconnu est écarté, une valeur illisible redonne le défaut, une valeur hors bornes est ramenée aux bornes."""
    propres = seuils_par_defaut(code)
    if not isinstance(bruts, dict):
        return propres
    for nom, seuil in TYPES[code].seuils.items():
        valeur = bruts.get(nom)
        if isinstance(valeur, bool) or not isinstance(valeur, (int, float)):
            continue
        valeur = max(seuil.bas, min(seuil.haut, valeur))
        propres[nom] = int(valeur) if seuil.entier else round(float(valeur), 4)
    return propres
