"""[.mark] The installation's settings (decision of Evan, 07/10, n° 319, option A).

The .mark notification addresses and the backup mail server live in .mark's own
organization (key ``INSTALLATION_MARK`` of ``organization_configurations``, no migration),
shown and changed by superusers only.

Which organization is .mark's: the ONE that holds this key, designated by its id, never by
its name. The first save by a superuser fixes it (from the organization they selected);
a save from any other organization is refused with the holder's id. To move it, delete the
row of the holder (a deliberate gesture, documented in the labo's reference).

⛔ Reading never raises: an alert must not fail because its settings are unreadable.
"""

from __future__ import annotations

from loguru import logger

from api.db import db_client
from api.enums import OrganizationConfigurationKey
from api.schemas.apres_appel import ReglagesInstallation
from api.services.apres_appel.reglages import CleManquante, secret
from api.services.cles_reference import CleIntrouvable

CLE = OrganizationConfigurationKey.INSTALLATION_MARK.value


class InstallationAilleurs(Exception):
    """The settings are already held by another organization (its id in the message)."""

    def __init__(self, organisation_mark: int):
        self.organisation_mark = organisation_mark
        super().__init__(
            f"The installation settings are held by organization {organisation_mark}, "
            ".mark's: change them from there."
        )


async def _porteurs() -> list[dict]:
    return await db_client.get_all_configurations_by_key(CLE)


async def lire_installation() -> tuple[int | None, ReglagesInstallation]:
    """(.mark's organization id, its settings). None and the defaults when nobody holds
    them, or when two organizations do (logged: it must be fixed by hand)."""
    try:
        porteurs = await _porteurs()
        if not porteurs:
            return None, ReglagesInstallation()
        if len(porteurs) > 1:
            ids = sorted(p["organization_id"] for p in porteurs)
            logger.error(
                f"[.mark] Installation settings held by several organizations {ids}: none used."
            )
            return None, ReglagesInstallation()
        porteur = porteurs[0]
        return porteur["organization_id"], ReglagesInstallation.model_validate(
            porteur["value"]
        )
    except Exception as erreur:  # noqa: BLE001
        logger.error(f"[.mark] Installation settings unreadable: {erreur!r}")
        return None, ReglagesInstallation()


async def ecrire_installation(
    organization_id: int, reglages: ReglagesInstallation
) -> None:
    """Saved in ``organization_id`` if it is .mark's, or if nobody holds them yet.
    Raises ``InstallationAilleurs``, or ``CleIntrouvable`` (password not a key of THIS
    organization's « Keys »)."""
    for porteur in await _porteurs():
        if porteur["organization_id"] != organization_id:
            raise InstallationAilleurs(porteur["organization_id"])
    if reglages.smtp.mot_de_passe is not None:
        try:
            await secret(
                reglages.smtp.mot_de_passe,
                organization_id,
                "smtp",
                "the mail server password",
            )
        except CleManquante as erreur:
            raise CleIntrouvable(str(erreur)) from None
    await db_client.upsert_configuration(
        organization_id, CLE, reglages.model_dump(mode="json")
    )
