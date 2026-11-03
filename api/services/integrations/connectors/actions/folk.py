"""[.mark] folk (CRM): actions and translator « dossier » (U3 sexies, point 8, F2).

State « À essayer »: written from folk's public documentation (https://developer.folk.app/
api-reference, read on 03/11/2026), proven on answers recorded in a file. Through Nango's relay
(integration ``folk``, base ``https://api.folk.app``).

- ``find_contact``: ``GET /v1/people`` with ``filter[phones][eq]`` (international form) or
  ``filter[emails][eq]``.
- ``create_contact``: ``POST /v1/people``; the group of the settings (``groups``) when the client
  chose one. folk merges a duplicate in the background: search first.
- ``add_call_note``: ``POST /v1/notes`` (``entity.id``, ``visibility``, ``content``).
folk has no deals: no ``create_deal`` here.
"""

from __future__ import annotations

from typing import Any
from urllib.parse import quote

from api.services.integrations.connectors.actions._commun import (
    action_creer_contact,
    action_note,
    action_trouver,
    criteres,
    declarer_dossier,
    formes_du_numero,
    identite,
    resultat_creation,
    resultat_note,
    texte_de_la_note,
    trouves,
)
from api.services.integrations.connectors.catalogue import (
    Connecteur,
    ContexteAction,
    declarer,
)
from api.services.integrations.connectors.nango import Requete

REGLAGES_CONTACT = {"groupe": ""}  # folk group id (grp_...); empty = no group


def _recherche(formes: list[str], mail: str | None) -> Requete:
    params: dict[str, Any] = {"limit": 3}
    if formes:
        params["filter[phones][eq]"] = formes[0]
    elif mail:
        params["filter[emails][eq]"] = mail
    return Requete("GET", "/v1/people", params=params)


def _chercher(params: dict, ctx: ContexteAction) -> Requete:
    formes, mail = criteres(params, ctx)
    return _recherche(formes, mail)


def _liste(reponse: Any) -> list[dict]:
    return [p for p in (((reponse or {}).get("data") or {}).get("items") or []) if isinstance(p, dict)]


def _resultat_recherche(reponse: Any, _params: dict, _ctx: ContexteAction) -> dict:
    return trouves([(p.get("id"), p.get("fullName")) for p in _liste(reponse)])


def _creer(params: dict, ctx: ContexteAction) -> Requete:
    i = identite(params, ctx)
    r = {**REGLAGES_CONTACT, **ctx.reglages}
    corps: dict[str, Any] = {}
    if i["prenom"]:
        corps["firstName"] = i["prenom"]
    if i["nom"]:
        corps["lastName"] = i["nom"]
    if i["mail"]:
        corps["emails"] = [i["mail"]]
    if i["telephone"]:
        corps["phones"] = [i["telephone"]]
    if r.get("groupe"):
        corps["groups"] = [{"id": str(r["groupe"])}]
    return Requete("POST", "/v1/people", json=corps)


def _note(params: dict, ctx: ContexteAction) -> Requete:
    return Requete(
        "POST",
        "/v1/notes",
        json={
            "entity": {"id": str(params["identifiant"])},
            "visibility": "public",
            "content": texte_de_la_note(params, ctx),
        },
    )


FOLK = declarer(
    Connecteur(
        nom="folk",
        libelle="folk",
        integration="folk",
        actions=(
            action_trouver(_chercher, _resultat_recherche),
            action_creer_contact(_creer, resultat_creation("data.id"), REGLAGES_CONTACT),
            action_note(_note, resultat_note),
        ),
    )
)


def _dossier(p: dict) -> dict:
    valeurs = {
        "id_externe": str(p.get("id")),
        "nom": p.get("lastName"),
        "prenom": p.get("firstName"),
        "mail": (p.get("emails") or [None])[0],
        "telephones": [t for t in p.get("phones") or [] if t],
    }
    return {k: v for k, v in valeurs.items() if v not in (None, "", [])}


declarer_dossier(
    systeme="folk",
    libelle="folk",
    integration="folk",
    chercher=lambda a, _o: _recherche(formes_du_numero(a.get("telephone")), None),
    lire_liste=lambda r, _a, _o: [_dossier(p) for p in _liste(r)],
    lire=lambda a, _o: Requete("GET", f"/v1/people/{quote(str(a['id_externe']), safe='')}"),
    lire_un=lambda r, _a, _o: _dossier((r or {}).get("data") or {}),
)
