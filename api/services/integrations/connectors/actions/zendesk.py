"""[.mark] Zendesk (support): find a user, create him, open a ticket (U3 sexies, point 8, F3).

State « À essayer ». Documentation read on 03/11/2026: tickets
(https://developer.zendesk.com/api-reference/ticketing/tickets/tickets/: ``POST /api/v2/tickets``, body
``{"ticket": {"subject", "comment": {"body"}, "priority", "requester" | "requester_id"}}``, priority
urgent/high/normal/low, answer ``ticket.id``; no phone field on ``requester``), users
(``GET /api/v2/users/search?query=`` matches name, email, phone; ``POST /api/v2/users`` body
``{"user": {"name", "email", "phone"}}``, E.164 phone, answer ``user.id``) and search
(``GET /api/v2/search?query=type:user phone:...``, ``results[]`` with ``id`` and ``name``).
Through Nango's relay (integration ``zendesk``, which knows the account's subdomain).

- ``find_contact`` (reads): users by the caller's number. ``create_contact`` (writes).
- ``create_ticket`` (writes): the subject and the description are the caller's request; the caller's
  number goes into the description (the requester has no phone field).
"""

from __future__ import annotations

from typing import Any

from api.services.integrations.connectors.actions._commun import (
    action_creer_contact,
    action_trouver,
    criteres,
    identite,
    nom_complet,
    resultat_creation,
    trouves,
)
from api.services.integrations.connectors.catalogue import (
    Action,
    Connecteur,
    ContexteAction,
    Parametre,
    declarer,
)
from api.services.integrations.connectors.nango import Requete

REGLAGES_TICKET = {"priorite": "normal"}
PRIORITES = ("urgent", "high", "normal", "low")


def _chercher(params: dict, ctx: ContexteAction) -> Requete:
    formes, mail = criteres(params, ctx)
    terme = f"phone:{formes[0]}" if formes else f"email:{mail}"
    if any(c in terme for c in ('"', "\n")):
        raise ValueError("Zendesk: an e-mail cannot hold a quote.")
    return Requete("GET", "/api/v2/search", params={"query": f"type:user {terme}"})


def _resultat_recherche(reponse: Any, _params: dict, _ctx: ContexteAction) -> dict:
    return trouves([(r.get("id"), r.get("name")) for r in (reponse or {}).get("results") or []])


def _creer(params: dict, ctx: ContexteAction) -> Requete:
    i = identite(params, ctx)
    utilisateur = {
        "name": nom_complet(i["prenom"], i["nom"]) or i["telephone"] or i["mail"],
        "email": i["mail"],
        "phone": i["telephone"],
    }
    return Requete("POST", "/api/v2/users", json={"user": {k: v for k, v in utilisateur.items() if v}})


def _ticket(params: dict, ctx: ContexteAction) -> Requete:
    r = {**REGLAGES_TICKET, **ctx.reglages}
    if r["priorite"] not in PRIORITES:
        raise ValueError("Zendesk: unknown priority.")
    c = ctx.modele.contact
    description = str(params["description"]).strip()
    if c.telephone:
        description = f"{description}\n\nTéléphone de l'appelant : {c.telephone}"
    ticket: dict[str, Any] = {
        "subject": str(params["sujet"]).strip()[:150],
        "comment": {"body": description},
        "priority": r["priorite"],
    }
    if params.get("identifiant"):
        ticket["requester_id"] = int(params["identifiant"])
    elif c.mail:
        ticket["requester"] = {"name": nom_complet(c.prenom, c.nom) or c.mail, "email": c.mail}
    return Requete("POST", "/api/v2/tickets", json={"ticket": ticket})


ZENDESK = declarer(
    Connecteur(
        nom="zendesk",
        libelle="Zendesk",
        integration="zendesk",
        actions=(
            action_trouver(_chercher, _resultat_recherche),
            action_creer_contact(_creer, resultat_creation("user.id")),
            Action(
                nom="create_ticket",
                description="Open a ticket with the caller's request (a breakdown, a complaint, a question).",
                parametres=(
                    Parametre("sujet", description="A short title."),
                    Parametre("description", description="What the caller said, complete."),
                    Parametre("identifiant", description="The identifier of his user, if find_contact gave one.", obligatoire=False),
                ),
                ecrit=True,
                preparer=_ticket,
                resultat=lambda reponse, _p, _c: {
                    "cree": True,
                    "identifiant": str(((reponse or {}).get("ticket") or {}).get("id") or _manque()),
                },
                reglages_par_defaut=REGLAGES_TICKET,
            ),
        ),
    )
)


def _manque() -> str:
    raise ValueError("Zendesk gave no ticket.")
