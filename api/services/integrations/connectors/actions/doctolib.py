"""[.mark] Doctolib: the booking link by SMS (U3 sexies, point 8, F3).

Doctolib opens no API to us: the agent sends the booking page of the practitioner to the caller by
SMS, and he books himself. No Doctolib documentation to read for that; the SMS is Twilio's (see
``twilio_sms.py``, state « À essayer »): same connection (integration ``twilio``), same form body.

- ``send_booking_link`` (writes, never anticipated): to the number the CALLER gave, never to one the
  model chooses. Settings: the practitioner's page (it must be a Doctolib address, so that the action
  cannot be turned into a way to send any link), the Twilio account and sender, the text.
"""

from __future__ import annotations

from typing import Any
from urllib.parse import quote, urlsplit

from api.schemas.apres_appel import numero_e164
from api.services.integrations.connectors.actions.twilio_sms import LONGUEUR_MAX
from api.services.integrations.connectors.catalogue import (
    Action,
    Connecteur,
    ContexteAction,
    declarer,
)
from api.services.integrations.connectors.nango import Requete

HOTES_PERMIS = ("www.doctolib.fr", "doctolib.fr")
REGLAGES = {
    "page": "",  # https://www.doctolib.fr/...
    "sid_compte": "",
    "expediteur": "",
    "service_messagerie": "",
    "texte": "Voici le lien pour prendre rendez-vous :",
}


def _page(r: dict) -> str:
    morceaux = urlsplit(str(r.get("page") or "").strip())
    if morceaux.scheme != "https" or morceaux.hostname not in HOTES_PERMIS or morceaux.username or morceaux.port:
        raise ValueError("Doctolib: the practitioner's page must be a https://www.doctolib.fr address.")
    return morceaux.geturl()


def _preparer(_params: dict, ctx: ContexteAction) -> Requete:
    r = {**REGLAGES, **ctx.reglages}
    page = _page(r)
    sid = str(r.get("sid_compte") or "").strip()
    if not (sid.startswith("AC") and sid.isalnum()):
        raise ValueError("Doctolib: the Twilio Account SID is not set.")
    if not (r.get("expediteur") or r.get("service_messagerie")):
        raise ValueError("Doctolib: the SMS sender is not set.")
    destinataire = numero_e164(ctx.modele.contact.telephone)
    if not destinataire:
        raise ValueError("Doctolib: the caller's number is unknown, nothing to send to.")
    corps = f"{str(r['texte']).strip()}\n{page}"
    if len(corps) > LONGUEUR_MAX:
        raise ValueError("The text message is too long.")
    formulaire = {"To": destinataire, "Body": corps}
    if r.get("service_messagerie"):
        formulaire["MessagingServiceSid"] = str(r["service_messagerie"])
    else:
        formulaire["From"] = str(r["expediteur"])
    return Requete("POST", f"/2010-04-01/Accounts/{quote(sid, safe='')}/Messages.json", formulaire=formulaire)


def _resultat(reponse: Any, _params: dict, _ctx: ContexteAction) -> dict:
    if not (reponse or {}).get("sid"):
        raise ValueError("Twilio gave no message.")
    return {"envoye": True, "statut": (reponse or {}).get("status") or "queued"}


DOCTOLIB = declarer(
    Connecteur(
        nom="doctolib",
        libelle="Doctolib",
        integration="twilio",
        actions=(
            Action(
                nom="send_booking_link",
                description="Send the caller, by text message, the link to book with the practitioner himself.",
                parametres=(),
                ecrit=True,
                preparer=_preparer,
                resultat=_resultat,
                reglages_par_defaut=REGLAGES,
            ),
        ),
    )
)
