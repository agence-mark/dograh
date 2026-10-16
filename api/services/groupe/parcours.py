"""[.mark] Chantier agents-specialises, lot 7 (D91) : le parcours d'un appel, agent par agent.

``nodes_visited`` dédoublonne par NOM d'étape : quand deux agents ont une étape du même nom, ou
quand le principal reprend la main après un spécialisé, l'ordre se perd. Le parcours garde une
entrée par entrée dans une étape, avec l'agent qui la porte, et se rend « Agent › étape › étape ».

Aucun mot de métier : des noms d'agents et d'étapes venus de la configuration.
"""

from __future__ import annotations

from typing import Any, Iterable, Mapping

SEPARATEUR_DE_PARCOURS = " › "


def rendre_le_parcours(entrees: Iterable[Mapping[str, Any]]) -> str:
    """« Agent › étape › étape › Autre agent › étape » : le nom de l'agent s'écrit quand l'agent
    change (un retour chez le même agent plus tard l'écrit de nouveau). Rend ``""`` sans entrée.
    ⛔ Ne lève jamais."""
    try:
        morceaux: list[str] = []
        courant: Any = object()
        for entree in entrees:
            cle = entree.get("agent_id") or entree.get("agent")
            if cle != courant:
                courant = cle
                morceaux.append(
                    str(entree.get("agent") or f"Agent {entree.get('agent_id') or ''}".strip())
                )
            morceaux.append(str(entree.get("etape") or "?"))
        return SEPARATEUR_DE_PARCOURS.join(morceaux)
    except Exception:  # noqa: BLE001
        return ""
