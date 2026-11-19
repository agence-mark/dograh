"""[.mark] Brique OPT1 : le choix unique obligatoire (inventaire, famille 3).

Un seul choix, sans lequel la ligne est incomplète (« 1 accompagnement inclus » par grillade) : la ligne attend son choix, la question numérotée porte le libellé du groupe.
Le défaut d'un groupe obligatoire est pris d'office quand il existe ; la personne peut en changer. Deux écritures du format commun, une seule règle : l'option dont
l'identifiant est dans ``groupe.defaut`` (le défaut du groupe), ou celle qui est ``par_defaut`` (le défaut de l'option).
"""

from __future__ import annotations

from typing import Any

from api.services.commande.briques.registre import Brique, enregistrer


def brique_opt1_choix_obligatoire(groupe: dict[str, Any]) -> list[dict[str, Any]]:
    """Les options prises d'office dans un groupe obligatoire (vendables, pas en rupture), dans l'ordre du groupe ; vide : rien n'est choisi à la place de la personne."""
    voulus = set(groupe.get("defaut") or [])
    return [o for o in groupe["options"] if (o["id"] in voulus or o["par_defaut"]) and o["vendable"] and not o["rupture"]]


def _sans(carte: dict) -> dict:
    """Le groupe devient facultatif (plus de question) : la brique est son caractère obligatoire."""
    for g in carte["groupes"]:
        if g["min"] == 1 and g["max"] == 1:
            g["min"] = 0
    return carte


enregistrer(Brique(
    "OPT1", "options", "C", (("groupes", "min"), ("groupes", "defaut")), brique_opt1_choix_obligatoire,
    change_la_fiche_du_modele=True, vue_sur_carte=True, sans_la_brique=_sans, carte_d_essai="briques/OPT1",
    phrase="la question numérotée du choix obligatoire, au libellé du groupe",
))
