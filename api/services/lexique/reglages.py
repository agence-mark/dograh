"""[.mark] The agent's switches for the trade vocabulary, read defensively.

⛔ Same defence as the other switches of the call: a stored configuration
carries explicit JSON nulls for keys nobody ever touched, and a value typed by
hand can be anything. The switch is read ALONE, never through the whole schema,
so a neighbouring setting out of bounds never turns the vocabulary off (rule of
the towns check, 2026-09-16).
"""

from __future__ import annotations

from api.schemas.lexique_metier import LexiqueMetier
from api.schemas.workflow_configurations import DEFAULT_LEXIQUE_METIER
from api.services.lexique.stockage import lire_lexique


def interrupteur_allume(run_configs: dict | None) -> bool:
    valeur = (run_configs or {}).get("lexique_metier")
    return DEFAULT_LEXIQUE_METIER if valeur is None else bool(valeur)


async def lire_lexique_de_lappel(run_configs: dict | None, organization_id: int | None) -> LexiqueMetier:
    """The vocabulary this call uses: empty when the agent's switch is off.

    ⛔ Never raises (``lire_lexique``): a vocabulary problem costs a call nothing.
    """
    if not interrupteur_allume(run_configs):
        return LexiqueMetier()
    return await lire_lexique(organization_id)
