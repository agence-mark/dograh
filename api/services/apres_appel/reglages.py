"""[.mark] The after-call settings: the organization's (A1 to A8) and the agent's (A6).

⛔ Tenant isolation: the organization is ALWAYS the one of the run's agent
(``workflow.organization_id``) or of the signed-in user; nothing a call or a request
carries can point at another organization's settings, database or keys.
"""

from __future__ import annotations


from loguru import logger

from api.db import db_client
from api.enums import OrganizationConfigurationKey
from api.schemas.apres_appel import (
    ApresAppelAgent,
    ReglagesApresAppel,
    verifier_adresses,
)
from api.services.cles_reference import CleIntrouvable, _cle, est_reference, uuid_de

CLE = OrganizationConfigurationKey.APRES_APPEL.value
CLE_AGENT = "apres_appel"


async def lire_reglages(organization_id: int) -> ReglagesApresAppel:
    """Never raises: unreadable = the defaults (nothing configured), logged."""
    try:
        ligne = await db_client.get_configuration(organization_id, CLE)
        if ligne is None or not ligne.value:
            return ReglagesApresAppel()
        return ReglagesApresAppel.model_validate(ligne.value)
    except Exception as erreur:  # noqa: BLE001
        logger.error(
            f"[.mark] After-call settings of organization {organization_id} unreadable: {erreur!r}"
        )
        return ReglagesApresAppel()


async def ecrire_reglages(
    organization_id: int, reglages: ReglagesApresAppel
) -> ReglagesApresAppel:
    await db_client.upsert_configuration(
        organization_id, CLE, reglages.model_dump(mode="json")
    )
    return reglages


def reglages_de_lagent(workflow_configurations: dict | None) -> ApresAppelAgent:
    """What the agent switched on. Absent or unreadable = off (X2), never an error."""
    brut = (workflow_configurations or {}).get(CLE_AGENT)
    if not brut:
        return ApresAppelAgent()
    try:
        return ApresAppelAgent.model_validate(brut)
    except Exception as erreur:  # noqa: BLE001
        logger.error(
            f"[.mark] After-call settings of an agent unreadable, read as off: {erreur!r}"
        )
        return ApresAppelAgent()


async def adresses_de_lorganisation(organization_id: int) -> list[str]:
    try:
        ligne = await db_client.get_configuration(
            organization_id, OrganizationConfigurationKey.ORGANIZATION_PREFERENCES.value
        )
        valeurs = ((ligne.value if ligne else None) or {}).get(
            "adresses_notification"
        ) or []
        return verifier_adresses(list(valeurs))
    except Exception as erreur:  # noqa: BLE001
        logger.error(
            f"[.mark] Notification addresses of organization {organization_id} unreadable: {erreur!r}"
        )
        return []


class CleManquante(ValueError):
    """A setting needs a key from « Keys » and has none, or a deleted one. Safe to show."""


async def secret(
    reference: str | None, organization_id: int, fournisseur: str, quoi: str
) -> str:
    """The value of a key of the library, checked to be of the expected provider family.

    ⛔ The value is never logged nor put in an error message."""
    if not reference:
        raise CleManquante(f"No key chosen for {quoi}: pick one in « Keys ».")
    if not est_reference(reference):
        raise CleManquante(f"The {quoi} must be chosen in « Keys », never typed.")
    trouvee = await _cle(uuid_de(reference), organization_id)
    if trouvee is None:
        raise CleManquante(
            f"The key chosen for {quoi} was deleted: pick another in « Keys »."
        )
    valeur, son_fournisseur = trouvee
    if son_fournisseur != fournisseur:
        raise CleManquante(
            f"The key chosen for {quoi} is a {son_fournisseur} key, not a {fournisseur} one."
        )
    return valeur


async def verifier_les_references(
    organization_id: int, reglages: ReglagesApresAppel
) -> None:
    """At save (strict): every reference points at a key of THIS organization, of the
    right provider. Raises ``CleIntrouvable`` with a message to show."""
    for reference, fournisseur, quoi in (
        (reglages.synthese.cle, "mistral", "the summary"),
        (reglages.smtp.mot_de_passe, "smtp", "the mail server password"),
        (reglages.webhook.secret, "webhook", "the webhook secret"),
    ):
        if reference is None:
            continue
        try:
            await secret(reference, organization_id, fournisseur, quoi)
        except CleManquante as erreur:
            raise CleIntrouvable(str(erreur)) from None
