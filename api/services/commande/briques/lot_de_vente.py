"""[.mark] Brique QTE2 : le lot de vente (inventaire, famille 7 ; 2 cartes sur 44, A19 et A20 : maki par 6, sashimi par 12).

L'unité de vente est un lot (``lot_de_vente`` : le nombre de pièces) et le prix du produit est celui d'UN lot. Le client dit des PIÈCES (« douze maki ») : la règle vérifie le
multiple ; une quantité hors multiple est refusée avec les deux multiples voisins en choix, jamais choisie par le code (« quatre maki » sur un lot de 6 : 6 ou 12). La ligne est
stockée et envoyée à la caisse en nombre de LOTS (le code de caisse est celui du lot) ; le retour porte ``lots`` et ``pieces``.
"""

from __future__ import annotations

from typing import Any

from api.services.commande.briques.registre import Brique, enregistrer

RAISON = "multiple_du_lot"


def multiples_voisins(lot: int, pieces: int) -> list[int]:
    """Les deux multiples de ``lot`` les plus proches de ``pieces`` (celui d'en dessous quand il existe, celui d'au-dessus), toujours deux."""
    dessous = (pieces // lot) * lot
    voisins = [m for m in (dessous, dessous + lot) if m > 0]
    return voisins if len(voisins) == 2 else [lot, 2 * lot]


def brique_qte2_multiple_du_lot(produit: dict[str, Any], pieces: int) -> dict[str, Any]:
    """``{"lots", "pieces"}`` pour un nombre de pièces qui est un multiple du lot, ``{}`` quand le produit n'a pas de lot, ou le refus (``raison``, ``choix``)."""
    lot = produit.get("lot_de_vente")
    if not lot:
        return {}
    if pieces % int(lot):
        return {"raison": RAISON, "article": produit["nom"], "lot": int(lot), "choix": multiples_voisins(int(lot), pieces)}
    return {"lots": pieces // int(lot), "pieces": pieces}


def _sans(carte: dict) -> dict:
    for p in carte["produits"]:
        p["lot_de_vente"] = None
    return carte


enregistrer(Brique(
    "QTE2", "quantite_et_unite", "C", (("produits", "lot_de_vente"),), brique_qte2_multiple_du_lot,
    change_la_fiche_du_modele=True, vue_sur_carte=True, sans_la_brique=_sans, carte_d_essai="briques/QTE2",
    phrase="une quantité hors multiple du lot est refusée avec les deux multiples voisins ; la ligne compte des lots",
))
