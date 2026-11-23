"""[.mark] Brique PRX2 : « hors jours fériés » (inventaire, famille 6 ; 4 cartes sur 44), une règle inconnue.

Aucun modèle de caisse n'exprime « hors jours fériés » (jours de semaine et dates seulement). La clé ``hors_feries`` de la disponibilité (``plages.py`` l'ignore : elle ne restreint
rien) le dit : un jour férié, l'article reste vendable, la ligne reçoit une note (``regle_inconnue_en_note``, lot 8) et le portail est signalé. Jamais un refus.
Les jours fériés de France sont calculés (jours fixes, Pâques, lundi de Pâques, Ascension, lundi de Pentecôte).
"""

from __future__ import annotations

from datetime import date, timedelta
from typing import Any

from api.services.commande.briques.registre import Brique, enregistrer

FIXES = ((1, 1), (5, 1), (5, 8), (7, 14), (8, 15), (11, 1), (11, 11), (12, 25))


def paques(annee: int) -> date:
    """Le dimanche de Pâques (calcul grégorien de Meeus, Jones et Butcher)."""
    a, b, c = annee % 19, annee // 100, annee % 100
    d, e = b // 4, b % 4
    f = (b + 8) // 25
    g = (b - f + 1) // 3
    h = (19 * a + b - d - g + 15) % 30
    i, k = c // 4, c % 4
    l = (32 + 2 * e + 2 * i - h - k) % 7
    m = (a + 11 * h + 22 * l) // 451
    mois, jour = divmod(h + l - 7 * m + 114, 31)
    return date(annee, mois, jour + 1)


def jours_feries(annee: int) -> frozenset[date]:
    """Les jours fériés de France de l'année."""
    p = paques(annee)
    return frozenset({date(annee, m, j) for m, j in FIXES} | {p + timedelta(days=1), p + timedelta(days=39), p + timedelta(days=50)})


def brique_prx2_en_regle_inconnue(objet: dict[str, Any], jour: date) -> str | None:
    """Le texte de la règle inconnue à noter sur la ligne quand l'article se vend « hors jours fériés » et que ``jour`` est férié ; sinon ``None``. Jamais un refus."""
    if not (objet.get("disponibilite") or {}).get("hors_feries") or jour not in jours_feries(jour.year):
        return None
    return f"{objet['nom']} : hors jours fériés, à vérifier"


def _sans(carte: dict) -> dict:
    for p in carte["produits"]:
        p["disponibilite"] = None
    return carte


enregistrer(Brique(
    "PRX2", "prix_et_conditions", "C", (("produits", "disponibilite"),), brique_prx2_en_regle_inconnue,
    change_la_fiche_du_modele=False, vue_sur_carte=True, sans_la_brique=_sans, carte_d_essai="briques/PRX2",
    phrase="un jour férié, l'article est pris avec une note de ligne et un signalement au portail, jamais refusé",
))
