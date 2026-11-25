"""[.mark] Brique FOR13 : l'inclus défini par rubrique (inventaire, famille 5 ; « servi avec 1 soupe, 1 salade et 1 riz »).

Ce qui est servi avec chaque produit de la rubrique est écrit une fois sur la catégorie (``resto_categorie.inclus``) ; la lecture d'un produit de la rubrique le rend
(fait ``servi_avec``), la commande l'envoie à la caisse en note de ligne (aucun modèle de caisse ne l'exprime, inventaire § 5 : ``regle_inconnue_en_note``).
"""

from __future__ import annotations

from typing import Any

from api.services.commande.briques.registre import Brique, enregistrer


def faits_de_la_rubrique(carte: dict[str, Any], categorie_id: str | None) -> dict[str, Any]:
    categorie = next((c for c in carte.get("categories") or [] if c["id"] == categorie_id), None)
    inclus = [str(x) for x in (categorie or {}).get("inclus") or [] if str(x).strip()]
    return {"servi_avec": inclus} if inclus else {}


def brique_for13_inclus_de_la_rubrique(servi_avec: list[str]) -> str | None:
    """La note de ligne de ce qui est servi avec, ou ``None``."""
    return ("servi avec : " + ", ".join(servi_avec)) if servi_avec else None


def id_de_la_rubrique(article: dict[str, Any]) -> str:
    """L'identifiant de la règle « servi avec » d'un article : sa rubrique (la règle est écrite une fois sur la catégorie), à défaut son nom."""
    return f"rubrique:{article.get('categorie') or article.get('nom')}"


def fait_de_la_rubrique(article: dict[str, Any]) -> dict[str, Any] | None:
    """Ce qui est servi avec, en fait brut que le modèle dit avec ses mots, une fois à l'ajout (FOR13-B du lot 11 ; lot 7b : jamais une phrase finie) ; ``None`` sans inclus."""
    servi = [str(x) for x in article.get("servi_avec") or [] if str(x).strip()]
    return {"servi_avec": servi} if servi else None


def _sans(carte: dict) -> dict:
    for c in carte["categories"]:
        c["inclus"] = []
    return carte


enregistrer(Brique(
    "FOR13", "formules", "C", (("categories", "inclus"),), brique_for13_inclus_de_la_rubrique,
    change_la_fiche_du_modele=True, vue_sur_carte=True, sans_la_brique=_sans, carte_d_essai="briques/FOR13",
    phrase="la lecture d'un produit de la rubrique rend servi_avec",
))
