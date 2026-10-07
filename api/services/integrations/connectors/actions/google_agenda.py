"""[.mark] Google Agenda (plan connecteurs-agent D13, chantier l-agent-travaille L5): declared and
wired, not switched on. The real trial waits for the Google application (Q3).

l-agent-collegue, L4 (H2, H8): this file also declares Google Agenda's TRANSLATOR for the hub
(bottom of the file), MULTI-agenda: one person = one agenda (``lien_externe``, H7), a search
reads every agenda asked in one ``freeBusy`` call. The two actions above are unchanged; the
booking they make is noted for the hub (``au_hub``) and written after the call (H6).

- ``find_free_slots`` (reads; may be anticipated, D17): up to three free slots that respect the
  client's rules (D9): duration by reason, opening ranges, minimum notice, horizon.
- ``book_appointment`` (writes; never anticipated): the event, its title and description built
  from the common model (D16).

API: ``POST /calendar/v3/freeBusy``, ``POST /calendar/v3/calendars/{id}/events``, through the relay.
"""

from __future__ import annotations

import unicodedata
from datetime import date, datetime, time, timedelta
from typing import Any
from urllib.parse import quote
from zoneinfo import ZoneInfo

from api.services.hub.traducteurs import (
    Champ,
    ObjetTraduit,
    Operation,
    Traducteur,
    declarer_traducteur,
)
from api.services.integrations.connectors.catalogue import (
    Action,
    Connecteur,
    ContexteAction,
    Parametre,
    declarer,
)
from api.services.integrations.connectors.nango import Requete

JOURS = ("lundi", "mardi", "mercredi", "jeudi", "vendredi", "samedi", "dimanche")
MOIS = (
    "janvier",
    "février",
    "mars",
    "avril",
    "mai",
    "juin",
    "juillet",
    "août",
    "septembre",
    "octobre",
    "novembre",
    "décembre",
)

REGLAGES_CRENEAUX = {
    "agenda": "primary",
    "fuseau": "Europe/Paris",
    "duree_defaut_min": 60,
    # reason (words found in it) → minutes; set from the audit (D9)
    "duree_par_motif": {},
    # days 1 (Monday) to 7, "HH:MM"
    "plages": [
        {"jours": [1, 2, 3, 4, 5], "debut": "09:00", "fin": "12:00"},
        {"jours": [1, 2, 3, 4, 5], "debut": "14:00", "fin": "18:00"},
    ],
    "delai_minimal_h": 24,
    "horizon_jours": 14,
    "pas_min": 30,
    "nombre": 3,
}


def _sans_accents(texte: str) -> str:
    return "".join(
        c
        for c in unicodedata.normalize("NFD", (texte or "").casefold())
        if unicodedata.category(c) != "Mn"
    )


def duree(reglages: dict, motif: str | None) -> int:
    for mots, minutes in (reglages.get("duree_par_motif") or {}).items():
        if any(
            _sans_accents(m.strip()) in _sans_accents(motif or "")
            for m in str(mots).split("|")
            if m.strip()
        ):
            return int(minutes)
    return int(reglages.get("duree_defaut_min") or 60)


def libelle(moment: datetime) -> str:
    minutes = f" {moment.minute:02d}" if moment.minute else ""
    return f"{JOURS[moment.weekday()]} {moment.day} {MOIS[moment.month - 1]} à {moment.hour} h{minutes}"


def _fenetre(
    params: dict, reglages: dict, maintenant: datetime
) -> tuple[datetime, datetime]:
    fuseau = ZoneInfo(reglages["fuseau"])
    debut = maintenant.astimezone(fuseau) + timedelta(
        hours=float(reglages["delai_minimal_h"])
    )
    voulu = params.get("date")
    if voulu:
        try:
            jour = date.fromisoformat(str(voulu)[:10])
            debut = max(debut, datetime.combine(jour, time(0), fuseau))
        except ValueError:
            pass
    return debut, debut + timedelta(days=int(reglages["horizon_jours"]))


def _preparer_creneaux(
    params: dict, ctx: ContexteAction, maintenant: datetime | None = None
) -> Requete:
    r = {**REGLAGES_CRENEAUX, **ctx.reglages}
    debut, fin = _fenetre(params, r, maintenant or datetime.now(ZoneInfo(r["fuseau"])))
    return Requete(
        "POST",
        "/calendar/v3/freeBusy",
        json={
            "timeMin": debut.isoformat(),
            "timeMax": fin.isoformat(),
            "timeZone": r["fuseau"],
            "items": [{"id": r["agenda"]}],
        },
    )


def creneaux_libres(
    occupe: list[tuple[datetime, datetime]],
    params: dict,
    reglages: dict,
    maintenant: datetime,
) -> list[datetime]:
    r = {**REGLAGES_CRENEAUX, **reglages}
    fuseau = ZoneInfo(r["fuseau"])
    debut, fin = _fenetre(params, r, maintenant)
    longueur = timedelta(minutes=duree(r, params.get("motif") or params.get("_motif")))
    pas = timedelta(minutes=int(r["pas_min"]))
    sortie: list[datetime] = []
    jour = debut.date()
    while jour <= fin.date() and len(sortie) < int(r["nombre"]):
        for plage in r["plages"]:
            if jour.isoweekday() not in plage["jours"]:
                continue
            h1, m1 = map(int, plage["debut"].split(":"))
            h2, m2 = map(int, plage["fin"].split(":"))
            moment = datetime.combine(jour, time(h1, m1), fuseau)
            borne = datetime.combine(jour, time(h2, m2), fuseau)
            while moment + longueur <= borne and len(sortie) < int(r["nombre"]):
                if moment >= debut and not any(
                    moment < b and moment + longueur > a for a, b in occupe
                ):
                    sortie.append(moment)
                    moment += longueur
                else:
                    moment += pas
        jour += timedelta(days=1)
    return sorted(sortie)[: int(r["nombre"])]


def _resultat_creneaux(
    reponse: Any, params: dict, ctx: ContexteAction, maintenant: datetime | None = None
) -> dict:
    r = {**REGLAGES_CRENEAUX, **ctx.reglages}
    agenda = ((reponse or {}).get("calendars") or {}).get(r["agenda"]) or {}
    occupe = [
        (
            datetime.fromisoformat(b["start"].replace("Z", "+00:00")),
            datetime.fromisoformat(b["end"].replace("Z", "+00:00")),
        )
        for b in agenda.get("busy") or []
    ]
    params = {**params, "_motif": params.get("motif") or ctx.modele.motif}
    libres = creneaux_libres(
        occupe, params, r, maintenant or datetime.now(ZoneInfo(r["fuseau"]))
    )
    # D8: the useful result only, never the raw answer (the agenda's other events).
    return (
        {"creneaux": [{"debut": m.isoformat(), "libelle": libelle(m)} for m in libres]}
        if libres
        else {"creneaux": [], "aucun": True}
    )


REGLAGES_RENDEZ_VOUS = {
    "agenda": "primary",
    "fuseau": "Europe/Paris",
    "duree_defaut_min": 60,
    "duree_par_motif": {},
    "titre": "{motif} · {nom}",
}


def _preparer_rendez_vous(params: dict, ctx: ContexteAction) -> Requete:
    r = {**REGLAGES_RENDEZ_VOUS, **ctx.reglages}
    debut = datetime.fromisoformat(str(params["debut"]))
    if debut.tzinfo is None:
        debut = debut.replace(tzinfo=ZoneInfo(r["fuseau"]))
    modele = ctx.modele
    motif = params.get("motif") or modele.motif or "Rendez-vous"
    fin = debut + timedelta(minutes=duree(r, motif))
    nom = (
        " ".join(x for x in (modele.contact.prenom, modele.contact.nom) if x)
        or "appelant"
    )
    lignes = [
        f"Motif : {motif}",
        f"Contact : {nom}",
        *(
            [f"Téléphone : {modele.contact.telephone}"]
            if modele.contact.telephone
            else []
        ),
        *([f"Adresse : {modele.adresse.texte()}"] if modele.adresse.texte() else []),
        "Posé par l'assistant vocal.",
    ]
    corps = {
        "summary": str(r["titre"]).format(motif=motif, nom=nom),
        "description": "\n".join(lignes),
        "start": {"dateTime": debut.isoformat(), "timeZone": r["fuseau"]},
        "end": {"dateTime": fin.isoformat(), "timeZone": r["fuseau"]},
    }
    if modele.adresse.texte():
        corps["location"] = modele.adresse.texte()
    return Requete(
        "POST",
        f"/calendar/v3/calendars/{quote(r['agenda'], safe='')}/events",
        json=corps,
    )


def _resultat_rendez_vous(reponse: Any, params: dict, ctx: ContexteAction) -> dict:
    debut = datetime.fromisoformat(str(params["debut"]))
    return {
        "pose": True,
        "libelle": libelle(debut),
        "identifiant": (reponse or {}).get("id"),
    }


def _au_hub_rendez_vous(resultat: dict, params: dict, ctx: ContexteAction) -> dict | None:
    """l-agent-collegue, H6: the booking, in the hub's format, for the after-call."""
    if not (resultat or {}).get("identifiant"):
        return None
    r = {**REGLAGES_RENDEZ_VOUS, **ctx.reglages}
    debut = datetime.fromisoformat(str(params["debut"]))
    if debut.tzinfo is None:
        debut = debut.replace(tzinfo=ZoneInfo(r["fuseau"]))
    motif = params.get("motif") or ctx.modele.motif
    return {
        "systeme": "google_agenda",
        "agenda": r["agenda"],
        "id_externe": str(resultat["identifiant"]),
        "debut": debut.isoformat(),
        "fin": (debut + timedelta(minutes=duree(r, motif))).isoformat(),
        "motif": motif,
    }


GOOGLE_AGENDA = declarer(
    Connecteur(
        nom="google_agenda",
        libelle="Google Agenda",
        integration="google-calendar",
        actions=(
            Action(
                nom="find_free_slots",
                description="Find up to three free appointment slots in the business's calendar.",
                parametres=(
                    Parametre(
                        "motif",
                        description="The reason for the appointment, in the caller's words.",
                        obligatoire=False,
                    ),
                    Parametre(
                        "date",
                        description="The day the caller prefers, YYYY-MM-DD. Leave empty for the first slots.",
                        obligatoire=False,
                    ),
                ),
                ecrit=False,
                anticipable_permis=True,
                preparer=_preparer_creneaux,
                resultat=_resultat_creneaux,
                reglages_par_defaut=REGLAGES_CRENEAUX,
            ),
            Action(
                nom="book_appointment",
                description="Book the appointment the caller accepted, at one of the slots proposed.",
                parametres=(
                    Parametre(
                        "debut",
                        description="The start of the slot accepted, exactly as proposed (ISO date-time).",
                    ),
                    Parametre(
                        "motif",
                        description="The reason for the appointment.",
                        obligatoire=False,
                    ),
                ),
                ecrit=True,
                preparer=_preparer_rendez_vous,
                resultat=_resultat_rendez_vous,
                reglages_par_defaut=REGLAGES_RENDEZ_VOUS,
                au_hub=_au_hub_rendez_vous,
            ),
        ),
    )
)


# --------------------------------------------------------------------------- #
# The translator of the hub (l-agent-collegue, L4, H2, H8)
# --------------------------------------------------------------------------- #


def _instant(texte: str) -> datetime:
    return datetime.fromisoformat(str(texte).replace("Z", "+00:00"))


def _chemin_evenements(agenda: str) -> str:
    if not agenda:
        raise ValueError("An appointment lives in an agenda: none given.")
    return f"/calendar/v3/calendars/{quote(str(agenda), safe='')}/events"


def _chercher(arguments: dict, _o: ObjetTraduit) -> Requete:
    return Requete(
        "POST",
        "/calendar/v3/freeBusy",
        json={
            "timeMin": arguments["debut"],
            "timeMax": arguments["fin"],
            "timeZone": "UTC",
            "items": [{"id": a} for a in arguments.get("agendas") or []],
        },
    )


def _lire_occupations(reponse: Any, arguments: dict, _o: ObjetTraduit) -> dict:
    """Agenda -> busy intervals. An agenda with ``errors`` (unknown, not shared) is left OUT:
    unknown is never free."""
    calendriers = (reponse or {}).get("calendars") or {}
    sortie = {}
    for agenda in arguments.get("agendas") or []:
        entree = calendriers.get(agenda)
        if not isinstance(entree, dict) or entree.get("errors"):
            continue
        sortie[agenda] = [
            (_instant(b["start"]), _instant(b["end"]))
            for b in entree.get("busy") or []
            if b.get("start") and b.get("end")
        ]
    return sortie


CORRESPONDANCE_EVENEMENT = (
    Champ("id_externe", "id"),
    Champ("titre", "summary"),
    Champ("description", "description"),
    Champ("lieu", "location"),
    Champ("debut", "start.dateTime"),
    Champ("fin", "end.dateTime"),
    Champ("fuseau", "start.timeZone"),
    Champ("fuseau", "end.timeZone"),
)


def _corps(arguments: dict, o: ObjetTraduit) -> dict:
    return o.vers_logiciel({k: v for k, v in arguments.items() if k not in ("agenda", "id_externe")})


def _creer(arguments: dict, o: ObjetTraduit) -> Requete:
    return Requete("POST", _chemin_evenements(arguments.get("agenda")), json=_corps(arguments, o))


def _un_evenement(arguments: dict) -> str:
    if not arguments.get("id_externe"):
        raise ValueError("Which appointment: no identifier given.")
    return f"{_chemin_evenements(arguments.get('agenda'))}/{quote(str(arguments['id_externe']), safe='')}"


def _lire(arguments: dict, _o: ObjetTraduit) -> Requete:
    return Requete("GET", _un_evenement(arguments))


def _modifier(arguments: dict, o: ObjetTraduit) -> Requete:
    return Requete("PATCH", _un_evenement(arguments), json=_corps(arguments, o))


def _evenement(reponse: Any, arguments: dict, o: ObjetTraduit) -> dict:
    return {**o.depuis_logiciel(reponse or {}), "agenda": arguments.get("agenda")}


def _chercher_evenements(arguments: dict, _o: ObjetTraduit) -> Requete:
    """l-agent-collegue, R-6: the appointments of one agenda with their place. Only the times, the
    place and the state are asked (``fields``): never a title, a description or a guest."""
    return Requete(
        "GET",
        _chemin_evenements(arguments.get("agenda")),
        params={
            "timeMin": arguments["debut"],
            "timeMax": arguments["fin"],
            "singleEvents": "true",
            "orderBy": "startTime",
            "maxResults": 250,
            "fields": "items(id,status,transparency,start,end,location)",
        },
    )


def _lire_evenements(reponse: Any, arguments: dict, o: ObjetTraduit) -> list[dict]:
    """Cancelled, « free » (transparent) and all-day events (no ``dateTime``) are left out."""
    sortie = []
    for e in (reponse or {}).get("items") or []:
        if not isinstance(e, dict) or e.get("status") == "cancelled" or e.get("transparency") == "transparent":
            continue
        valeurs = {**o.depuis_logiciel(e), "agenda": arguments.get("agenda")}
        if valeurs.get("debut") and valeurs.get("fin"):
            sortie.append(valeurs)
    return sortie


TRADUCTEUR = declarer_traducteur(
    Traducteur(
        systeme="google_agenda",
        libelle="Google Agenda",
        integration="google-calendar",
        domaine="agenda",
        reference_agenda={
            "en": "Calendar ID (often the person's Google address)",
            "fr": "Identifiant de l'agenda (souvent l'adresse Google de la personne)",
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
