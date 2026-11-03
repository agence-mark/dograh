"""[.mark] Setmore (booking software): actions (U3 sexies, point 8, F2).

State « À essayer ». Setmore API v1 (``/bookingapi``, https://setmore.docs.apiary.io), through
Nango's relay (integration ``setmore``). ⚠ Setmore's API is a limited beta (access on request,
Nango's page says so) and its reference could not be read in full at writing time: the shapes
below are the documented ones from memory of the apiary (slots, customer, appointment) and MUST be
checked at the first trial, with the beta access. The recorded answers prove the reading and the
bodies, not the software.

- ``find_free_slots`` (reads): ``POST /bookingapi/slots`` for ONE day (``selected_date`` in
  ``dd/MM/yyyy``), the staff member and the service of the settings. The slots come as « 09.30 ».
- ``book_appointment`` (writes): the customer (``POST /bookingapi/customer/create``), then the
  appointment (``POST /bookingapi/appointment/create``, the action's ``suite``). Times are the
  account's local time written with a literal « Z », as Setmore does.
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

REGLAGES_CRENEAUX = {
    "personnel": "",  # staff_key
    "service": "",  # service_key
    "fuseau": "Europe/Paris",
    "delai_minimal_h": 24,
    "nombre": 3,
}
REGLAGES_RENDEZ_VOUS = {"personnel": "", "service": "", "fuseau": "Europe/Paris", "duree_min": 30}


def _cles(r: dict) -> tuple[str, str]:
    if not (r.get("personnel") and r.get("service")):
        raise ValueError("Setmore: the staff member and the service are not set.")
    return str(r["personnel"]), str(r["service"])


def _jour(params: dict, r: dict, maintenant: datetime | None) -> datetime:
    fuseau = ZoneInfo(r["fuseau"])
    debut = (maintenant or datetime.now(fuseau)).astimezone(fuseau) + timedelta(hours=float(r["delai_minimal_h"]))
    if params.get("date"):
        try:
            debut = max(debut, datetime.fromisoformat(str(params["date"])[:10]).replace(tzinfo=fuseau))
        except ValueError:
            pass
    return debut


def _preparer_creneaux(params: dict, ctx: ContexteAction, maintenant: datetime | None = None) -> Requete:
    r = {**REGLAGES_CRENEAUX, **ctx.reglages}
    personnel, service = _cles(r)
    return Requete(
        "POST",
        "/bookingapi/slots",
        json={
            "staff_key": personnel,
            "service_key": service,
            "selected_date": _jour(params, r, maintenant).strftime("%d/%m/%Y"),
        },
    )


def _resultat_creneaux(reponse: Any, params: dict, ctx: ContexteAction, maintenant: datetime | None = None) -> dict:
    r = {**REGLAGES_CRENEAUX, **ctx.reglages}
    fuseau = ZoneInfo(r["fuseau"])
    jour = _jour(params, r, maintenant)
    libres = []
    for texte in ((reponse or {}).get("data") or {}).get("slots") or []:
        try:
            heures, minutes = str(texte).replace(":", ".").split(".")[:2]
            moment = jour.replace(hour=int(heures), minute=int(minutes), second=0, microsecond=0, tzinfo=fuseau)
        except ValueError:
            continue
        # Nothing before the minimal notice (``jour`` is the notice, or midnight of the day asked).
        if moment >= jour:
            libres.append(moment)
    libres = sorted(set(libres))[: int(r["nombre"])]
    return (
        {"creneaux": [{"debut": m.isoformat(), "libelle": libelle(m)} for m in libres]}
        if libres
        else {"creneaux": [], "aucun": True}
    )


def _preparer_rendez_vous(params: dict, ctx: ContexteAction) -> Requete:
    c = ctx.modele.contact
    corps = {
        "first_name": params.get("prenom") or c.prenom or "Appelant",
        "last_name": params.get("nom") or c.nom or "-",
        "email_id": params.get("mail") or c.mail,
        "cell_phone": c.telephone,
    }
    return Requete("POST", "/bookingapi/customer/create", json={k: v for k, v in corps.items() if v})


def _local(moment: datetime) -> str:
    return moment.strftime("%Y-%m-%dT%H:%MZ")


async def _poser(reponse: Any, params: dict, ctx: ContexteAction) -> Any:
    """The customer exists: the appointment itself (same connection, same deadline)."""
    r = {**REGLAGES_RENDEZ_VOUS, **ctx.reglages}
    personnel, service = _cles(r)
    client = (((reponse or {}).get("data") or {}).get("customer") or {}).get("key")
    if not client:
        raise ValueError("Setmore gave no customer for the booking.")
    fuseau = ZoneInfo(r["fuseau"])
    debut = datetime.fromisoformat(str(params["debut"]))
    debut = (debut if debut.tzinfo else debut.replace(tzinfo=fuseau)).astimezone(fuseau)
    motif = params.get("motif") or ctx.modele.motif
    return await nango.relayer(
        ctx.organization_id,  # type: ignore[arg-type]
        "setmore",
        Requete(
            "POST",
            "/bookingapi/appointment/create",
            json={
                "staff_key": personnel,
                "service_key": service,
                "customer_key": client,
                "start_time": _local(debut),
                "end_time": _local(debut + timedelta(minutes=int(r["duree_min"]))),
                "comment": "\n".join(x for x in (f"Motif : {motif}" if motif else None, "Posé par l'assistant vocal.") if x),
            },
        ),
        delai=5.0,
    )


def _resultat_rendez_vous(reponse: Any, params: dict, _ctx: ContexteAction) -> dict:
    cle = ((((reponse or {}).get("data") or {}).get("appointment")) or {}).get("key")
    if not cle:
        raise ValueError("Setmore gave no appointment for the booking.")
    return {"pose": True, "libelle": libelle(datetime.fromisoformat(str(params["debut"]))), "identifiant": str(cle)}


SETMORE = declarer(
    Connecteur(
        nom="setmore",
        libelle="Setmore",
        integration="setmore",
        actions=(
            Action(
                nom="find_free_slots",
                description="Find up to three free appointment slots in the business's Setmore, on one day.",
                parametres=(
                    Parametre("date", description="The day the caller prefers, YYYY-MM-DD. Leave empty for the first possible day.", obligatoire=False),
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
                    Parametre("debut", description="The start of the slot accepted, exactly as proposed (ISO date-time)."),
                    Parametre("motif", description="The reason for the appointment.", obligatoire=False),
                    Parametre("prenom", description="His first name.", obligatoire=False),
                    Parametre("nom", description="His last name.", obligatoire=False),
                    Parametre("mail", description="His e-mail address, as he says it.", obligatoire=False),
                ),
                ecrit=True,
                preparer=_preparer_rendez_vous,
                resultat=_resultat_rendez_vous,
                suite=_poser,
                reglages_par_defaut=REGLAGES_RENDEZ_VOUS,
            ),
        ),
    )
)
