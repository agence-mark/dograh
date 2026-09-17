"""[.mark] The agent's switches for the trade vocabulary, read defensively.

⛔ Same defence as the other switches of the call: a stored configuration
carries explicit JSON nulls for keys nobody ever touched, and a value typed by
hand can be anything. The switch is read ALONE, never through the whole schema,
so a neighbouring setting out of bounds never turns the vocabulary off (rule of
the towns check, 2026-09-16).
"""

from __future__ import annotations

from loguru import logger

from api.schemas.lexique_metier import LexiqueMetier
from api.schemas.workflow_configurations import (
    DEFAULT_LEXIQUE_METIER,
    WorkflowConfigurationDefaults,
)
from api.services.lexique.stockage import lire_lexique


def interrupteur_allume(run_configs: dict | None) -> bool:
    """La clé lue SEULE par le schéma, comme les interrupteurs voisins : une valeur
    tapée à la main (« false » en texte) doit s'éteindre ici comme ailleurs."""
    try:
        return WorkflowConfigurationDefaults.model_validate(
            {"lexique_metier": (run_configs or {}).get("lexique_metier")}
        ).lexique_metier
    except Exception as erreur:  # noqa: BLE001 -- the call must go on
        logger.warning(f"[.mark] Trade vocabulary switch unreadable, left on: {erreur!r}")
        return DEFAULT_LEXIQUE_METIER


async def lire_lexique_de_lappel(run_configs: dict | None, organization_id: int | None) -> LexiqueMetier:
    """The vocabulary this call uses: empty when the agent's switch is off.

    ⛔ Never raises (``lire_lexique``): a vocabulary problem costs a call nothing.
    """
    if not interrupteur_allume(run_configs):
        return LexiqueMetier()
    return await lire_lexique(organization_id)
