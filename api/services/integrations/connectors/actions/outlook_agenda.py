"""[.mark] Microsoft Outlook (agenda): the hub's translator (chantier l-agent-collegue, L4, H8, Q2).

Declared and wired, OFF: nothing uses it until an organization chooses it in « Integrations »
(X2). No Microsoft application exists yet (Q7): it is proven by the stand-in of the relay and
the API's documented answers; the trial on a real agenda comes with the application.

Microsoft Graph, through Nango's relay (integration ``outlook``, base ``graph.microsoft.com``):

- search: ``POST /v1.0/me/calendar/getSchedule`` -- the busy items of several mailboxes at once
  (one person's agenda = her mailbox address, H7). A schedule that comes back with an ``error``
  (unknown, not shared) is left OUT: unknown is never free. Busy = ``busy``, ``tentative``,
  ``oof``, ``workingElsewhere``; ``free`` is not.
- create, read, update: ``/v1.0/users/{mailbox}/calendar/events[/{id}]``.
- search of the events of one agenda (R-6, the place of the previous appointment):
  ``GET /v1.0/users/{mailbox}/calendarView`` with ``$select`` of the times, the place and the
  state only (never a subject, a body or an attendee).

Times: Graph takes a date-time WITHOUT offset plus a time zone; the translator always sends
UTC (``timeZone: "UTC"``) and reads the answer's own time zone (UTC unless asked otherwise),
so no Windows time-zone name is ever needed.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any
from urllib.parse import quote

from api.services.hub.traducteurs import (
    Champ,
    ObjetTraduit,
    Operation,
    Traducteur,
    declarer_traducteur,
)
from api.services.integrations.connectors.nango import Requete

OCCUPE = ("busy", "tentative", "oof", "workingelsewhere")


def _en_utc(texte: str) -> str:
    """ISO with offset -> Graph's UTC date-time without offset."""
    moment = datetime.fromisoformat(str(texte).replace("Z", "+00:00"))
    if moment.tzinfo is None:
        raise ValueError("A date-time of the hub always carries its offset.")
    return moment.astimezone(UTC).replace(tzinfo=None).isoformat(timespec="seconds")


def _depuis_graph(valeur: Any, fuseau: str | None = "UTC") -> datetime:
    """Graph's ``{dateTime, timeZone}`` (or its date-time alone, UTC) -> an aware instant."""
    if isinstance(valeur, dict):
        fuseau = valeur.get("timeZone") or "UTC"
        valeur = valeur.get("dateTime")
    texte = str(valeur)
    # Graph writes up to seven decimals: Python reads six.
    if "." in texte:
        entier, decimales = texte.split(".", 1)
        texte = f"{entier}.{decimales[:6]}"
    moment = datetime.fromisoformat(texte.replace("Z", "+00:00"))
    if moment.tzinfo is None:
        if (fuseau or "UTC").upper() not in ("UTC", "COORDINATED UNIVERSAL TIME"):
            raise ValueError(f"Unexpected time zone from Graph: {fuseau}")
        moment = moment.replace(tzinfo=UTC)
    return moment


def _boite(agenda: str | None) -> str:
    if not agenda:
        raise ValueError("An appointment lives in an agenda (a mailbox): none given.")
    return quote(str(agenda), safe="@.")


def _chercher(arguments: dict, _o: ObjetTraduit) -> Requete:
    return Requete(
        "POST",
        "/v1.0/me/calendar/getSchedule",
        json={
            "schedules": list(arguments.get("agendas") or []),
            "startTime": {"dateTime": _en_utc(arguments["debut"]), "timeZone": "UTC"},
            "endTime": {"dateTime": _en_utc(arguments["fin"]), "timeZone": "UTC"},
            "availabilityViewInterval": 15,
        },
    )


def _lire_occupations(reponse: Any, arguments: dict, _o: ObjetTraduit) -> dict:
    demandes = {str(a).casefold(): a for a in arguments.get("agendas") or []}
    sortie: dict = {}
    for horaire in (reponse or {}).get("value") or []:
        agenda = demandes.get(str(horaire.get("scheduleId") or "").casefold())
        if agenda is None or horaire.get("error"):
            continue
        sortie[agenda] = [
            (_depuis_graph(e.get("start")), _depuis_graph(e.get("end")))
            for e in horaire.get("scheduleItems") or []
            if str(e.get("status") or "").casefold() in OCCUPE
            and e.get("start")
            and e.get("end")
        ]
    return sortie


CORRESPONDANCE_EVENEMENT = (
    Champ("id_externe", "id"),
    Champ("titre", "subject"),
    Champ("description", "body.content"),
    Champ("description", "body.contentType", vers=lambda _v: "text"),
    Champ("lieu", "location.displayName"),
    Champ(
        "debut",
        "start",
        vers=lambda v: {"dateTime": _en_utc(v), "timeZone": "UTC"},
        depuis=lambda v: _depuis_graph(v).isoformat(),
    ),
    Champ(
        "fin",
        "end",
        vers=lambda v: {"dateTime": _en_utc(v), "timeZone": "UTC"},
        depuis=lambda v: _depuis_graph(v).isoformat(),
    ),
)


def _corps(arguments: dict, o: ObjetTraduit) -> dict:
    return o.vers_logiciel(
        {
            k: v
            for k, v in arguments.items()
            if k not in ("agenda", "id_externe", "fuseau")
        }
    )


def _creer(arguments: dict, o: ObjetTraduit) -> Requete:
    return Requete(
        "POST",
        f"/v1.0/users/{_boite(arguments.get('agenda'))}/calendar/events",
        json=_corps(arguments, o),
    )


def _un_evenement(arguments: dict) -> str:
    if not arguments.get("id_externe"):
        raise ValueError("Which appointment: no identifier given.")
    return (
        f"/v1.0/users/{_boite(arguments.get('agenda'))}/calendar/events/"
        f"{quote(str(arguments['id_externe']), safe='')}"
    )


def _lire(arguments: dict, _o: ObjetTraduit) -> Requete:
    return Requete("GET", _un_evenement(arguments))


def _modifier(arguments: dict, o: ObjetTraduit) -> Requete:
    return Requete("PATCH", _un_evenement(arguments), json=_corps(arguments, o))


def _evenement(reponse: Any, arguments: dict, o: ObjetTraduit) -> dict:
    return {**o.depuis_logiciel(reponse or {}), "agenda": arguments.get("agenda")}


def _chercher_evenements(arguments: dict, _o: ObjetTraduit) -> Requete:
    def borne(texte: str) -> str:
        return datetime.fromisoformat(str(texte).replace("Z", "+00:00")).astimezone(UTC).isoformat(timespec="seconds")

    return Requete(
        "GET",
        f"/v1.0/users/{_boite(arguments.get('agenda'))}/calendarView",
        params={
            "startDateTime": borne(arguments["debut"]),
            "endDateTime": borne(arguments["fin"]),
            "$select": "id,start,end,location,isCancelled,isAllDay,showAs",
            "$orderby": "start/dateTime",
            "$top": 250,
        },
    )


def _lire_evenements(reponse: Any, arguments: dict, o: ObjetTraduit) -> list[dict]:
    """Cancelled, all-day and « free » events are left out. Graph answers in UTC (no ``Prefer``
    header is sent), which ``_depuis_graph`` reads."""
    sortie = []
    for e in (reponse or {}).get("value") or []:
        if (
            not isinstance(e, dict)
            or e.get("isCancelled")
            or e.get("isAllDay")
            or str(e.get("showAs") or "busy").casefold() == "free"
            or not e.get("start")
            or not e.get("end")
        ):
            continue
        sortie.append({**o.depuis_logiciel(e), "agenda": arguments.get("agenda")})
    return sortie


TRADUCTEUR = declarer_traducteur(
    Traducteur(
        systeme="outlook_agenda",
        libelle="Microsoft Outlook (agenda)",
        integration="outlook",
        domaine="agenda",
        reference_agenda={
            "en": "The person's mailbox address (Microsoft 365)",
            "fr": "Adresse de la boîte aux lettres de la personne (Microsoft 365)",
        },
        objets=(
            ObjetTraduit(
                "disponibilites",
                correspondance=(),
                operations={"chercher": Operation(_chercher, _lire_occupations)},
            ),
            ObjetTraduit(
                "rendez_vous",
                correspondance=CORRESPONDANCE_EVENEMENT,
                operations={
                    "creer": Operation(_creer, _evenement),
                    "chercher": Operation(_chercher_evenements, _lire_evenements),
                    "lire": Operation(_lire, _evenement),
                    "modifier": Operation(_modifier, _evenement),
                },
            ),
        ),
    )
)
