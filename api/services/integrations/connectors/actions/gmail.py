"""[.mark] Gmail (e-mail): action (U3 sexies, point 8, F2).

State « À essayer »: written from Google's public documentation (Gmail API ``users.messages.send``,
https://developers.google.com/workspace/gmail/api/reference/rest/v1/users.messages/send), proven
on a recorded answer. Through Nango's relay (integration ``google-mail``).

- ``send_email`` (writes, never anticipated): a message from the connected mailbox to the address
  the CALLER gave (the common model of the call), never to an address the model invents. The body
  is an RFC 2822 message, UTF-8, sent as base64url in ``raw``. The client's settings: the sender's
  display name, the subject prefix and a closing line.
"""

from __future__ import annotations

import base64
import re
from email.message import EmailMessage
from email.policy import SMTP
from typing import Any

from api.services.integrations.connectors.catalogue import (
    Action,
    Connecteur,
    ContexteAction,
    Parametre,
    declarer,
)
from api.services.integrations.connectors.nango import Requete

REGLAGES = {"prefixe_objet": "", "signature": ""}
_ADRESSE = re.compile(r"^[^@\s<>,;]+@[^@\s<>,;]+\.[^@\s<>,;]+$")


def message_brut(destinataire: str, objet: str, texte: str) -> str:
    """The message in Gmail's format: RFC 2822, UTF-8, base64url without padding."""
    m = EmailMessage(policy=SMTP)
    m["To"] = destinataire
    m["Subject"] = objet
    m.set_content(texte, charset="utf-8")
    return base64.urlsafe_b64encode(m.as_bytes()).decode("ascii").rstrip("=")


def _preparer(params: dict, ctx: ContexteAction) -> Requete:
    r = {**REGLAGES, **ctx.reglages}
    destinataire = str(ctx.modele.contact.mail or "").strip()
    if not _ADRESSE.match(destinataire):
        raise ValueError("Gmail: the caller's e-mail address is unknown, nothing to send to.")
    objet = " ".join(f"{r.get('prefixe_objet') or ''} {params['objet']}".split())
    texte = str(params["message"]).strip()
    if r.get("signature"):
        texte = f"{texte}\n\n{r['signature']}"
    return Requete(
        "POST",
        "/gmail/v1/users/me/messages/send",
        json={"raw": message_brut(destinataire, objet, texte)},
    )


def _resultat(reponse: Any, _params: dict, _ctx: ContexteAction) -> dict:
    if not (reponse or {}).get("id"):
        raise ValueError("Gmail gave no message.")
    return {"envoye": True}


GMAIL = declarer(
    Connecteur(
        nom="gmail",
        libelle="Gmail",
        integration="google-mail",
        actions=(
            Action(
                nom="send_email",
                description="Send an e-mail to the caller, at the address he gave. Use it for what he must keep: a confirmation, a document, a link.",
                parametres=(
                    Parametre("objet", description="The subject, short."),
                    Parametre("message", description="The text of the e-mail, in the caller's language."),
                ),
                ecrit=True,
                preparer=_preparer,
                resultat=_resultat,
                reglages_par_defaut=REGLAGES,
            ),
        ),
    )
)
