"""[.mark] The organization's « Caller verification » settings (L6, V2, V7).

Stored under ``VERIFICATION_APPELANT`` in ``organization_configurations`` (no migration, X3).
Absent: the defaults of the code (G2, a common default), but nothing runs until an agent
switches ``verification_appelant`` on (V7).

⛔ Tenant isolation: always the organization of the run's agent or of the signed-in user.
"""

from __future__ import annotations

from loguru import logger

from api.db import db_client
from api.enums import OrganizationConfigurationKey
from api.schemas.verification import ReglagesVerification

CLE = OrganizationConfigurationKey.VERIFICATION_APPELANT.value
INTERRUPTEUR = "verification_appelant"


def interrupteur_allume(run_configs: dict | None) -> bool:
    return bool((run_configs or {}).get(INTERRUPTEUR))


async def lire_reglages(organization_id: int) -> ReglagesVerification:
    """Never raises: unreadable = the defaults, logged."""
    try:
        ligne = await db_client.get_configuration(organization_id, CLE)
        if ligne is None or not ligne.value:
            return ReglagesVerification()
        return ReglagesVerification.model_validate(ligne.value)
    except Exception as erreur:  # noqa: BLE001 -- the defaults, never a crash
        logger.error(
            f"[.mark] Caller verification settings of organization {organization_id} unreadable, defaults used: {erreur!r}"
        )
        return ReglagesVerification()


async def ecrire_reglages(organization_id: int, reglages: ReglagesVerification) -> ReglagesVerification:
    await db_client.upsert_configuration(organization_id, CLE, reglages.model_dump(mode="json"))
    return reglages
