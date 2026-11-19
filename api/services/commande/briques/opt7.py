"""[.mark] Brique OPT7 : le support au choix avec écart de prix (inventaire, famille 3).

Pain, naan, enveloppe : un choix obligatoire dont chaque option a son prix (naan nature 1,50 €, naan fromage 3,50 €). L'écart s'ajoute au prix de base (le prix de l'option est
un supplément comme un autre), il part à la caisse sous le nom de l'option (D50).
"""

from __future__ import annotations

from typing import Any

from api.services.commande.briques.registre import Brique, enregistrer


def brique_opt7_ajouter_l_ecart(prix_de_base: int, option: dict[str, Any], quantite: int = 1) -> int:
    """Le prix d'une unité de la ligne avec ce support."""
    return prix_de_base + option["prix"] * quantite


def _sans(carte: dict) -> dict:
    for g in carte["groupes"]:
        for o in g["options"]:
            o["prix"] = 0  # sans la brique, aucun écart de prix
    return carte


enregistrer(Brique(
    "OPT7", "options", "A", (("groupes", "options"),), brique_opt7_ajouter_l_ecart,
    change_la_fiche_du_modele=False, vue_sur_carte=True, sans_la_brique=_sans, carte_d_essai="briques/OPT7",
    phrase="rien de nouveau : le prix de chaque option est dans la question du groupe",
))
