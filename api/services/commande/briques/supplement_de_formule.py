"""[.mark] Brique FOR4 : le supplément sur une ligne de formule (inventaire, famille 5 ; HubRise : ``extra_charge`` d'un sku de ligne de deal).

La formule change de prix selon le produit pris dedans (« avec le pad thaï, un euro de plus ») : prix de la formule plus les suppléments des choix. Le supplément de la
ligne est le SEUL prix de ce choix dans la formule : le supplément de taille d'une option (RET2) ne s'ajoute pas en plus (inventaire § 4 : la ligne de formule gagne).
"""

from __future__ import annotations

from typing import Any

from api.services.commande.briques.registre import Brique, enregistrer


def brique_for4_ajouter_le_supplement_de_ligne(ligne: dict[str, Any], code: str) -> int:
    """Le supplément d'une unité de ce choix dans cette ligne (0 : aucun)."""
    return int((ligne.get("supplements") or {}).get(code, 0))


def _sans(carte: dict) -> dict:
    for f in carte["formules"]:
        for ligne in f["lignes"]:
            ligne.pop("supplements", None)
    return carte


enregistrer(Brique(
    "FOR4", "formules", "C", (("formules", "lignes"),), brique_for4_ajouter_le_supplement_de_ligne,
    change_la_fiche_du_modele=False, vue_sur_carte=True, sans_la_brique=_sans, carte_d_essai="briques/FOR4",
    phrase="rien de nouveau : le supplément du choix part dans le prix de la formule",
))
