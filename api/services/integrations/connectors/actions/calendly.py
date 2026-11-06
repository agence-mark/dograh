"""[.mark] Calendly (booking software): actions (U3 sexies, point 8, F2).

State « À essayer »: written from Calendly's public documentation (read on 03/11/2026:
« List Event Type Available Times » and « Create Event Invitee »,
https://developer.calendly.com/api-docs), proven on answers recorded in a file. Through Nango's
relay (integration ``calendly``, base ``https://api.calendly.com``).

- ``find_free_slots`` (reads): ``GET /event_type_available_times`` on the event type of the
  settings, from the minimal notice to the horizon (31 days at most, a Calendly limit).
- ``book_appointment`` (writes): ``POST /invitees`` (Scheduling API; **paid Calendly plans only**,
  a free plan answers 403 = the fallback sentence). Calendly needs the invitee's e-mail: the model
  asks for it. The time travels in UTC, as Calendly requires.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any
from zoneinfo import ZoneInfo

from api.services.integrations.connectors.actions.google_agenda import libelle
from api.services.integrations.connectors.catalogue import (
    Action,
    Connecteur,
    ContexteAction,
    Parametre,
    declarer,
)
from api.services.integrations.connectors.nango import Requete

REGLAGES_CRENEAUX = {
    "type_evenement": "",  # URI of the event type: https://api.calendly.com/event_types/<uuid>
    "fuseau": "Europe/Paris",
    "delai_minimal_h": 24,
    "horizon_jours": 14,
    "nombre": 3,
}
REGLAGES_RENDEZ_VOUS = {"type_evenement": "", "fuseau": "Europe/Paris"}


def _type(reglages: dict) -> str:
    uri = str(reglages.get("type_evenement") or "").strip()
    if not uri.startswith("https://api.calendly.com/event_types/"):
        raise ValueError("Calendly: the event type (its API address) is not set.")
    return uri


def _z(moment: datetime) -> str:
    return moment.astimezone(UTC).isoformat(timespec="seconds").replace("+00:00", "Z")


def _preparer_creneaux(params: dict, ctx: ContexteAction, maintenant: datetime | None = None) -> Requete:
    r = {**REGLAGES_CRENEAUX, **ctx.reglages}
    debut = (maintenant or datetime.now(UTC)) + timedelta(hours=float(r["delai_minimal_h"]))
    voulu = params.get("date")
    if voulu:
        try:
            debut = max(debut, datetime.fromisoformat(str(voulu)[:10]).replace(tzinfo=ZoneInfo(r["fuseau"])))
        except ValueError:
            pass
    fin = debut + timedelta(days=min(int(r["horizon_jours"]), 31))
    return Requete(
        "GET",
        "/event_type_available_times",
        params={"event_type": _type(r), "start_time": _z(debut), "end_time": _z(fin)},
    )


def _resultat_creneaux(reponse: Any, _params: dict, ctx: ContexteAction) -> dict:
    r = {**REGLAGES_CRENEAUX, **ctx.reglages}
    fuseau = ZoneInfo(r["fuseau"])
    libres = sorted(
        datetime.fromisoformat(c["start_time"].replace("Z", "+00:00")).astimezone(fuseau)
        for c in (reponse or {}).get("collection") or []
        if c.get("status") == "available" and c.get("start_time")
    )[: int(r["nombre"])]
    return (
        {"creneaux": [{"debut": m.isoformat(), "libelle": libelle(m)} for m in libres]}
        if libres
        else {"creneaux": [], "aucun": True}
    )


def _preparer_rendez_vous(params: dict, ctx: ContexteAction) -> Requete:
    r = {**REGLAGES_RENDEZ_VOUS, **ctx.reglages}
    debut = datetime.fromisoformat(str(params["debut"]))
    if debut.tzinfo is None:
        debut = debut.replace(tzinfo=ZoneInfo(r["fuseau"]))
    c = ctx.modele.contact
    prenom, nom = params.get("prenom") or c.prenom, params.get("nom") or c.nom
    invite: dict[str, Any] = {
        "email": params["mail"],
        "timezone": r["fuseau"],
        "name": " ".join(x for x in (prenom, nom) if x) or "Appelant",
    }
    if prenom:
        invite["first_name"] = prenom
    if nom:
        invite["last_name"] = nom
    if c.telephone:
        invite["text_reminder_number"] = c.telephone
    return Requete(
        "POST",
        "/invitees",
        json={"event_type": _type(r), "start_time": _z(debut), "invitee": invite},
    )


def _resultat_rendez_vous(reponse: Any, params: dict, _ctx: ContexteAction) -> dict:
    uri = ((reponse or {}).get("resource") or {}).get("uri")
    if not uri:
        raise ValueError("Calendly gave no invitee for the booking.")
    return {"pose": True, "libelle": libelle(datetime.fromisoformat(str(params["debut"]))), "identifiant": uri}


CALENDLY = declarer(
    Connecteur(
        nom="calendly",
        libelle="Calendly",
        integration="calendly",
        actions=(
            Action(
                nom="find_free_slots",
                description="Find up to three free appointment slots offered by the business's Calendly.",
                parametres=(
                    Parametre("date", description="The day the caller prefers, YYYY-MM-DD. Leave empty for the first slots.", obligatoire=False),
                ),
                ecrit=False,
                anticipable_permis=True,
                preparer=_preparer_creneaux,
                resultat=_resultat_creneaux,
                reglages_par_defaut=REGLAGES_CRENEAUX,
            ),
            Action(
                nom="book_appointment",
                description="Book the appointment the caller accepted, at one of the slots proposed. Ask for his e-mail address first: Calendly sends him the confirmation.",
                parametres=(
                    Parametre("debut", description="The start of the slot accepted, exactly as proposed (ISO date-time)."),
                    Parametre("mail", description="His e-mail address, as he says it."),
                    Parametre("prenom", description="His first name.", obligatoire=False),
                    Parametre("nom", description="His last name.", obligatoire=False),
                ),
                ecrit=True,
                preparer=_preparer_rendez_vous,
                resultat=_resultat_rendez_vous,
                reglages_par_defaut=REGLAGES_RENDEZ_VOUS,
            ),
        ),
    )
)
