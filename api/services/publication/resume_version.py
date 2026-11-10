"""[.mark] Clôture, É36 : « Ce qui change » d'une version, en résumé, pour la page Versions de l'agent.

Réutilise la comparaison de la fenêtre Publier (``changements.calculer``) : même regard, aucun appel à un modèle, aucune dépense.
Calculé UNE fois, à la création de la version publiée, puis rangé dans ``resume_changements`` : la page ne recalcule rien et ne
relit pas la version précédente (pas de N+1). Données neutres (comptes, noms d'étapes) : l'écran écrit la phrase, en français ou
en anglais. Pur : rien n'est lu en base ici.
"""

from __future__ import annotations

from typing import Any

from api.services.publication import changements

NOMS_MAX = 3
NOM_LONGUEUR_MAX = 60


def _noms(lignes: list[dict[str, Any]], genre: str) -> tuple[int, list[str]]:
    """Le nombre d'étapes touchées (une étape changée sur plusieurs champs compte une fois) et les premiers noms."""
    vus: list[str] = []
    for ligne in lignes:
        nom = str(ligne.get("ou") or "?")
        if ligne.get("genre") == genre and nom not in vus:
            vus.append(nom)
    return len(vus), [n[:NOM_LONGUEUR_MAX] for n in vus[:NOMS_MAX]]


def resumer(
    graphe: dict[str, Any] | None,
    graphe_precedent: dict[str, Any] | None,
    reglages: dict[str, Any] | None = None,
    reglages_precedents: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Le résumé de ce que cette version change par rapport à la précédente (``total`` : le nombre réel de changements)."""
    calcul = changements.calculer(graphe, graphe_precedent, reglages, reglages_precedents)
    lignes = calcul["lignes"]
    ajoutees, noms_ajoutees = _noms(lignes, "node_added")
    retirees, noms_retirees = _noms(lignes, "node_removed")
    modifiees, noms_modifiees = _noms(lignes, "node_changed")
    return {
        "total": calcul["total"],
        "etapes_ajoutees": ajoutees,
        "noms_ajoutees": noms_ajoutees,
        "etapes_retirees": retirees,
        "noms_retirees": noms_retirees,
        "etapes_modifiees": modifiees,
        "noms_modifiees": noms_modifiees,
        "liaisons": sum(1 for ligne in lignes if str(ligne.get("genre", "")).startswith("link_")),
        "reglages": sum(1 for ligne in lignes if ligne.get("genre") == "setting_changed"),
    }
