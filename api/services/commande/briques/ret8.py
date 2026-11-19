"""[.mark] Brique RET8 : la composition libre à l'unité (inventaire, famille 4).

Une base à prix, chaque ingrédient facturé (pizza créative à 1 € l'ingrédient) : le total est la base plus la somme des ingrédients, relu avant de l'enregistrer ; chaque ingrédient part à la
caisse à son prix.
"""

from __future__ import annotations

from typing import Any

from api.services.commande.briques.registre import Brique, enregistrer


def brique_ret8_base_plus_ingredients(prix_de_la_base: int, choix: list[dict[str, Any]]) -> int:
    """Le prix d'une unité : la base plus chaque ingrédient à son prix (quantité comprise)."""
    return prix_de_la_base + sum(int(c["prix"]) * int(c.get("quantite", 1)) for c in choix)


def _sans(carte: dict) -> dict:
    retires = {g["id"] for g in carte["groupes"] if g["role"] == "supplement"}
    carte["groupes"] = [g for g in carte["groupes"] if g["id"] not in retires]
    for p in carte["produits"]:
        p["groupes"] = [g for g in p.get("groupes") or [] if g not in retires]
    return carte


enregistrer(Brique(
    "RET8", "ajouts", "C", (("groupes", "role"), ("options", "prix")), brique_ret8_base_plus_ingredients,
    change_la_fiche_du_modele=True, vue_sur_carte=True, sans_la_brique=_sans, carte_d_essai="briques/RET8",
    phrase="la case de composition existe ; le total relu est la base plus chaque ingrédient",
))
