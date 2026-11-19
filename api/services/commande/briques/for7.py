"""[.mark] Brique FOR7 : le menu enfant (inventaire, famille 5 ; 11 cartes sur 44).

La condition d'âge (``age_max``) est un FAIT que le retour porte et que le modèle dit ; elle n'est jamais vérifiée. Les modes permis (``modes``, NULL : tous) : une formule
demandée dans un mode qu'elle n'a pas est refusée dès l'ajout quand le mode est connu (``mode_non_permis``, avec les modes permis) ; le refus quand le mode arrive
après est la disponibilité par mode du lot 12 (PRX3).
"""

from __future__ import annotations

from typing import Any

from api.services.commande.briques.registre import Brique, enregistrer

RAISON_DU_MODE = "mode_non_permis"


def faits_de_la_formule(formule: dict[str, Any]) -> dict[str, Any]:
    """Ce que la lecture et l'ajout rendent : ``condition`` (l'âge maximum dit), ``modes`` permis."""
    sortie: dict[str, Any] = {"modes": formule.get("modes")}
    if formule.get("age_max"):
        sortie["condition"] = {"age_max": int(formule["age_max"])}
    return sortie


def brique_for7_dire_la_condition(article: dict[str, Any], mode: str | None) -> dict[str, Any] | None:
    """Le refus d'une formule demandée dans un mode qu'elle n'a pas, ou ``None`` ; la condition d'âge ne refuse jamais."""
    modes = article.get("modes")
    if mode and modes is not None and mode not in modes:
        return {"raison": RAISON_DU_MODE, "article": article["nom"], "mode": mode, "choix": list(modes)}
    return None


def _sans(carte: dict) -> dict:
    for f in carte["formules"]:
        f["age_max"], f["modes"] = None, None
    return carte


enregistrer(Brique(
    "FOR7", "formules", "C", (("formules", "age_max"), ("formules", "modes")), brique_for7_dire_la_condition,
    change_la_fiche_du_modele=True, vue_sur_carte=True, sans_la_brique=_sans, carte_d_essai="briques/FOR7",
    phrase="la condition d'âge est un fait du retour ; un mode non permis est refusé avec les modes permis",
))
