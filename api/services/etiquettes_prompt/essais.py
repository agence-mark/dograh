"""[.mark] Lot 8 (§ 3 bis, point 7) : un outil cité par une étiquette d'un prompt mais jamais appelé pendant un test.

C'est un AVERTISSEMENT rangé avec le résultat du test, jamais un échec seul : le test garde son statut.
"""

from __future__ import annotations

from typing import Any

from api.services.etiquettes_prompt import familles as f


async def fonctions_citees(organisation_id: int, graphe: dict | None) -> dict[str, str]:
    """``{nom de la fonction: libellé de l'outil}`` des outils cités par une étiquette du graphe. Ne lève jamais."""
    from api.services.etiquettes_prompt.catalogue import textes_du_brouillon
    from api.services.etiquettes_prompt.table import construire

    try:
        textes = [t for _c, _n, _e, t, _d in textes_du_brouillon(graphe, None)]
        if not any(e.famille == f.OUTIL for t in textes for e in f.etiquettes_de(t)):
            return {}
        table = await construire(organisation_id, textes)
        return {fonction: fonction for fonction in table.outils.values()}
    except Exception:  # noqa: BLE001 -- un avertissement manqué ne fait pas tomber une suite de tests
        return {}


def outils_cites_jamais_appeles(cites: dict[str, str], essais: list[dict[str, Any]]) -> list[dict[str, str]]:
    """Pure. Un avertissement par outil cité qu'aucun essai réussi ou raté n'a appelé (essais en erreur exclus)."""
    joues = [e for e in essais if not e.get("erreur")]
    if not cites or not joues:
        return []
    appeles = {nom for e in joues for nom in e.get("outils_appeles") or []}
    return [
        {"type": "outil_cite_jamais_appele", "outil": fonction, "message": f"The prompt cites the tool « {fonction} » but the test never called it."}
        for fonction in sorted(cites)
        if fonction not in appeles
    ]
