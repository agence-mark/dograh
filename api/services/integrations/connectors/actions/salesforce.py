"""[.mark] Salesforce (CRM): actions and translator « dossier » (U3 sexies, point 8, F2).

State « À essayer »: written from Salesforce's public documentation (REST API: SOQL ``query``,
``sobjects``; https://developer.salesforce.com/docs/atlas.en-us.api_rest.meta), proven on answers
recorded in a file. Through Nango's relay (integration ``salesforce``, which knows the org's
instance URL).

- ``find_contact``: SOQL on ``Contact`` (``Phone``, ``MobilePhone`` for every typing of the number,
  or ``Email``). Every value put in the query is escaped.
- ``create_contact``: ``POST /sobjects/Contact`` (a last name is required by Salesforce: « Appelant »
  when the caller gave none); owner = the client's setting.
- ``add_call_note``: a completed ``Task`` (call) on the contact: the activity history, which every
  Salesforce edition has (a ``Note`` needs the notes feature switched on).
- ``create_deal``: an ``Opportunity`` in the stage of the settings, then the contact's role on it.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any
from urllib.parse import quote

from api.services.integrations.connectors import nango
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

VERSION = "v60.0"
BASE = f"/services/data/{VERSION}"
CHAMPS = "Id, FirstName, LastName, Email, Phone, MobilePhone, MailingPostalCode, MailingCity"
REGLAGES_CONTACT = {"proprietaire": ""}  # Salesforce user Id; empty = the connected user
REGLAGES_AFFAIRE = {"proprietaire": "", "etape": "Prospecting", "delai_cloture_jours": 30}


def echapper(valeur: str) -> str:
    """A text put between quotes in SOQL: backslash and quote escaped, line breaks refused."""
    texte = str(valeur).replace("\\", "\\\\").replace("'", "\\'")
    return texte.replace("\n", " ").replace("\r", " ")


def _soql(formes: list[str], mail: str | None, limite: int = 3) -> str:
    conditions = []
    if formes:
        liste = ", ".join(f"'{echapper(f)}'" for f in formes)
        conditions += [f"Phone IN ({liste})", f"MobilePhone IN ({liste})"]
    if mail:
        conditions.append(f"Email = '{echapper(mail)}'")
    return f"SELECT {CHAMPS} FROM Contact WHERE {' OR '.join(conditions)} LIMIT {limite}"


def _chercher(params: dict, ctx: ContexteAction) -> Requete:
    formes, mail = criteres(params, ctx)
    return Requete("GET", f"{BASE}/query", params={"q": _soql(formes, mail)})


def _nom(c: dict) -> str:
    return nom_complet(c.get("FirstName"), c.get("LastName"))


def _resultat_recherche(reponse: Any, _params: dict, _ctx: ContexteAction) -> dict:
    return trouves([(c.get("Id"), _nom(c)) for c in (reponse or {}).get("records") or []])


def _creer(params: dict, ctx: ContexteAction) -> Requete:
    i = identite(params, ctx)
    r = {**REGLAGES_CONTACT, **ctx.reglages}
    corps = {
        "FirstName": i["prenom"],
        "LastName": i["nom"] or "Appelant",
        "Email": i["mail"],
        "Phone": i["telephone"],
        "OwnerId": r.get("proprietaire") or None,
    }
    return Requete("POST", f"{BASE}/sobjects/Contact", json={k: v for k, v in corps.items() if v})


def _note(params: dict, ctx: ContexteAction) -> Requete:
    r = {**REGLAGES_CONTACT, **ctx.reglages}
    corps = {
        "Subject": "Appel de l'assistant vocal",
        "Description": texte_de_la_note(params, ctx),
        "WhoId": str(params["identifiant"]),
        "Status": "Completed",
        "TaskSubtype": "Call",
        "ActivityDate": datetime.now(UTC).date().isoformat(),
        "OwnerId": r.get("proprietaire") or None,
    }
    return Requete("POST", f"{BASE}/sobjects/Task", json={k: v for k, v in corps.items() if v})


def _affaire(params: dict, ctx: ContexteAction) -> Requete:
    r = {**REGLAGES_AFFAIRE, **ctx.reglages}
    cloture = datetime.now(UTC).date() + timedelta(days=int(r["delai_cloture_jours"]))
    corps = {
        "Name": titre_affaire(params, ctx),
        "StageName": r["etape"],
        "CloseDate": cloture.isoformat(),
        "OwnerId": r.get("proprietaire") or None,
    }
    return Requete("POST", f"{BASE}/sobjects/Opportunity", json={k: v for k, v in corps.items() if v})


async def _role_du_contact(reponse: Any, params: dict, ctx: ContexteAction) -> Any:
    """The opportunity exists: the contact takes his role on it (a second request, same connection)."""
    if (reponse or {}).get("id") and ctx.organization_id is not None:
        await nango.relayer(
            ctx.organization_id,
            "salesforce",
            Requete(
                "POST",
                f"{BASE}/sobjects/OpportunityContactRole",
                json={
                    "OpportunityId": reponse["id"],
                    "ContactId": str(params["identifiant"]),
                    "IsPrimary": True,
                },
            ),
            delai=5.0,
        )
    return reponse


def _affaire_action():
    from dataclasses import replace

    return replace(
        action_affaire(_affaire, resultat_creation("id"), REGLAGES_AFFAIRE), suite=_role_du_contact
    )


SALESFORCE = declarer(
    Connecteur(
        nom="salesforce",
        libelle="Salesforce",
        integration="salesforce",
        actions=(
            action_trouver(_chercher, _resultat_recherche),
            action_creer_contact(_creer, resultat_creation("id"), REGLAGES_CONTACT),
            action_note(_note, resultat_note, REGLAGES_CONTACT),
            _affaire_action(),
        ),
    )
)


def _dossier(c: dict) -> dict:
    valeurs = {
        "id_externe": str(c.get("Id")),
        "nom": c.get("LastName"),
        "prenom": c.get("FirstName"),
        "mail": c.get("Email"),
        "code_postal": c.get("MailingPostalCode"),
        "commune": c.get("MailingCity"),
        "telephones": [t for t in (c.get("Phone"), c.get("MobilePhone")) if t],
    }
    return {k: v for k, v in valeurs.items() if v not in (None, "", [])}


def _chercher_dossier(a: dict, _o) -> Requete:
    formes = formes_du_numero(a.get("telephone"))
    if not formes:
        raise ValueError("A Salesforce contact is found by his phone number.")
    return Requete("GET", f"{BASE}/query", params={"q": _soql(formes, None)})


declarer_dossier(
    systeme="salesforce",
    libelle="Salesforce",
    integration="salesforce",
    chercher=_chercher_dossier,
    lire_liste=lambda r, _a, _o: [_dossier(c) for c in (r or {}).get("records") or []],
    lire=lambda a, _o: Requete(
        "GET", f"{BASE}/sobjects/Contact/{quote(str(a['id_externe']), safe='')}", params={"fields": CHAMPS.replace(" ", "")}
    ),
    lire_un=lambda r, _a, _o: _dossier(r or {}),
)
