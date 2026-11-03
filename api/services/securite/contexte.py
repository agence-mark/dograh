"""[.mark] Ce que le garde de sortie sait de l'agent à cet instant, lu dans le moteur (U3 quinquies, couche 2).

Relu à chaque réplique : l'étape (donc le prompt et les outils offerts) change pendant l'appel. Le moteur est le même au téléphone
et au clavier. ⛔ Ne lève jamais.
"""

from __future__ import annotations

from typing import Any, Callable

from api.services.securite import textes
from api.services.securite.garde_sortie import Contexte


def _valeurs_de_texte(*dictionnaires: Any) -> list[str]:
    valeurs: list[str] = []
    for d in dictionnaires:
        if isinstance(d, dict):
            valeurs.extend(str(v) for v in d.values() if isinstance(v, (str, int, float)) and len(str(v)) >= 3)
    return valeurs


def depuis_le_moteur(moteur: Any) -> Callable[[], Contexte]:
    """Un rappel qui rend le contexte du garde d'après le moteur de l'appel."""

    def lire() -> Contexte:
        try:
            agent = getattr(moteur, "active_agent", None)
            outils = getattr(getattr(agent, "tools", None), "standard_tools", None) or []
            noms = [getattr(o, "name", None) or (o.get("name") if isinstance(o, dict) else None) for o in outils]
            prompt = str(getattr(agent, "system_prompt", "") or "")
            # les consignes de sécurité elles-mêmes ne sont pas une « consigne récitée » à protéger
            if textes.ENTETE in prompt:
                prompt = prompt.split(textes.ENTETE)[0]
            appel = getattr(moteur, "_gathered_context", None) or {}
            exclusions = _valeurs_de_texte(appel.get("extracted_variables"), appel.get("initial_context"), appel.get("template_context_variables"))
            return Contexte(noms_d_outils=[n for n in noms if n], consignes=prompt, exclusions=exclusions)
        except Exception:  # noqa: BLE001
            return Contexte()

    return lire
