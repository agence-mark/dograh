"""[.mark] Brique OPT10 : la cuisson (inventaire, famille 3 ; jamais vue sur les 44 cartes).

Un groupe de choix ordinaire, réglé comme OPT1 (alias déclaré). Sans groupe de cuisson, « à point » est une note de ligne signalée (``choix_sans_objet``, E19). Code seulement,
aucune case nouvelle (D66).
"""

from __future__ import annotations

from api.services.commande.briques.opt1 import brique_opt1_choix_obligatoire
from api.services.commande.briques.registre import Brique, enregistrer


def brique_opt10_comme_opt1(groupe: dict) -> list[dict]:
    """Se règle comme OPT1 : un choix obligatoire, son défaut pris d'office."""
    return brique_opt1_choix_obligatoire(groupe)


enregistrer(Brique(
    "OPT10", "options", "C", (("groupes", "min"),), brique_opt10_comme_opt1, alias_de="OPT1",
    change_la_fiche_du_modele=False, vue_sur_carte=False, sans_la_brique=lambda carte: carte, carte_d_essai="briques/OPT10",
    phrase="rien de nouveau pour le modèle",
))
