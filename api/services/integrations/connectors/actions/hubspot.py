"""[.mark] HubSpot (CRM): actions and translator « dossier » (U3 sexies, point 8, F2).

Declared and wired, state « À essayer »: proven on answers recorded in a file, written from
HubSpot's public documentation (CRM API v3, https://developers.hubspot.com/docs/api/crm/contacts);
the trial on a test account comes with Evan (D3). Through Nango's relay (integration ``hubspot``).

- ``find_contact``: ``POST /crm/v3/objects/contacts/search``, one filter group per typing of the
  number (``phone`` and ``mobilephone``, international and national form: HubSpot compares the
  text as stored), or the e-mail.
- ``create_contact``: ``POST /crm/v3/objects/contacts``; the owner is the client's setting.
- ``add_call_note``: ``POST /crm/v3/objects/notes`` associated to the contact (type 202).
- ``create_deal``: ``POST /crm/v3/objects/deals`` in the pipeline and stage of the settings,
  associated to the contact (type 3).
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any
from urllib.parse import quote

from api.services.integrations.connectors.actions._commun import (
    action_affaire,
    action_creer_contact,
    action_note,
    action_trouver,
    criteres,
    declarer_dossier,
    formes_du_numero,
    identite,
    nom_complet,
    resultat_creation,
    resultat_note,
    texte_de_la_note,
    titre_affaire,
    trouves,
)
from api.services.integrations.connectors.catalogue import (
    Connecteur,
    ContexteAction,
    declarer,
)
from api.services.integrations.connectors.nango import Requete

PROPRIETES = ["firstname", "lastname", "email", "phone", "mobilephone", "zip", "city"]
REGLAGES_CONTACT = {"proprietaire": ""}  # HubSpot owner id; empty = none
REGLAGES_AFFAIRE = {"proprietaire": "", "pipeline": "default", "etape": "appointmentscheduled"}


def _filtres(formes: list[str], mail: str | None) -> list[dict]:
    groupes = [
        {"filters": [{"propertyName": champ, "operator": "EQ", "value": forme}]}
        for forme in formes
        for champ in ("phone", "mobilephone")
    ]
    if mail:
        groupes.append({"filters": [{"propertyName": "email", "operator": "EQ", "value": mail}]})
    return groupes[:5]  # HubSpot takes five filter groups at most


def _chercher(params: dict, ctx: ContexteAction) -> Requete:
    formes, mail = criteres(params, ctx)
    return Requete(
        "POST",
        "/crm/v3/objects/contacts/search",
        json={"filterGroups": _filtres(formes, mail), "properties": PROPRIETES, "limit": 3},
    )


def _nom(fiche: dict) -> str:
    p = fiche.get("properties") or {}
    return nom_complet(p.get("firstname"), p.get("lastname"))


def _resultat_recherche(reponse: Any, _params: dict, _ctx: ContexteAction) -> dict:
    return trouves([(r.get("id"), _nom(r)) for r in (reponse or {}).get("results") or []])


def _creer(params: dict, ctx: ContexteAction) -> Requete:
    i = identite(params, ctx)
    r = {**REGLAGES_CONTACT, **ctx.reglages}
    proprietes = {"firstname": i["prenom"], "lastname": i["nom"], "email": i["mail"], "phone": i["telephone"]}
    if r.get("proprietaire"):
        proprietes["hubspot_owner_id"] = str(r["proprietaire"])
    return Requete(
        "POST",
        "/crm/v3/objects/contacts",
        json={"properties": {k: v for k, v in proprietes.items() if v}},
    )


def _association(identifiant: str, type_id: int) -> dict:
    return {
        "to": {"id": str(identifiant)},
        "types": [{"associationCategory": "HUBSPOT_DEFINED", "associationTypeId": type_id}],
    }


def _note(params: dict, ctx: ContexteAction) -> Requete:
    r = {**REGLAGES_CONTACT, **ctx.reglages}
    proprietes = {
        "hs_timestamp": datetime.now(UTC).isoformat(timespec="seconds").replace("+00:00", "Z"),
        "hs_note_body": texte_de_la_note(params, ctx),
    }
    if r.get("proprietaire"):
        proprietes["hubspot_owner_id"] = str(r["proprietaire"])
    return Requete(
        "POST",
        "/crm/v3/objects/notes",
        json={"properties": proprietes, "associations": [_association(params["identifiant"], 202)]},
    )


def _affaire(params: dict, ctx: ContexteAction) -> Requete:
    r = {**REGLAGES_AFFAIRE, **ctx.reglages}
    proprietes = {"dealname": titre_affaire(params, ctx), "pipeline": r["pipeline"], "dealstage": r["etape"]}
    if r.get("proprietaire"):
        proprietes["hubspot_owner_id"] = str(r["proprietaire"])
    return Requete(
        "POST",
        "/crm/v3/objects/deals",
        json={"properties": proprietes, "associations": [_association(params["identifiant"], 3)]},
    )


HUBSPOT = declarer(
    Connecteur(
        nom="hubspot",
        libelle="HubSpot",
        integration="hubspot",
        actions=(
            action_trouver(_chercher, _resultat_recherche),
            action_creer_contact(_creer, resultat_creation("id"), REGLAGES_CONTACT),
            action_note(_note, resultat_note, REGLAGES_CONTACT),
            action_affaire(_affaire, resultat_creation("id"), REGLAGES_AFFAIRE),
        ),
    )
)


# --------------------------------------------------------------------------- #
# Translator « dossier »
# --------------------------------------------------------------------------- #


def _dossier(fiche: dict) -> dict:
    p = fiche.get("properties") or {}
    valeurs = {
        "id_externe": str(fiche.get("id")),
        "nom": p.get("lastname"),
        "prenom": p.get("firstname"),
        "mail": p.get("email"),
        "code_postal": p.get("zip"),
        "commune": p.get("city"),
        "telephones": [t for t in (p.get("phone"), p.get("mobilephone")) if t],
    }
    return {k: v for k, v in valeurs.items() if v not in (None, "", [])}


declarer_dossier(
    systeme="hubspot",
    libelle="HubSpot",
    integration="hubspot",
    chercher=lambda a, _o: Requete(
        "POST",
        "/crm/v3/objects/contacts/search",
        json={
            "filterGroups": _filtres(formes_du_numero(a.get("telephone")), None)
            or [{"filters": [{"propertyName": "hs_object_id", "operator": "EQ", "value": str(a.get("reference") or "")}]}],
            "properties": PROPRIETES,
            "limit": 3,
        },
    ),
    lire_liste=lambda r, _a, _o: [_dossier(x) for x in (r or {}).get("results") or []],
    lire=lambda a, _o: Requete(
        "GET", f"/crm/v3/objects/contacts/{quote(str(a['id_externe']), safe='')}", params={"properties": ",".join(PROPRIETES)}
    ),
    lire_un=lambda r, _a, _o: _dossier(r or {}),
)
