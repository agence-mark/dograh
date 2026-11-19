"""[.mark] Brique OPT9 : le lait et le sucre au choix (inventaire, famille 3).

Des groupes de choix ordinaires, avec un écart de prix pour un lait : réglés comme OPT1 (alias déclaré).
"""

from __future__ import annotations

from api.services.commande.briques.opt1 import brique_opt1_choix_obligatoire
from api.services.commande.briques.registre import Brique, enregistrer


def brique_opt9_comme_opt1(groupe: dict) -> list[dict]:
    """Se règle comme OPT1 : un choix obligatoire, son défaut pris d'office."""
    return brique_opt1_choix_obligatoire(groupe)


enregistrer(Brique(
    "OPT9", "options", "C", (("groupes", "min"),), brique_opt9_comme_opt1, alias_de="OPT1",
    change_la_fiche_du_modele=False, vue_sur_carte=True, sans_la_brique=lambda carte: carte, carte_d_essai="briques/OPT9",
    phrase="rien de nouveau : un groupe de choix ordinaire",
))
