"""[.mark] Brique FOR10 : le menu ou le plat pour N personnes (inventaire, famille 5 ; 10 cartes sur 44 ; banc B9 § 3 : la sous-case ``personnes``, 16/18).

Le prix par nombre de personnes (``personnes`` : ``{"<n>": centimes}``) : chaque nombre est une déclinaison de la formule (type ``personnes``). La sous-case
``ajouter[].personnes`` dit le nombre ; absent, la question numérotée de la déclinaison (« pour combien de personnes », mot de ``types_de_declinaison.json``) ; un nombre
que la carte n'a pas est redemandé avec ses choix (``personnes_hors_liste``). Le contenu est relu (fait ``contenu``).
"""

from __future__ import annotations

from typing import Any

from api.services.commande.briques.registre import Brique, enregistrer

RAISON_HORS_LISTE = "personnes_hors_liste"


def vendu_par_personnes(article: dict[str, Any] | None) -> bool:
    """L'article de la carte (la vue de ``article_de_la_carte``) se décline-t-il par nombre de personnes ?"""
    return bool(article) and any(d.get("type") == "personnes" for d in article.get("declinaisons") or [])


def personnes_de(formule: dict[str, Any]) -> list[tuple[int, int]]:
    """Les ``(nombre, prix)`` de la formule, par nombre croissant ; vide : la formule ne se vend pas par personnes."""
    sortie = []
    for n, prix in (formule.get("personnes") or {}).items():
        if str(n).isdigit() and isinstance(prix, int) and not isinstance(prix, bool):
            sortie.append((int(n), prix))
    return sorted(sortie)


def brique_for10_pour_combien(article: dict[str, Any], personnes: Any) -> str | None:
    """La variante de la ligne pour le nombre dit (le nom de la déclinaison), ou ``None`` : rien dit, ou un nombre que la carte n'a pas (la question suit)."""
    if personnes is None or isinstance(personnes, bool):
        return None
    try:
        n = int(personnes)
    except (TypeError, ValueError):
        return None
    if any(d.get("type") == "personnes" and d["nom"] == str(n) for d in article.get("declinaisons") or []):
        return str(n)
    return None


def _sans(carte: dict) -> dict:
    for f in carte["formules"]:
        f["personnes"] = None
    return carte


enregistrer(Brique(
    "FOR10", "formules", "C", (("formules", "personnes"),), brique_for10_pour_combien,
    change_la_fiche_du_modele=True, vue_sur_carte=True, sans_la_brique=_sans, carte_d_essai="briques/FOR10",
    phrase="la sous-case personnes ; sans le nombre, la question numérotée « pour combien de personnes »",
))
