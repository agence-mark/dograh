"""[.mark] Where an organization's announcement settings are read and written.

One row of ``organization_configurations``, key ``ANNONCE_OUVERTURE`` (no
migration, same table as the trade vocabulary). Format and bounds:
``api/schemas/annonce_ouverture.py``.

⛔ ``lire_annonce_ouverture`` never raises: it is read when a call is set up, and
a missing or unreadable setting must leave the call exactly as it was without
one -- the default sentences and the state computed from the hours -- never stop
it.
"""

from __future__ import annotations

from loguru import logger

from api.db import db_client
from api.enums import OrganizationConfigurationKey
from api.schemas.annonce_ouverture import ReglagesAnnonceOuverture

CLE = OrganizationConfigurationKey.ANNONCE_OUVERTURE.value


async def lire_annonce_ouverture(organization_id: int | None) -> ReglagesAnnonceOuverture:
    """The organization's settings; the defaults when absent, unreadable or on any error."""
    if organization_id is None:
        return ReglagesAnnonceOuverture()
    try:
        ligne = await db_client.get_configuration(organization_id, CLE)
        if ligne is None or not ligne.value:
            return ReglagesAnnonceOuverture()
        return ReglagesAnnonceOuverture.model_validate(ligne.value)
    except Exception as erreur:  # noqa: BLE001 -- a sentence is never worth a call
        logger.warning(
            f"[.mark] Announcement settings of organization {organization_id} unreadable, "
            f"defaults used: {erreur!r}"
        )
        return ReglagesAnnonceOuverture()


async def lire_annonce_ouverture_strict(
    organization_id: int | None,
) -> ReglagesAnnonceOuverture:
    """The settings, or an exception if the row exists and cannot be read.

    ⛔ For the SCREEN only. The « never raises » rule is made for the call: on the
    screen it would show the default sentences, and the save that follows (a full
    replacement) would overwrite settings that are really there -- the defect the
    independent review of 17/09 found on the trade vocabulary.
    """
    if organization_id is None:
        return ReglagesAnnonceOuverture()
    ligne = await db_client.get_configuration(organization_id, CLE)
    if ligne is None or not ligne.value:
        return ReglagesAnnonceOuverture()
    return ReglagesAnnonceOuverture.model_validate(ligne.value)


async def enregistrer_annonce_ouverture(
    organization_id: int, reglages: ReglagesAnnonceOuverture
) -> ReglagesAnnonceOuverture:
    await db_client.upsert_configuration(
        organization_id, CLE, reglages.model_dump(mode="json")
    )
    return reglages
