"""[.mark] Brique RET3 : le supplément par classe d'ingrédient (inventaire, famille 4).

Standard et premium à des prix différents (saumon fumé au prix premium) : chaque option porte SON prix ; une classe n'est qu'un regroupement (un groupe de choix), jamais une règle de
prix à part.
"""

from __future__ import annotations

from typing import Any

from api.services.commande.briques.registre import Brique, enregistrer


def brique_ret3_prix_de_l_option(option: dict[str, Any]) -> int:
    """Le prix de l'option, quelle que soit sa classe."""
    return option["prix"]


enregistrer(Brique(
    "RET3", "ajouts", "A", (("options", "prix"),), brique_ret3_prix_de_l_option,
    change_la_fiche_du_modele=False, vue_sur_carte=True, sans_la_brique=lambda carte: carte, carte_d_essai="briques/RET3",
    phrase="rien de nouveau : chaque option part à son prix",
))
