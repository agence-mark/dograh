"""[.mark] Les réglages EN VIGUEUR pour un agent : ceux de l'APPEL (le principal) complétés, puis surchargés, par ceux de l'agent.

Avant, ``agent.reglages or moteur.reglages_appel`` rendait les réglages d'un spécialiste dès qu'ils n'étaient pas vides : un interrupteur posé sur le principal
restait éteint pour lui. Un seul endroit fait ce calcul ; toutes les lectures d'un interrupteur « de l'agent qui a la main » passent par lui.
⛔ Ne lève jamais.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any


def reglages_de_l_agent(moteur: Any, agent: Any) -> dict[str, Any]:
    try:
        appel = getattr(moteur, "reglages_appel", None)
        propres = getattr(agent, "reglages", None)
        return {**(appel if isinstance(appel, Mapping) else {}), **(propres if isinstance(propres, Mapping) else {})}
    except Exception:  # noqa: BLE001
        return {}
