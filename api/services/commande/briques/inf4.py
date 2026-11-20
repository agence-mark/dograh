"""[.mark] Brique INF4 : le halal (inventaire, famille 9).

Deux données, jamais mélangées : la case « halal » du RESTAURANT (``resto_reglage.halal_restaurant``) et l'étiquette ``halal`` d'un ARTICLE. La règle dit ce qui est écrit, rien de plus :
elle ne conclut jamais d'un côté vers l'autre.
"""

from __future__ import annotations

from api.services.commande.briques.registre import Brique, enregistrer


CODE = "halal"  # l'étiquette de régime que cette brique lit, sur l'article


def brique_inf4_dire_ce_qui_est_ecrit(regimes_de_l_article: list[str] | None, halal_restaurant: bool) -> dict[str, bool]:
    """``{"article": bool, "restaurant": bool, "ecrit": bool}`` : ``ecrit`` est vrai quand au moins l'une des deux données le dit."""
    article = bool(regimes_de_l_article and CODE in regimes_de_l_article)
    return {"article": article, "restaurant": bool(halal_restaurant), "ecrit": article or bool(halal_restaurant)}


def _sans(carte: dict) -> dict:
    for p in carte["produits"]:
        p["regimes"] = None
    return carte


enregistrer(Brique(
    "INF4", "informations", "C", (("produits", "regimes"),), brique_inf4_dire_ce_qui_est_ecrit,
    change_la_fiche_du_modele=False, vue_sur_carte=True, sans_la_brique=_sans, carte_d_essai="briques/INF4",
    phrase="halal : ce qui est écrit (le restaurant, l'article), rien de plus",
))
