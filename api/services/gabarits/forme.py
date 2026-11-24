"""[.mark] Chantier Partie 1, lot 4 (n° 149, 150) : la FORME d'un agent installé, numérotée, et sa montée d'une forme ancienne à la forme actuelle.

La base des retouches (ce que le gabarit avait installé, étape par étape) est rangée dans l'application. Elle porte son numéro de forme (``forme``).
Forme 2 (actuelle) : ``{"forme": 2, "noeuds": {id: {type, prompt, greeting, outils, reglages}}, "sorties": [{source, cible, condition, fermee_si_action_ouverte,
garde_l_action_ouverte}]}``. Avant (sans numéro) : des sorties en listes à quatre ou cinq éléments, des nœuds sans ``reglages``. Le code ne lit plus que la forme
actuelle ; une base ancienne se monte UNE fois par ``api/outils/monter_la_forme.py`` (idempotent : une base déjà montée n'est pas touchée).
"""

from __future__ import annotations

from typing import Any

FORME_ACTUELLE = 2
CHAMPS_D_UNE_SORTIE = ("source", "cible", "condition", "fermee_si_action_ouverte", "garde_l_action_ouverte")


class FormeAMonter(Exception):
    """Une base de retouches d'une forme ancienne : à monter avant toute comparaison (jamais lue de travers)."""


def exiger_la_forme_actuelle(base: dict[str, Any] | None) -> None:
    if base and base.get("forme") != FORME_ACTUELLE:
        raise FormeAMonter("La base des retouches d'un agent installé est d'une forme ancienne : lancer ``python -m api.outils.monter_la_forme``.")


def _sortie_nommee(sortie: Any) -> Any:
    """Une sortie ancienne (liste à quatre éléments : la garde de l'action ouverte est venue s'y ajouter, cinq) devient un dictionnaire nommé."""
    if not isinstance(sortie, (list, tuple)):
        return sortie
    valeurs = [*sortie, *([False] * (len(CHAMPS_D_UNE_SORTIE) - len(sortie)))]
    return dict(zip(CHAMPS_D_UNE_SORTIE, valeurs, strict=False))


def monter(base: dict[str, Any], actuelle: dict[str, Any] | None = None) -> dict[str, Any]:
    """La base à la forme actuelle. ``actuelle`` : la forme de l'agent tel qu'il est : une base d'avant les réglages d'étape valait ce que l'agent porte, elle en reprend
    les réglages (jamais une retouche). Idempotente : une base déjà à la forme actuelle est rendue telle quelle."""
    if base.get("forme") == FORME_ACTUELLE:
        return base
    portes = (actuelle or {}).get("noeuds") or {}
    noeuds = {}
    for i, n in (base.get("noeuds") or {}).items():
        if isinstance(n, dict) and "reglages" not in n:
            n = {**n, "reglages": (portes.get(i) or {}).get("reglages") or {}}
        noeuds[i] = n
    return {"forme": FORME_ACTUELLE, "noeuds": noeuds, "sorties": [_sortie_nommee(s) for s in base.get("sorties") or []]}
