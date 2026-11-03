"""[.mark] Acuity Scheduling (booking software): actions (U3 sexies, point 8, F2).

State « À essayer »: written from Acuity's public documentation (read on 03/11/2026:
``GET /availability/times`` and ``POST /appointments``,
https://developers.acuityscheduling.com/reference), proven on answers recorded in a file. Through
Nango's relay (integration ``acuity-scheduling``, base ``https://acuityscheduling.com/api/v1``).

- ``find_free_slots`` (reads): ``GET /availability/times`` for ONE day (Acuity answers by day). With
  a day asked, that day; otherwise ``GET /availability/dates`` for the month, then the times of the
  first day that has some (the second request is the action's ``suite``).
- ``book_appointment`` (writes): ``POST /appointments?admin=true`` (booking as the owner: the e-mail
  is then optional and a note is allowed). Appointment type (and calendar) are the client's settings.
"""

from __future__ import annotations

from datetime import datetime, timedelta
from typing import Any
from zoneinfo import ZoneInfo

from api.services.integrations.connectors import nango
from api.services.integrations.connectors.actions.google_agenda import libelle
from api.services.integrations.connectors.catalogue import (
    Action,
    Connecteur,
    ContexteAction,
    Parametre,
    declarer,
)
from api.services.integrations.connectors.nango import Requete

INTEGRATION = "acuity-scheduling"
REGLAGES_CRENEAUX = {
    "type_rendez_vous": "",  # appointmentTypeID
    "agenda": "",  # calendarID; empty = any calendar offering the type
    "fuseau": "Europe/Paris",
    "delai_minimal_h": 24,
    "nombre": 3,
}
REGLAGES_RENDEZ_VOUS = {"type_rendez_vous": "", "agenda": "", "fuseau": "Europe/Paris", "duree_defaut_min": 30, "duree_par_motif": {}}


def _type(reglages: dict) -> int:
    try:
        return int(reglages.get("type_rendez_vous"))
    except (TypeError, ValueError):
        raise ValueError("Acuity: the appointment type is not set.") from None


def _requete_jours(r: dict, jour: datetime) -> Requete:
    params: dict[str, Any] = {"date": jour.date().isoformat(), "appointmentTypeID": _type(r), "timezone": r["fuseau"]}
    if r.get("agenda"):
        params["calendarID"] = int(r["agenda"])
    return Requete("GET", "/availability/times", params=params)


def _premier_jour(params: dict, r: dict, maintenant: datetime | None) -> datetime:
    debut = (maintenant or datetime.now(ZoneInfo(r["fuseau"]))).astimezone(ZoneInfo(r["fuseau"])) + timedelta(
        hours=float(r["delai_minimal_h"])
    )
    voulu = params.get("date")
    if voulu:
        try:
            debut = max(debut, datetime.fromisoformat(str(voulu)[:10]).replace(tzinfo=ZoneInfo(r["fuseau"])))
        except ValueError:
            pass
    return debut


def _preparer_creneaux(params: dict, ctx: ContexteAction, maintenant: datetime | None = None) -> Requete:
    r = {**REGLAGES_CRENEAUX, **ctx.reglages}
    debut = _premier_jour(params, r, maintenant)
    if params.get("date"):
        return _requete_jours(r, debut)
    # No day asked: the days of the month that have room, then the times of the first one.
    parametres: dict[str, Any] = {"month": debut.strftime("%Y-%m"), "appointmentTypeID": _type(r), "timezone": r["fuseau"]}
    if r.get("agenda"):
        parametres["calendarID"] = int(r["agenda"])
    return Requete("GET", "/availability/dates", params=parametres)


async def _jours_puis_heures(reponse: Any, params: dict, ctx: ContexteAction, maintenant: datetime | None = None) -> Any:
    """``/availability/dates`` answers ``[{"date": "2030-01-08"}, ...]``: the times of the first
    day from the minimal notice on. A list of times (a day asked) goes through unchanged."""
    if not (isinstance(reponse, list) and reponse and isinstance(reponse[0], dict) and "date" in reponse[0]):
        return reponse
    r = {**REGLAGES_CRENEAUX, **ctx.reglages}
    premier = _premier_jour(params, r, maintenant).date().isoformat()
    for jour in sorted(str(d["date"]) for d in reponse if d.get("date")):
        if jour >= premier:
            return await nango.relayer(
                ctx.organization_id,  # type: ignore[arg-type]
                INTEGRATION,
                _requete_jours(r, datetime.fromisoformat(jour)),
                delai=5.0,
            )
    return []


def _resultat_creneaux(reponse: Any, _params: dict, ctx: ContexteAction, maintenant: datetime | None = None) -> dict:
    r = {**REGLAGES_CRENEAUX, **ctx.reglages}
    fuseau = ZoneInfo(r["fuseau"])
    debut = (maintenant or datetime.now(fuseau)) + timedelta(hours=float(r["delai_minimal_h"]))
    libres = sorted(
        m
        for m in (
            datetime.fromisoformat(_iso(c["time"])).astimezone(fuseau)
            for c in reponse or []
            if isinstance(c, dict) and c.get("time")
        )
        if m >= debut
    )[: int(r["nombre"])]
    return (
        {"creneaux": [{"debut": m.isoformat(), "libelle": libelle(m)} for m in libres]}
        if libres
        else {"creneaux": [], "aucun": True}
    )


def _iso(texte: str) -> str:
    """Acuity writes the offset without a colon (« -0800 »): Python wants « -08:00 »."""
    t = str(texte)
    if len(t) > 5 and t[-5] in "+-" and t[-3] != ":":
        t = f"{t[:-2]}:{t[-2:]}"
    return t.replace("Z", "+00:00")


def _preparer_rendez_vous(params: dict, ctx: ContexteAction) -> Requete:
    r = {**REGLAGES_RENDEZ_VOUS, **ctx.reglages}
    debut = datetime.fromisoformat(str(params["debut"]))
    if debut.tzinfo is None:
        debut = debut.replace(tzinfo=ZoneInfo(r["fuseau"]))
    c = ctx.modele.contact
    motif = params.get("motif") or ctx.modele.motif
    corps: dict[str, Any] = {
        "datetime": debut.astimezone(ZoneInfo(r["fuseau"])).isoformat(timespec="seconds"),
        "appointmentTypeID": _type(r),
        "firstName": params.get("prenom") or c.prenom or "Appelant",
        "lastName": params.get("nom") or c.nom or "-",
        "timezone": r["fuseau"],
        "notes": "\n".join(x for x in (f"Motif : {motif}" if motif else None, "Posé par l'assistant vocal.") if x),
    }
    if params.get("mail") or c.mail:
        corps["email"] = params.get("mail") or c.mail
    if c.telephone:
        corps["phone"] = c.telephone
    if r.get("agenda"):
        corps["calendarID"] = int(r["agenda"])
    return Requete("POST", "/appointments", params={"admin": "true"}, json=corps)


def _resultat_rendez_vous(reponse: Any, params: dict, _ctx: ContexteAction) -> dict:
    identifiant = (reponse or {}).get("id")
    if identifiant is None:
        raise ValueError("Acuity gave no appointment for the booking.")
    return {"pose": True, "libelle": libelle(datetime.fromisoformat(str(params["debut"]))), "identifiant": str(identifiant)}


ACUITY = declarer(
    Connecteur(
        nom="acuity",
        libelle="Acuity Scheduling",
        integration=INTEGRATION,
        actions=(
            Action(
                nom="find_free_slots",
                description="Find up to three free appointment slots in the business's Acuity.",
                parametres=(
                    Parametre("date", description="The day the caller prefers, YYYY-MM-DD. Leave empty for the first slots.", obligatoire=False),
                ),
                ecrit=False,
                anticipable_permis=True,
                preparer=_preparer_creneaux,
                resultat=_resultat_creneaux,
                suite=_jours_puis_heures,
                reglages_par_defaut=REGLAGES_CRENEAUX,
            ),
            Action(
                nom="book_appointment",
                description="Book the appointment the caller accepted, at one of the slots proposed.",
                parametres=(
                    Parametre("debut", description="The start of the slot accepted, exactly as proposed (ISO date-time)."),
                    Parametre("motif", description="The reason for the appointment.", obligatoire=False),
                    Parametre("prenom", description="His first name.", obligatoire=False),
                    Parametre("nom", description="His last name.", obligatoire=False),
                    Parametre("mail", description="His e-mail address, as he says it.", obligatoire=False),
                ),
                ecrit=True,
                preparer=_preparer_rendez_vous,
                resultat=_resultat_rendez_vous,
                reglages_par_defaut=REGLAGES_RENDEZ_VOUS,
            ),
        ),
    )
)
