"""[.mark] Brique PRX6 : le produit alcoolisé (inventaire, famille 6 ; 4 cartes sur 44).

``alcool`` (et ``degre``) sont dans le format commun, importés ; l'alcool écrit à l'écran (surcouche) s'y ajoute, jamais effacé par un import. La règle d'âge est DITE à la
remise, jamais vérifiée : l'ajout d'un article alcoolisé rend le fait ``alcool``. Un article alcoolisé n'est jamais proposé en vente en plus (le drapeau est lu par la vente
en plus) et le titre-restaurant ne le paie pas (règle du module, inchangée).
"""

from __future__ import annotations

from typing import Any

from api.services.commande.briques.registre import Brique, enregistrer


def brique_prx6_regle_d_age_dite(article: dict[str, Any]) -> dict[str, Any] | None:
    """Le fait à rendre pour un article alcoolisé (``{"alcool": True, "degre": ...}``), ou ``None``. Jamais un refus."""
    if not article.get("alcool"):
        return None
    return {"alcool": True, **({"degre": article["degre"]} if article.get("degre") is not None else {})}


def _sans(carte: dict) -> dict:
    for p in carte["produits"]:
        p["alcool"], p["degre"] = False, None
    return carte


enregistrer(Brique(
    "PRX6", "prix_et_conditions", "C", (("produits", "alcool"), ("produits", "degre")), brique_prx6_regle_d_age_dite,
    change_la_fiche_du_modele=False, vue_sur_carte=True, sans_la_brique=_sans, carte_d_essai="briques/PRX6",
    phrase="un article alcoolisé rend le fait alcool : la règle d'âge est dite à la remise, jamais vérifiée",
))
