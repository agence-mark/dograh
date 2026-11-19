"""[.mark] Brique PRX3 : la disponibilité par mode (inventaire, famille 6 ; 2 cartes sur 44).

Un produit, une option ou une formule ne se vend que dans certains modes (``modes``, NULL : tous). Une seule règle les sert tous : elle refuse DÈS QUE le mode est connu, à
l'ajout si le mode est déjà posé, à la pose du mode sinon (jamais au total). Le refus rend les modes permis, jamais un choix fait à la place du client.
"""

from __future__ import annotations

from typing import Any

from api.services.commande.briques.registre import Brique, enregistrer

RAISON = "mode_non_permis"


def brique_prx3_refuser_des_que_le_mode_est_connu(objet: dict[str, Any], mode: str | None) -> dict[str, Any] | None:
    """Le refus d'un objet (``nom``, ``modes``) demandé dans un mode qu'il n'a pas, ou ``None`` (mode inconnu, ou ``modes`` non dit : tous)."""
    modes = objet.get("modes")
    if mode and modes is not None and mode not in modes:
        return {"raison": RAISON, "article": objet["nom"], "mode": mode, "choix": list(modes)}
    return None


def lignes_hors_du_mode(objets_des_lignes: list[dict[str, Any]], mode: str) -> list[dict[str, Any]]:
    """Les refus des lignes déjà au panier qui ne se vendent pas dans le mode qui vient d'être posé (une ligne = l'objet qu'elle porte)."""
    refus = [brique_prx3_refuser_des_que_le_mode_est_connu(objet, mode) for objet in objets_des_lignes]
    return [r for r in refus if r is not None]


def _sans(carte: dict) -> dict:
    for p in carte["produits"]:
        p["modes"] = None
    for g in carte["groupes"]:
        for o in g["options"]:
            o["modes"] = None
    for f in carte["formules"]:
        f["modes"] = None
    return carte


enregistrer(Brique(
    "PRX3", "prix_et_conditions", "C", (("produits", "modes"), ("options", "modes"), ("formules", "modes")), brique_prx3_refuser_des_que_le_mode_est_connu,
    change_la_fiche_du_modele=False, vue_sur_carte=True, sans_la_brique=_sans, carte_d_essai="briques/PRX3",
    phrase="un mode non permis est refusé avec les modes permis, dès que le mode est connu",
))
