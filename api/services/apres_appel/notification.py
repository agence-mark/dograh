"""[.mark] The notification addresses (A5, PN6): where a failure is told.

Two lists: the organization's own (``adresses_notification`` of its preferences, theme
« Organization »: only its own calls) and the .mark addresses of the installation
(``MARK_ADRESSES_NOTIFICATION``: everything). A failed after-call step, a failed night
task, later a call to call back after a breakdown (L7) go to both.

The mail leaves through the organization's mail server; an organization without one
uses the installation's (``MARK_SMTP_URL``, ``smtp[s]://user:password@host:port?from=…``,
read from the environment like ``MARK_BASES_CLIENTS_URL``). Neither: the failure stays
in the log and on screen, never silent.

⛔ A notification never raises: telling a failure must not make a second one.
"""

from __future__ import annotations

import os
from urllib.parse import parse_qs, unquote, urlsplit

from loguru import logger

from api.schemas.apres_appel import ReglagesSmtp
from api.services.apres_appel import mail
from api.services.apres_appel.reglages import (
    adresses_de_lorganisation,
    adresses_mark,
    lire_reglages,
)

VARIABLE_SMTP = "MARK_SMTP_URL"


def smtp_de_linstallation() -> tuple[ReglagesSmtp, str | None] | None:
    brut = os.environ.get(VARIABLE_SMTP, "").strip()
    if not brut:
        return None
    try:
        m = urlsplit(brut)
        options = parse_qs(m.query)
        securite = (options.get("securite") or [None])[0] or (
            "ssl" if m.scheme == "smtps" else "starttls"
        )
        smtp = ReglagesSmtp(
            hote=m.hostname,
            port=m.port or (465 if securite == "ssl" else 587),
            securite=securite,
            utilisateur=unquote(m.username) if m.username else None,
            expediteur=(options.get("from") or [None])[0],
            nom_expediteur=(options.get("nom") or [".mark"])[0],
        )
        return smtp, unquote(m.password) if m.password else None
    except Exception as erreur:  # noqa: BLE001 -- the message must not carry the password
        logger.error(f"[.mark] {VARIABLE_SMTP} unreadable ({type(erreur).__name__})")
        return None


async def _envoyer_installation(destinataires, sujet, texte) -> bool:
    installation = smtp_de_linstallation()
    if installation is None or not installation[0].configure:
        return False
    smtp, mdp = installation
    import asyncio
    from email.message import EmailMessage
    from email.utils import formataddr

    message = EmailMessage()
    message["From"] = formataddr((smtp.nom_expediteur or "", smtp.expediteur))
    message["To"] = ", ".join(destinataires)
    message["Subject"] = sujet
    message.set_content(texte)
    await asyncio.to_thread(mail._envoyer, smtp, mdp, message)
    return True


async def notifier(organization_id: int | None, sujet: str, texte: str) -> list[str]:
    """Send the alert; returns the addresses it went to (empty: nowhere, logged)."""
    destinataires: list[str] = []
    try:
        if organization_id is not None:
            destinataires += await adresses_de_lorganisation(organization_id)
        for adresse in adresses_mark():
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
        if await _envoyer_installation(destinataires, sujet_complet, texte):
            return destinataires
        logger.error(f"[.mark] Alert not mailed (no mail server): {sujet}")
        return []
    except Exception as erreur:  # noqa: BLE001
        logger.error(
            f"[.mark] Alert not mailed ({type(erreur).__name__}: {erreur}): {sujet}"
        )
        return []
