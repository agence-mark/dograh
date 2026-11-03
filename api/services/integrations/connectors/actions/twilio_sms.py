"""[.mark] Twilio SMS (messages): action (U3 sexies, point 8, F2).

State « À essayer »: written from Twilio's public documentation (Messages resource, ``POST
/2010-04-01/Accounts/{AccountSid}/Messages.json``, form-encoded: https://www.twilio.com/docs/
messaging/api/message-resource), proven on a recorded answer. Through Nango's relay (integration
``twilio``, Basic authorization with the client's own Account SID and token or API key).

- ``send_sms`` (writes, never anticipated): a text message to the number the CALLER gave, never to a
  number the model chooses (it would be a way to send a message to anyone). The client's settings:
  the Account SID (the path needs it), the sender (a number of his Twilio account, or a messaging
  service) and a closing line.
Twilio takes only form-encoded bodies: the relay sends the ``formulaire`` of the request.
"""

from __future__ import annotations

from typing import Any
from urllib.parse import quote

from api.schemas.apres_appel import numero_e164
from api.services.integrations.connectors.catalogue import (
    Action,
    Connecteur,
    ContexteAction,
    Parametre,
    declarer,
)
from api.services.integrations.connectors.nango import Requete

LONGUEUR_MAX = 600  # four SMS segments of 160 characters, then Twilio refuses
REGLAGES = {
    "sid_compte": "",  # AC...
    "expediteur": "",  # a number of the client's Twilio account (E.164) ...
    "service_messagerie": "",  # ... or a messaging service (MG...), which wins when set
    "signature": "",
}


def _preparer(params: dict, ctx: ContexteAction) -> Requete:
    r = {**REGLAGES, **ctx.reglages}
    sid = str(r.get("sid_compte") or "").strip()
    if not (sid.startswith("AC") and sid.isalnum()):
        raise ValueError("Twilio: the Account SID is not set.")
    if not (r.get("expediteur") or r.get("service_messagerie")):
        raise ValueError("Twilio: the sender is not set.")
    destinataire = numero_e164(ctx.modele.contact.telephone)
    if not destinataire:
        raise ValueError("Twilio: the caller's number is unknown, nothing to send to.")
    texte = str(params["message"]).strip()
    if r.get("signature"):
        texte = f"{texte}\n{r['signature']}"
    if len(texte) > LONGUEUR_MAX:
        raise ValueError("The text message is too long.")
    formulaire = {"To": destinataire, "Body": texte}
    if r.get("service_messagerie"):
        formulaire["MessagingServiceSid"] = str(r["service_messagerie"])
    else:
        formulaire["From"] = str(r["expediteur"])
    return Requete("POST", f"/2010-04-01/Accounts/{quote(sid, safe='')}/Messages.json", formulaire=formulaire)


def _resultat(reponse: Any, _params: dict, _ctx: ContexteAction) -> dict:
    sid = (reponse or {}).get("sid")
    if not sid:
        raise ValueError("Twilio gave no message.")
    return {"envoye": True, "statut": (reponse or {}).get("status") or "queued"}


TWILIO_SMS = declarer(
    Connecteur(
        nom="twilio_sms",
        libelle="Twilio SMS",
        integration="twilio",
        actions=(
            Action(
                nom="send_sms",
                description=(
                    "Send a text message to the caller's phone (the number he calls from or gave). "
                    "Use it for what he must keep: an address, a time, a link."
                ),
                parametres=(Parametre("message", description="The text, short and complete, in the caller's language."),),
                ecrit=True,
                preparer=_preparer,
                resultat=_resultat,
                reglages_par_defaut=REGLAGES,
            ),
        ),
    )
)
