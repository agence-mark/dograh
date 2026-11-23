"""[.mark] Brique PRX8 : la quantité maximale par commande (inventaire, famille 6 ; aucune carte lue, HubRise ``max_per_order``).

``max_par_commande`` est un plafond de carte, par produit, additionné sur toutes les lignes du même produit de la commande. Au-delà : refus avec le maximum. Les bornes de
sécurité (20 par ligne, E30 ; 1 à 99 du classeur) restent : ce sont des bornes d'intégrité, pas des règles de carte. Code seulement, aucune case nouvelle.
"""

from __future__ import annotations

from typing import Any

from api.services.commande.briques.registre import Brique, enregistrer

RAISON = "quantite_au_dela_du_maximum"


def brique_prx8_refuser_au_dela(produit: dict[str, Any], deja_pris: int, demande: int) -> dict[str, Any] | None:
    """Le refus quand ``deja_pris`` (les autres lignes du produit) plus ``demande`` dépasse ``max_par_commande``, sinon ``None`` (non dit : aucun plafond de carte)."""
    maximum = produit.get("max_par_commande")
    if maximum is None or deja_pris + demande <= int(maximum):
        return None
    return {"raison": RAISON, "article": produit["nom"], "maximum": int(maximum), "deja_dans_la_commande": deja_pris}


def _sans(carte: dict) -> dict:
    for p in carte["produits"]:
        p["max_par_commande"] = None
    return carte


enregistrer(Brique(
    "PRX8", "prix_et_conditions", "C", (("produits", "max_par_commande"),), brique_prx8_refuser_au_dela,
    change_la_fiche_du_modele=False, vue_sur_carte=False, sans_la_brique=_sans, carte_d_essai="briques/PRX8",
    phrase="au-delà du maximum par commande, refus avec le maximum ; aucune case nouvelle",
))
