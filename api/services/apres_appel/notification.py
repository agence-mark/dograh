"""[.mark] The notification addresses (A5, PN6): where a failure is told.

Two lists: the organization's own (``adresses_notification`` of its preferences, theme
« Organization »: only its own calls) and the .mark addresses of the installation (all
calls), kept in .mark's organization (decision of Evan, 07/10, n° 319:
``services/apres_appel/installation.py``). A failed after-call step, a failed night task,
a call to call back after a breakdown go to both.

The mail leaves through the organization's mail server; an organization without one uses
the installation's backup server (same settings, its password a key of .mark's « Keys »).
Neither: the failure stays in the log and on screen, never silent. The former variables
``MARK_ADRESSES_NOTIFICATION`` and ``MARK_SMTP_URL`` are gone (one place, on screen).

⛔ A notification never raises: telling a failure must not make a second one.
"""

from __future__ import annotations

from loguru import logger

from api.services.apres_appel import mail
from api.services.apres_appel.installation import lire_installation
from api.services.apres_appel.reglages import adresses_de_lorganisation, lire_reglages


async def smtp_de_secours_configure() -> bool:
    _, reglages = await lire_installation()
    return reglages.smtp.configure


async def notifier(organization_id: int | None, sujet: str, texte: str) -> list[str]:
    """Send the alert; returns the addresses it went to (empty: nowhere, logged)."""
    destinataires: list[str] = []
    try:
        if organization_id is not None:
            destinataires += await adresses_de_lorganisation(organization_id)
        organisation_mark, installation = await lire_installation()
        for adresse in installation.adresses_notification:
            if adresse.lower() not in {d.lower() for d in destinataires}:
                destinataires.append(adresse)
        if not destinataires:
            logger.error(f"[.mark] Alert with no notification address: {sujet}")
            return []
        sujet_complet = f"[.mark] {sujet}"
        if organization_id is not None:
            reglages = await lire_reglages(organization_id)
            if reglages.smtp.configure:
                await mail.envoyer(
                    reglages.smtp, organization_id, destinataires, sujet_complet, texte
                )
                return destinataires
        if organisation_mark is not None and installation.smtp.configure:
            await mail.envoyer(
                installation.smtp,
                organisation_mark,
                destinataires,
                sujet_complet,
                texte,
            )
            return destinataires
        logger.error(f"[.mark] Alert not mailed (no mail server): {sujet}")
        return []
    except Exception as erreur:  # noqa: BLE001
        logger.error(
            f"[.mark] Alert not mailed ({type(erreur).__name__}: {erreur}): {sujet}"
        )
        return []
