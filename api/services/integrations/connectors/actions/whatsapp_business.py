"""[.mark] WhatsApp Business (messages): a validated template to the caller (U3 sexies, point 8, F3).

State « À essayer ». Documentation read on 03/11/2026: the Cloud API messages reference
(https://developers.facebook.com/docs/whatsapp/cloud-api/reference/messages: ``POST /{Phone-Number-ID}/
messages``, required ``messaging_product``, ``recipient_type``, ``to``, ``type``; the answer holds
``messages[0].id``) and the page on template messages, which says a business-initiated message outside
the 24-hour window must be a template. ⚠️ The exact shape of the ``template`` object (name, language,
components, parameters) is NOT in the pages I could read: it is written from the usual example of
Meta's documentation and stays to be checked on the first test account.
Through Nango's relay (integration ``whatsapp-business``).

- ``send_template`` (writes, never anticipated): to the number the CALLER gave, never to a number the
  model chooses. The template, its language and the sender (phone number id) are the client's settings;
  the model only fills the variables.
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

REGLAGES = {"identifiant_numero": "", "modele": "", "langue": "fr", "version": "v21.0"}
LONGUEUR_VARIABLE = 200


def _preparer(params: dict, ctx: ContexteAction) -> Requete:
    r = {**REGLAGES, **ctx.reglages}
    numero = str(r.get("identifiant_numero") or "").strip()
    if not (numero.isdigit() and r.get("modele")):
        raise ValueError("WhatsApp: the sender number id and the template are not set.")
    destinataire = numero_e164(ctx.modele.contact.telephone)
    if not destinataire:
        raise ValueError("WhatsApp: the caller's number is unknown, nothing to send to.")
    variables = [str(params[n]).strip()[:LONGUEUR_VARIABLE] for n in ("variable_1", "variable_2") if params.get(n)]
    modele: dict[str, Any] = {"name": str(r["modele"]), "language": {"code": str(r["langue"])}}
    if variables:
        modele["components"] = [
            {"type": "body", "parameters": [{"type": "text", "text": v} for v in variables]}
        ]
    return Requete(
        "POST",
        f"/{quote(str(r['version']), safe='')}/{numero}/messages",
        json={
            "messaging_product": "whatsapp",
            "recipient_type": "individual",
            "to": destinataire.lstrip("+"),
            "type": "template",
            "template": modele,
        },
    )


def _resultat(reponse: Any, _params: dict, _ctx: ContexteAction) -> dict:
    messages = (reponse or {}).get("messages") or []
    if not (messages and messages[0].get("id")):
        raise ValueError("WhatsApp gave no message.")
    return {"envoye": True, "statut": messages[0].get("message_status") or "accepted"}


WHATSAPP_BUSINESS = declarer(
    Connecteur(
        nom="whatsapp_business",
        libelle="WhatsApp Business",
        integration="whatsapp-business",
        actions=(
            Action(
                nom="send_template",
                description=(
                    "Send the caller a WhatsApp message built on the business's validated template "
                    "(a confirmation, an address). The variables fill the blanks of the template."
                ),
                parametres=(
                    Parametre("variable_1", description="First blank of the template.", obligatoire=False),
                    Parametre("variable_2", description="Second blank of the template.", obligatoire=False),
                ),
                ecrit=True,
                preparer=_preparer,
                resultat=_resultat,
                reglages_par_defaut=REGLAGES,
            ),
        ),
    )
)
