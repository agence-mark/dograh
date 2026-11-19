"""[.mark] Brique OPT5 : le groupe propre à certains produits (inventaire, famille 3).

Le choix n'existe que sur quelques produits (« barbecue ou tomate » seulement sur la Texan) : un groupe n'est jamais proposé ni accepté sur un produit qui ne le porte pas.
La liste des produits d'un groupe est celle de ``produit.groupes`` ; une option dite d'un groupe que l'article n'a pas est refusée (HORS_CARTE) avec ce que l'article propose.
"""

from __future__ import annotations

from typing import Any

from api.services.commande.briques.registre import Brique, enregistrer


def brique_opt5_jamais_hors_produit(article: dict[str, Any], groupe_id: str) -> bool:
    """Vrai quand ce groupe est un choix de CET article."""
    return any(g["id"] == groupe_id for g in article.get("groupes") or [])


enregistrer(Brique(
    "OPT5", "options", "A", (("produits", "groupes"),), brique_opt5_jamais_hors_produit,
    change_la_fiche_du_modele=False, vue_sur_carte=True, sans_la_brique=lambda carte: carte, carte_d_essai="briques/OPT5",
    phrase="le refus d'une option que l'article n'a pas porte ce que l'article propose",
))
