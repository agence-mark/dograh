"""[.mark] Public holidays, computed by the code (chantier l-agent-collegue, L5, P10).

Added to the establishment's closures by the planner. Per establishment: metropolitan France
(the default, 11 days) or Alsace-Moselle (13: Good Friday and 26 December too). Easter by the
anonymous Gregorian algorithm (Meeus/Jones/Butcher), the movable days from it.
"""

from __future__ import annotations

from datetime import date, timedelta
from functools import lru_cache


def paques(annee: int) -> date:
    a, b, c = annee % 19, annee // 100, annee % 100
    d, e = b // 4, b % 4
    f = (b + 8) // 25
    g = (b - f + 1) // 3
    h = (19 * a + b - d - g + 15) % 30
    i, k = c // 4, c % 4
    l = (32 + 2 * e + 2 * i - h - k) % 7
    m = (a + 11 * h + 22 * l) // 451
    mois = (h + l - 7 * m + 114) // 31
    jour = (h + l - 7 * m + 114) % 31 + 1
    return date(annee, mois, jour)


@lru_cache(maxsize=64)
def jours_feries(annee: int, regime: str = "metropole") -> frozenset[date]:
    p = paques(annee)
    jours = {
        date(annee, 1, 1),  # Jour de l'an
        p + timedelta(days=1),  # Lundi de Pâques
        date(annee, 5, 1),
        date(annee, 5, 8),
        p + timedelta(days=39),  # Ascension
        p + timedelta(days=50),  # Lundi de Pentecôte
        date(annee, 7, 14),
        date(annee, 8, 15),
        date(annee, 11, 1),
        date(annee, 11, 11),
        date(annee, 12, 25),
    }
    if regime == "alsace_moselle":
        jours |= {p - timedelta(days=2), date(annee, 12, 26)}
    return frozenset(jours)


def est_ferie(jour: date, regime: str = "metropole") -> bool:
    return jour in jours_feries(jour.year, regime)
