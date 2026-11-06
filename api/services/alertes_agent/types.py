"""[.mark] Les types d'alerte d'agent : le registre unique (sous-lot 6, audit 12 § 3).

Un type = un code, ses mots (français et anglais), ses seuils par défaut et leurs bornes. Ajouter un type ne demande que d'ajouter
une entrée ici et sa fonction de calcul dans ``service.CALCULS`` : réglages, rangement, notification et écran sont communs.
⛔ Zéro vocabulaire métier.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

VERSION_MOINS_BIEN = "version_moins_bien"
# Partie 3, L3e : les alertes sur les vrais appels, une période contre la précédente (``appels.py``). Mêmes réglages, même rangement,
# même notification : des entrées de ce registre, jamais un second mécanisme.
HAUSSE_RATES = "hausse_rates"
HAUSSE_TRANSFERTS = "hausse_transferts"
HAUSSE_GARDE_FOUS = "hausse_garde_fous"
HAUSSE_PANNES = "hausse_pannes"
HAUSSE_LATENCE = "hausse_latence"
TYPES_DES_APPELS = (HAUSSE_RATES, HAUSSE_TRANSFERTS, HAUSSE_GARDE_FOUS, HAUSSE_PANNES, HAUSSE_LATENCE)


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


def _seuils_des_appels(hausse: float) -> dict[str, Seuil]:
    """Les trois seuils de tout signal des vrais appels : hausse relative (%), appels au minimum de chaque période, durée d'une période
    (en jours : 1, 7 ou 30 à l'écran). ``cas_min`` : le nombre d'appels concernés sans lequel une hausse n'est que du bruit."""
    return {
        "hausse": Seuil(hausse, 1, 1000),
        "appels_min": Seuil(10, 1, 1000, entier=True),
        "jours": Seuil(7, 1, 30, entier=True),
        "cas_min": Seuil(3, 1, 1000, entier=True),
    }


def _un_signal(code: str, fr: str, en: str, explication_fr: str, explication_en: str, hausse: float) -> TypeDAlerte:
    return TypeDAlerte(
        code=code,
        titre={"fr": fr, "en": en},
        explication={"fr": explication_fr, "en": explication_en},
        seuils=_seuils_des_appels(hausse),
    )


_PAS_DE_MODELE_FR = " Calculée après l'appel sur ce qui est déjà rangé : aucun appel à un modèle, aucune dépense."
_PAS_DE_MODELE_EN = " Computed after the call from what is already stored: no model call, no spend."

TYPES.update(
    {
        t.code: t
        for t in (
            _un_signal(
                HAUSSE_RATES,
                "Le juge relève plus d'appels ratés",
                "The judge flags more failed calls",
                "Part des appels jugés avec au moins un critère raté, comparée à la période de même durée qui précède." + _PAS_DE_MODELE_FR,
                "Share of judged calls with at least one failed criterion, compared with the period of the same length before it." + _PAS_DE_MODELE_EN,
                50,
            ),
            _un_signal(
                HAUSSE_TRANSFERTS,
                "Plus d'appels transférés",
                "More calls are transferred",
                "Part des appels terminés par un transfert, comparée à la période précédente." + _PAS_DE_MODELE_FR,
                "Share of calls that ended in a transfer, compared with the previous period." + _PAS_DE_MODELE_EN,
                50,
            ),
            _un_signal(
                HAUSSE_GARDE_FOUS,
                "Plus de garde-fous déclenchés",
                "More safeguards triggered",
                "Part des appels où un garde-fou de sécurité s'est déclenché, comparée à la période précédente." + _PAS_DE_MODELE_FR,
                "Share of calls where a safety safeguard triggered, compared with the previous period." + _PAS_DE_MODELE_EN,
                50,
            ),
            _un_signal(
                HAUSSE_PANNES,
                "Plus d'appels touchés par une panne",
                "More calls hit by an outage",
                "Part des appels où l'agent a basculé en repli de panne, comparée à la période précédente." + _PAS_DE_MODELE_FR,
                "Share of calls where the agent fell back to the outage plan, compared with the previous period." + _PAS_DE_MODELE_EN,
                50,
            ),
            _un_signal(
                HAUSSE_LATENCE,
                "L'agent répond plus lentement",
                "The agent answers more slowly",
                "Latence médiane des tours de parole, quand elle est mesurée, comparée à la période précédente." + _PAS_DE_MODELE_FR,
                "Median turn latency, when it is measured, compared with the previous period." + _PAS_DE_MODELE_EN,
                30,
            ),
        )
    }
)


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
