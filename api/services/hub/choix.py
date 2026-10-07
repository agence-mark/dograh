"""[.mark] Which translator an organization uses for each domain (« Integrations », L4).

Stored under ``TRADUCTEURS`` in ``organization_configurations`` (a free-text key of the
existing table: no migration of Dograh, X3). Nothing chosen = the domain is off: an action
that needs it says so, never a silent guess (X2).

⛔ Tenant isolation: always the organization of the run's agent or of the signed-in user.
"""

from __future__ import annotations

from loguru import logger

from api.db import db_client
from api.enums import OrganizationConfigurationKey
from api.schemas.traducteurs import ChoixTraducteurs

CLE = OrganizationConfigurationKey.TRADUCTEURS.value


async def lire_choix(organization_id: int | None) -> ChoixTraducteurs:
    """Never raises: unreadable or absent = nothing chosen."""
    if not organization_id:
        return ChoixTraducteurs()
    try:
        ligne = await db_client.get_configuration(organization_id, CLE)
        if ligne is None or not ligne.value:
            return ChoixTraducteurs()
        return ChoixTraducteurs.model_validate(ligne.value)
    except Exception as erreur:
        logger.error(
            f"[.mark] Translators of organization {organization_id} unreadable, none used: {erreur!r}"
        )
        return ChoixTraducteurs()


async def ecrire_choix(
    organization_id: int, choix: ChoixTraducteurs
) -> ChoixTraducteurs:
    await db_client.upsert_configuration(
        organization_id, CLE, choix.model_dump(mode="json")
    )
    return choix
