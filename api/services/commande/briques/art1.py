"""[.mark] Brique ART1 : l'article simple (inventaire, famille 1).

Un produit, un prix, une quantité. Le nom (« 1664 ») se retrouve par la recherche des noms (``recherche_liste``), jamais comme une quantité ; ici vit le seul
calcul : le prix d'une ligne est son prix unitaire fois sa quantité.
"""

from __future__ import annotations

from api.services.commande.briques.registre import Brique, enregistrer


def brique_art1_chiffrer(prix_unitaire: int, quantite: int) -> int:
    """Le prix d'une ligne, en centimes."""
    return prix_unitaire * quantite


enregistrer(Brique(
    "ART1", "article", "A", (("produits", "nom"), ("produits", "categorie_id"), ("produits", "synonymes")), brique_art1_chiffrer,
    change_la_fiche_du_modele=False, vue_sur_carte=True, sans_la_brique=lambda carte: carte, carte_d_essai="briques/ART1",
    phrase="rien de nouveau : la ligne et son prix",
))
