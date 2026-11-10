"""[.mark] Clôture, SA-3 (D18) : les limites du moteur du planificateur, réglables par organisation (avancé).

Stockées sous ``PLANIFICATEUR_MOTEUR`` dans ``organization_configurations`` (sans migration). Illisible ou absent : les valeurs
d'avant (``ReglagesMoteurPlanificateur()``), jamais une erreur pendant un appel.

⛔ Cloisonnement : l'organisation est toujours celle de l'appel ou du compte connecté.
"""

from __future__ import annotations

from loguru import logger

from api.db import db_client
from api.enums import OrganizationConfigurationKey
from api.schemas.planificateur import ReglagesMoteurPlanificateur

CLE = OrganizationConfigurationKey.PLANIFICATEUR_MOTEUR.value


async def lire_reglages(organization_id: int) -> ReglagesMoteurPlanificateur:
    """Never raises: unreadable = the values of before, logged."""
    try:
        ligne = await db_client.get_configuration(organization_id, CLE)
        if ligne is None or not ligne.value:
            return ReglagesMoteurPlanificateur()
        return ReglagesMoteurPlanificateur.model_validate(ligne.value)
    except Exception as erreur:  # noqa: BLE001 -- the values of before, never a crash during a call
        logger.error(f"[.mark] Planner engine settings of organization {organization_id} unreadable, defaults used: {erreur!r}")
        return ReglagesMoteurPlanificateur()


async def ecrire_reglages(organization_id: int, reglages: ReglagesMoteurPlanificateur) -> ReglagesMoteurPlanificateur:
    await db_client.upsert_configuration(organization_id, CLE, reglages.model_dump(mode="json"))
    return reglages
