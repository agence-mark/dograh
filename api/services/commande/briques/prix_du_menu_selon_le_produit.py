"""[.mark] Brique FOR5 : le prix du menu qui suit le produit (inventaire, famille 5).

« Le Texas en menu » : le prix du menu de CE produit (12,40 € simple, 13,90 € double), jamais la somme moins une remise. Écrit dans la carte comme un supplément par
produit sur la ligne du produit (FOR4 : l'écart au prix de base du menu) ; la formule se trouve par sa composition (FOR1). Une seule règle de prix.
"""

from __future__ import annotations

from typing import Any

from api.services.commande.briques import supplement_de_formule
from api.services.commande.briques.registre import Brique, enregistrer


def brique_for5_prix_en_menu(formule: dict[str, Any], code: str) -> int:
    """Le prix du menu pour ce produit : le prix de la formule et l'écart de ce produit sur sa ligne."""
    return int(formule["prix"]) + sum(supplement_de_formule.brique_for4_ajouter_le_supplement_de_ligne(ligne, code) for ligne in formule["lignes"])


enregistrer(Brique(
    "FOR5", "formules", "C", (("formules", "lignes"), ("formules", "prix")), brique_for5_prix_en_menu,
    change_la_fiche_du_modele=False, vue_sur_carte=True, sans_la_brique=lambda carte: carte, carte_d_essai="briques/FOR5",
    phrase="rien de nouveau : la formule de ce produit à son prix",
))
