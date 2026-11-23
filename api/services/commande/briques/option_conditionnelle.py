"""[.mark] Brique OPT6 : l'option conditionnelle, B si A (inventaire, famille 3 ; jamais vue sur les 44 cartes).

Un groupe n'apparaît que si une option est choisie (« avec une salade » ouvre « vinaigrette ») : ``si_option`` porte le code de caisse de l'option qui l'ouvre. Tant qu'elle n'est pas
choisie, le groupe n'existe pas : il n'est ni demandé, ni accepté, ni compté. Code seulement, aucune case nouvelle (D66).
"""

from __future__ import annotations

from typing import Any

from api.services.commande.briques.registre import Brique, enregistrer


def codes_choisis(choix: list[dict[str, Any]]) -> set[str]:
    """Les codes de caisse des options choisies à ce niveau."""
    return {c["option_code"] for c in choix or []}


def brique_opt6_poser_b_si_a(groupe: dict[str, Any], choisis: list[dict[str, Any]]) -> bool:
    """Vrai quand ce groupe est ouvert : il n'a pas de condition, ou l'option qui l'ouvre est choisie."""
    condition = groupe.get("si_option")
    return not condition or condition in codes_choisis(choisis)


def groupes_ouverts(groupes: list[dict[str, Any]], choisis: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [g for g in groupes if brique_opt6_poser_b_si_a(g, choisis)]


def _sans(carte: dict) -> dict:
    for g in carte["groupes"]:
        g["si_option"] = None
    return carte


enregistrer(Brique(
    "OPT6", "options", "C", (("groupes", "si_option"),), brique_opt6_poser_b_si_a,
    change_la_fiche_du_modele=False, vue_sur_carte=False, sans_la_brique=_sans, carte_d_essai="briques/OPT6",
    phrase="rien de nouveau pour le modèle : la question du groupe ne vient que quand son option est choisie",
))
