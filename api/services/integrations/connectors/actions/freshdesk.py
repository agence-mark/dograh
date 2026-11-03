"""[.mark] Freshdesk (support): open a ticket (U3 sexies, point 8, F3).

State « À essayer ». Documentation read on 03/11/2026: https://developers.freshdesk.com/api/#create_ticket
(``POST /api/v2/tickets``; one requester attribute is mandatory among ``requester_id``, ``email``,
``phone``, ``twitter_id``...; ``status`` 2 = open and ``priority`` 1 = low by default; answer 201
with the ticket's ``id``). ⚠️ The contacts filters (by phone or mobile) were NOT found in the pages
read: no ``find_contact`` here, nothing invented. Through Nango's relay (integration ``freshdesk``,
which knows the account's domain).

- ``create_ticket`` (writes): the requester is the caller (his e-mail when known, else his number).
"""

from __future__ import annotations

from typing import Any

from api.services.integrations.connectors.catalogue import (
    Action,
    Connecteur,
    ContexteAction,
    Parametre,
    declarer,
)
from api.services.integrations.connectors.nango import Requete

REGLAGES = {"priorite": 1}  # 1 low, 2 medium, 3 high, 4 urgent
STATUT_OUVERT = 2


def _ticket(params: dict, ctx: ContexteAction) -> Requete:
    r = {**REGLAGES, **ctx.reglages}
    if int(r["priorite"]) not in (1, 2, 3, 4):
        raise ValueError("Freshdesk: unknown priority.")
    c = ctx.modele.contact
    corps: dict[str, Any] = {
        "subject": str(params["sujet"]).strip()[:200],
        "description": str(params["description"]).strip().replace("\n", "<br>"),
        "status": STATUT_OUVERT,
        "priority": int(r["priorite"]),
    }
    if c.mail:
        corps["email"] = c.mail
    if c.telephone:
        corps["phone"] = c.telephone
    if "email" not in corps and "phone" not in corps:
        raise ValueError("Freshdesk needs the caller's e-mail or number.")
    return Requete("POST", "/api/v2/tickets", json=corps)


def _resultat(reponse: Any, _params: dict, _ctx: ContexteAction) -> dict:
    if not (reponse or {}).get("id"):
        raise ValueError("Freshdesk gave no ticket.")
    return {"cree": True, "identifiant": str(reponse["id"])}


FRESHDESK = declarer(
    Connecteur(
        nom="freshdesk",
        libelle="Freshdesk",
        integration="freshdesk",
        actions=(
            Action(
                nom="create_ticket",
                description="Open a ticket with the caller's request (a breakdown, a complaint, a question).",
                parametres=(
                    Parametre("sujet", description="A short title."),
                    Parametre("description", description="What the caller said, complete."),
                ),
                ecrit=True,
                preparer=_ticket,
                resultat=_resultat,
                reglages_par_defaut=REGLAGES,
            ),
        ),
    )
)
