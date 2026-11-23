"""[.mark] Brique OPT8 : le nombre de boules et les parfums (inventaire, famille 3).

Le nombre de boules fixe le prix (une déclinaison par nombre) et le nombre de parfums (DEC2 : ``quotas`` de la déclinaison sur le groupe des parfums). Trois boules : trois
parfums, jamais quatre.
"""

from __future__ import annotations

from typing import Any

from api.services.commande.briques.taille_fixant_le_nombre import brique_dec2_quota_selon_la_declinaison
from api.services.commande.briques.registre import Brique, enregistrer


def brique_opt8_parfums_selon_le_nombre(groupe: dict[str, Any], declinaison: dict[str, Any] | None) -> tuple[int, int]:
    """``(minimum, maximum)`` de parfums pour cette déclinaison (le nombre de boules)."""
    g = brique_dec2_quota_selon_la_declinaison(groupe, declinaison)
    return g["min"], g["max"]


def _sans(carte: dict) -> dict:
    for p in carte["produits"]:
        for d in p["declinaisons"]:
            d.pop("quotas", None)
    return carte


enregistrer(Brique(
    "OPT8", "options", "C", (("declinaisons", "quotas"),), brique_opt8_parfums_selon_le_nombre,
    change_la_fiche_du_modele=True, vue_sur_carte=True, sans_la_brique=_sans, carte_d_essai="briques/OPT8",
    phrase="la question des parfums porte le nombre de la taille choisie",
))
