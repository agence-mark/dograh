"""[.mark] Brique RET1 : le supplément à prix fixe (inventaire, famille 4).

Un ingrédient ajouté à prix fixe (« avec du bacon » : cheddar 1 €, bacon 1,50 €) : une option payante d'un groupe de rôle ``supplement``, ajoutée au prix de la ligne et envoyée à la
caisse sous son nom et son prix (D50).
"""

from __future__ import annotations

from typing import Any

from api.services.commande.briques.registre import Brique, enregistrer


def brique_ret1_ajouter_le_supplement(prix_de_la_ligne: int, option: dict[str, Any], quantite: int = 1) -> int:
    """Le prix d'une unité de la ligne avec ce supplément."""
    return prix_de_la_ligne + option["prix"] * quantite


def _sans(carte: dict) -> dict:
    """Sans la brique, la carte n'a aucun groupe de suppléments : la fiche n'a plus de choix à composer."""
    retires = {g["id"] for g in carte["groupes"] if g["role"] == "supplement"}
    carte["groupes"] = [g for g in carte["groupes"] if g["id"] not in retires]
    for p in carte["produits"]:
        p["groupes"] = [g for g in p.get("groupes") or [] if g not in retires]
    return carte


enregistrer(Brique(
    "RET1", "ajouts", "A", (("groupes", "role"), ("groupes", "options")), brique_ret1_ajouter_le_supplement,
    change_la_fiche_du_modele=True, vue_sur_carte=True, sans_la_brique=_sans, carte_d_essai="briques/RET1",
    phrase="le supplément dit part avec son prix ; la case de composition existe quand la carte a des suppléments",
))
