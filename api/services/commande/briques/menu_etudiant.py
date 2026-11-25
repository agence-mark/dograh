"""[.mark] Brique FOR9 : le menu étudiant ou d'un public justifié (inventaire, famille 5).

Le texte du justificatif (``public``) est un FAIT que le retour porte et que le modèle dit ; il n'est jamais contrôlé, et la formule n'est jamais refusée sur ce motif
(le justificatif ne se vérifie pas au téléphone, inventaire § 4).
"""

from __future__ import annotations

from typing import Any

from api.services.commande.briques.registre import Brique, enregistrer


def faits_de_la_formule(formule: dict[str, Any]) -> dict[str, Any]:
    texte = " ".join(str(formule.get("public") or "").split())
    return {"justificatif": texte} if texte else {}


def brique_for9_dire_le_justificatif(article: dict[str, Any]) -> dict[str, Any]:
    """Le fait à dire (``justificatif``), vide sans justificatif ; jamais un refus."""
    return {"justificatif": article["justificatif"]} if article.get("justificatif") else {}


def fait_du_justificatif(article: dict[str, Any]) -> dict[str, Any] | None:
    """Le justificatif, en fait brut que le modèle dit avec ses mots, une fois à l'ajout (FOR9 du lot 11 ; lot 7b : jamais une phrase finie) ; ``None`` sans justificatif."""
    texte = str(article.get("justificatif") or "").strip().rstrip(".")
    return {"justificatif": texte} if texte else None


def _sans(carte: dict) -> dict:
    for f in carte["formules"]:
        f["public"] = None
    return carte


enregistrer(Brique(
    "FOR9", "formules", "C", (("formules", "public"),), brique_for9_dire_le_justificatif,
    change_la_fiche_du_modele=True, vue_sur_carte=True, sans_la_brique=_sans, carte_d_essai="briques/FOR9",
    phrase="le justificatif est un fait du retour, jamais un refus",
))
