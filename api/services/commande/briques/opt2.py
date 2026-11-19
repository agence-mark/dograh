"""[.mark] Brique OPT2 : le choix multiple à total fixe (inventaire, famille 3).

N éléments parmi une liste (« limite 2 sauces ») : le code compte, refuse le dépassement avec la raison (``MAXIMUM_ATTEINT``) et relance sous le minimum.
"""

from __future__ import annotations

from typing import Any

from api.services.commande.briques.registre import Brique, enregistrer


def brique_opt2_compter(groupe: dict[str, Any], deja: int, en_plus: int) -> str | None:
    """``None`` : ces choix tiennent dans le groupe ; ``"maximum"`` : ils le dépassent (refus avec la raison)."""
    return "maximum" if deja + en_plus > groupe["max"] else None


def _sans(carte: dict) -> dict:
    for g in carte["groupes"]:
        g["max"] = max(g["max"], 99)  # sans la brique, aucun total n'est fixé
    return carte


enregistrer(Brique(
    "OPT2", "options", "A", (("groupes", "min"), ("groupes", "max")), brique_opt2_compter,
    change_la_fiche_du_modele=False, vue_sur_carte=True, sans_la_brique=_sans, carte_d_essai="briques/OPT2",
    phrase="le refus d'un dépassement porte le groupe et le maximum",
))
