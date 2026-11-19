"""[.mark] Brique RET2 : le supplément qui dépend de la taille (inventaire, famille 4 ; conflit RET2 et FOR4).

Le même ingrédient, un prix selon la taille du plat (ingrédient en plus 1 € en Junior, 1,50 € en Senior) : le prix de l'option est lu à la déclinaison de la LIGNE avant de chiffrer
(``prix_par_declinaison``) ; une déclinaison que l'option ne cite pas garde le prix de l'option. Conflit avec une ligne de formule (FOR4, lot 11) : la ligne de formule gagne, le
supplément ne s'ajoute pas deux fois.
"""

from __future__ import annotations

from typing import Any

from api.services.commande.briques.registre import Brique, enregistrer


def brique_ret2_prix_a_la_declinaison(option: dict[str, Any], declinaison: dict[str, Any] | None) -> int:
    """Le prix d'une unité de cette option sur la déclinaison de la ligne."""
    par_declinaison = option.get("prix_par_declinaison") or {}
    if declinaison is not None and declinaison.get("id") in par_declinaison:
        return int(par_declinaison[declinaison["id"]])
    return option["prix"]


def _sans(carte: dict) -> dict:
    for g in carte["groupes"]:
        for o in g["options"]:
            o.pop("prix_par_declinaison", None)
    return carte


enregistrer(Brique(
    "RET2", "ajouts", "C", (("options", "prix_par_declinaison"),), brique_ret2_prix_a_la_declinaison,
    change_la_fiche_du_modele=False, vue_sur_carte=True, sans_la_brique=_sans, carte_d_essai="briques/RET2",
    phrase="rien de nouveau : le supplément part au prix de la taille de la ligne",
))
