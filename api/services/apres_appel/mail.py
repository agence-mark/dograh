"""[.mark] The mail server of the organization (A4, A5): a generic SMTP (Q1: the sending
service is chosen at the Scaleway migration). The password is a key of « Keys »,
never typed in the settings.

The standard library's ``smtplib`` in a thread: no dependency added (R5).
« Sent » means the server accepted the mail; « delivered » needs the service's own
receipts (Q1), so it stays unknown here.
"""

from __future__ import annotations

import asyncio
import smtplib
import ssl
from email.message import EmailMessage
from email.utils import formataddr, make_msgid

from api.schemas.apres_appel import ReglagesSmtp
from api.services.apres_appel.reglages import secret

DELAI_S = 20


class MailImpossible(RuntimeError):
    """Not configured, refused or unreachable. Message safe to show (never the password).
    ``definitif``: retrying will not help (a setting is missing or wrong)."""

    def __init__(self, message: str, definitif: bool = False):
        super().__init__(message)
        self.definitif = definitif


async def mot_de_passe(smtp: ReglagesSmtp, organization_id: int) -> str | None:
    if not smtp.mot_de_passe:
        return None
    return await secret(
        smtp.mot_de_passe, organization_id, "smtp", "the mail server password"
    )


def _envoyer(smtp: ReglagesSmtp, mdp: str | None, message: EmailMessage) -> None:
    contexte = ssl.create_default_context()
    if smtp.securite == "ssl":
        serveur = smtplib.SMTP_SSL(
            smtp.hote, smtp.port, timeout=DELAI_S, context=contexte
        )
    else:
        serveur = smtplib.SMTP(smtp.hote, smtp.port, timeout=DELAI_S)
    try:
        if smtp.securite == "starttls":
            serveur.starttls(context=contexte)
        if smtp.utilisateur:
            serveur.login(smtp.utilisateur, mdp or "")
        serveur.send_message(message)
    finally:
        try:
            serveur.quit()
        except Exception:  # noqa: BLE001
            pass


async def envoyer(
    smtp: ReglagesSmtp,
    organization_id: int,
    destinataires: list[str],
    sujet: str,
    texte: str,
) -> str:
    """Send one mail; returns its Message-ID. Raises ``MailImpossible``."""
    if not smtp.configure:
        raise MailImpossible(
            "No mail server set in « After the call » (server and sender).",
            definitif=True,
        )
    if not destinataires:
        raise MailImpossible("No recipient.", definitif=True)
    try:
        mdp = await mot_de_passe(smtp, organization_id)
    except ValueError as erreur:
        raise MailImpossible(str(erreur), definitif=True) from None
    message = EmailMessage()
    message["From"] = formataddr((smtp.nom_expediteur or "", smtp.expediteur))
    message["To"] = ", ".join(destinataires)
    message["Subject"] = sujet
    identifiant = make_msgid(domain=smtp.expediteur.split("@")[-1])
    message["Message-ID"] = identifiant
    message.set_content(texte)
    try:
        await asyncio.to_thread(_envoyer, smtp, mdp, message)
    except smtplib.SMTPAuthenticationError:
        raise MailImpossible(
            "The mail server refused the user or the password.", definitif=True
        ) from None
    except smtplib.SMTPRecipientsRefused:
        raise MailImpossible(
            "The mail server refused the recipient.", definitif=True
        ) from None
    except (smtplib.SMTPException, OSError) as erreur:
        raise MailImpossible(
            f"The mail server did not take the mail ({type(erreur).__name__})."
        ) from None
    return identifiant
