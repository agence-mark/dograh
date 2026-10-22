"""[.mark] Where the retention settings of an organization are read and written (cloture-code, lot 6).

One row of ``organization_configurations`` per key (no migration), same pattern as the announcement
(``services/annonce/stockage.py``): ``lire_reglages`` never raises (it is read when a call is set up, and an
unreadable setting must leave the call as the defaults make it -- audio NOT recorded), ``lire_reglages_strict``
is for the screen only (a save is a full replacement: never show defaults over settings that are really there).
"""

from __future__ import annotations

from loguru import logger

from api.constants import ENABLE_CALL_RECORDING_UPLOAD
from api.db import db_client
from api.enums import OrganizationConfigurationKey
from api.schemas.conservation_appels import (
    BilanDuPassage,
    ReglagesConservationAppels,
    VueConservationAppels,
)

CLE = OrganizationConfigurationKey.CONSERVATION_APPELS.value
CLE_BILAN = OrganizationConfigurationKey.CONSERVATION_APPELS_BILAN.value


def audio_autorise_par_l_installation() -> bool:
    """The ceiling: ``ENABLE_CALL_RECORDING_UPLOAD`` at ``false`` forbids the audio whatever a setting says."""
    return ENABLE_CALL_RECORDING_UPLOAD


def audio_voulu(reglages: ReglagesConservationAppels | None) -> bool:
    """Does the organization want the audio recorded? ``None``: a caller that knows no settings (the former path,
    the tests of the upstream flag) -- the ceiling alone decides, as before. A call always passes the settings."""
    return True if reglages is None else bool(reglages.audio_enregistre)


async def lire_reglages(organization_id: int | None) -> ReglagesConservationAppels:
    """The organization's settings; .mark's defaults when absent, unreadable or on any error."""
    if organization_id is None:
        return ReglagesConservationAppels()
    try:
        ligne = await db_client.get_configuration(organization_id, CLE)
        if ligne is None or not ligne.value:
            return ReglagesConservationAppels()
        return ReglagesConservationAppels.model_validate(ligne.value)
    except Exception as erreur:  # noqa: BLE001 -- a retention setting is never worth a call
        logger.warning(
            f"[.mark] Retention settings of organization {organization_id} unreadable, defaults used: {erreur!r}"
        )
        return ReglagesConservationAppels()


async def lire_reglages_strict(organization_id: int) -> ReglagesConservationAppels:
    """The settings, or an exception if the row exists and cannot be read. For the SCREEN only."""
    ligne = await db_client.get_configuration(organization_id, CLE)
    if ligne is None or not ligne.value:
        return ReglagesConservationAppels()
    return ReglagesConservationAppels.model_validate(ligne.value)


async def enregistrer_reglages(
    organization_id: int, reglages: ReglagesConservationAppels
) -> ReglagesConservationAppels:
    await db_client.upsert_configuration(organization_id, CLE, reglages.model_dump(mode="json"))
    return reglages


async def lire_bilan(organization_id: int) -> BilanDuPassage | None:
    """The last night's result; ``None`` when there is none or it cannot be read."""
    try:
        ligne = await db_client.get_configuration(organization_id, CLE_BILAN)
        if ligne is None or not ligne.value:
            return None
        return BilanDuPassage.model_validate(ligne.value)
    except Exception as erreur:  # noqa: BLE001
        logger.warning(f"[.mark] Retention result of organization {organization_id} unreadable: {erreur!r}")
        return None


async def ecrire_bilan(organization_id: int, bilan: BilanDuPassage) -> None:
    await db_client.upsert_configuration(organization_id, CLE_BILAN, bilan.model_dump(mode="json"))


async def vue_de_l_ecran(organization_id: int) -> VueConservationAppels:
    return VueConservationAppels(
        reglages=await lire_reglages_strict(organization_id),
        audio_autorise_par_l_installation=audio_autorise_par_l_installation(),
        dernier_passage=await lire_bilan(organization_id),
    )
