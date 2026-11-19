"""[.mark] Brique RET4 : le supplément pour changer d'accompagnement (inventaire, famille 4).

Un accompagnement de remplacement : quand l'un est inclus (le défaut d'un groupe à un seul choix obligatoire), les autres se paient par DIFFÉRENCE de prix avec lui, jamais à
leur prix absolu (« du riz rouge à la place » : riz rouge moins riz blanc inclus). Le défaut lui-même ne coûte rien de plus. Sans défaut, le prix de l'option est celui du supplément.
"""

from __future__ import annotations

from typing import Any

from api.services.commande.briques.registre import Brique, enregistrer


def _defaut(groupe: dict[str, Any]) -> dict[str, Any] | None:
    """L'option incluse d'un groupe à un seul choix obligatoire (le défaut du groupe ou de l'option), ou ``None``."""
    if groupe["min"] != 1 or groupe["max"] != 1:
        return None
    voulus = set(groupe.get("defaut") or [])
    defauts = [o for o in groupe["options"] if o["vendable"] and (o["id"] in voulus or o["par_defaut"])]
    return defauts[0] if len(defauts) == 1 else None


def brique_ret4_difference_de_prix(groupe: dict[str, Any], option: dict[str, Any], prix_de_l_option: int | None = None) -> int:
    """Ce que cette option ajoute au prix de la ligne : la différence avec l'option incluse (jamais négative), ou son prix quand aucune n'est incluse."""
    prix = option["prix"] if prix_de_l_option is None else prix_de_l_option
    inclus = _defaut(groupe)
    if inclus is None:
        return prix
    return max(0, prix - inclus["prix"])


def _sans(carte: dict) -> dict:
    for g in carte["groupes"]:
        g["defaut"] = []
        for o in g["options"]:
            o["par_defaut"] = False
    return carte


enregistrer(Brique(
    "RET4", "ajouts", "C", (("groupes", "defaut"), ("options", "par_defaut")), brique_ret4_difference_de_prix,
    change_la_fiche_du_modele=False, vue_sur_carte=True, sans_la_brique=_sans, carte_d_essai="briques/RET4",
    phrase="rien de nouveau : l'accompagnement de remplacement part à la différence de prix",
))
