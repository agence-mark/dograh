"""[.mark] Brique INF3 : le régime d'un article (inventaire, famille 9 ; C26).

Un régime ne se déduit jamais (ni des allergènes, ni des ingrédients) : seule l'ÉTIQUETTE posée par une personne sur l'article le dit (``vegetarien``, ``vegetalien``, ``sans_gluten``,
``halal``, ``autre``). Sans étiquette, la réponse est « je ne peux pas le garantir », jamais « non ».
"""

from __future__ import annotations

from api.services.commande.briques.registre import Brique, enregistrer

LIBELLES = {"vegetarien": "végétarien", "vegetalien": "végétalien", "sans_gluten": "sans gluten", "halal": "halal", "autre": "autre régime"}


def brique_inf3_jamais_sans_etiquette(regimes: list[str] | None, regime: str) -> str:
    """``etiquete`` quand l'article porte l'étiquette ``regime`` ; ``inconnu`` sinon (jamais un « non » sans étiquette)."""
    return "etiquete" if regimes and regime in regimes else "inconnu"


def articles_etiquetes(articles: list[dict], regime: str) -> list[str]:
    """Les noms des articles du catalogue qui portent l'étiquette ``regime`` (seulement eux)."""
    return [a["nom"] for a in articles if brique_inf3_jamais_sans_etiquette(a.get("regimes"), regime) == "etiquete"]


def _sans(carte: dict) -> dict:
    for p in carte["produits"]:
        p["regimes"] = None
    return carte


enregistrer(Brique(
    "INF3", "informations", "C", (("produits", "regimes"),), brique_inf3_jamais_sans_etiquette,
    change_la_fiche_du_modele=False, vue_sur_carte=True, sans_la_brique=_sans, carte_d_essai="briques/INF3",
    phrase="un régime n'est dit que s'il est étiqueté sur l'article ; sans étiquette : « je ne peux pas le garantir »",
))
