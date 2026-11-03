"""[.mark] Sellsy (CRM): actions and translator « dossier » (U3 sexies, point 8, F2).

State « À essayer ». Sellsy API v2 (https://docs.sellsy.com/api/v2/), through Nango's relay
(integration ``sellsy``, base ``https://api.sellsy.com/v2``). ⚠ The public reference could not be
read in full at writing time (the page served an index only): the paths and fields below follow
the documented v2 resources (``individuals``, ``contacts/search``, ``comments``, ``opportunities``)
and MUST be checked against the account at the first trial. Answers recorded in a file prove the
reading and the bodies, not the software.

- ``find_contact``: ``POST /contacts/search`` filtered by phone or e-mail.
- ``create_contact``: ``POST /individuals`` (a person, not a company).
- ``add_call_note``: ``POST /comments`` related to the contact.
- ``create_deal``: ``POST /opportunities`` in the pipeline and step of the settings, related to the
  contact.
"""

from __future__ import annotations

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

REGLAGES_CONTACT = {"proprietaire": ""}  # Sellsy staff id; empty = the connected user
REGLAGES_AFFAIRE = {"proprietaire": "", "pipeline": "", "etape": ""}  # ids in Sellsy


def _recherche(formes: list[str], mail: str | None) -> Requete:
    filtres: dict[str, Any] = {}
    if formes:
        filtres["phone_number"] = formes[0]
    elif mail:
        filtres["email"] = mail
    return Requete("POST", "/contacts/search", params={"limit": 3}, json={"filters": filtres})


def _chercher(params: dict, ctx: ContexteAction) -> Requete:
    formes, mail = criteres(params, ctx)
    return _recherche(formes, mail)


def _liste(reponse: Any) -> list[dict]:
    return [c for c in (reponse or {}).get("data") or [] if isinstance(c, dict)]


def _resultat_recherche(reponse: Any, _params: dict, _ctx: ContexteAction) -> dict:
    return trouves([(c.get("id"), nom_complet(c.get("first_name"), c.get("last_name")) or c.get("name")) for c in _liste(reponse)])


def _creer(params: dict, ctx: ContexteAction) -> Requete:
    i = identite(params, ctx)
    r = {**REGLAGES_CONTACT, **ctx.reglages}
    corps: dict[str, Any] = {
        "first_name": i["prenom"],
        "last_name": i["nom"] or "Appelant",
        "email": i["mail"],
        "mobile_number": i["telephone"],
    }
    if r.get("proprietaire"):
        corps["owner_id"] = int(r["proprietaire"])
    return Requete("POST", "/individuals", json={k: v for k, v in corps.items() if v})


def _lien(identifiant: str) -> list[dict]:
    return [{"id": int(identifiant), "type": "individual"}]


def _note(params: dict, ctx: ContexteAction) -> Requete:
    return Requete(
        "POST",
        "/comments",
        json={"description": texte_de_la_note(params, ctx), "related": _lien(params["identifiant"])},
    )


def _affaire(params: dict, ctx: ContexteAction) -> Requete:
    r = {**REGLAGES_AFFAIRE, **ctx.reglages}
    corps: dict[str, Any] = {"name": titre_affaire(params, ctx), "related": _lien(params["identifiant"])}
    for cle, champ in (("proprietaire", "owner_id"), ("pipeline", "pipeline"), ("etape", "step")):
        if r.get(cle):
            corps[champ] = int(r[cle])
    return Requete("POST", "/opportunities", json=corps)


SELLSY = declarer(
    Connecteur(
        nom="sellsy",
        libelle="Sellsy",
        integration="sellsy",
        actions=(
            action_trouver(_chercher, _resultat_recherche),
            action_creer_contact(_creer, resultat_creation("id"), REGLAGES_CONTACT),
            action_note(_note, resultat_note),
            action_affaire(_affaire, resultat_creation("id"), REGLAGES_AFFAIRE),
        ),
    )
)


def _dossier(c: dict) -> dict:
    valeurs = {
        "id_externe": str(c.get("id")),
        "nom": c.get("last_name") or c.get("name"),
        "prenom": c.get("first_name"),
        "mail": c.get("email"),
        "telephones": [t for t in (c.get("phone_number"), c.get("mobile_number")) if t],
    }
    return {k: v for k, v in valeurs.items() if v not in (None, "", [])}


declarer_dossier(
    systeme="sellsy",
    libelle="Sellsy",
    integration="sellsy",
    chercher=lambda a, _o: _recherche(formes_du_numero(a.get("telephone")), None),
    lire_liste=lambda r, _a, _o: [_dossier(c) for c in _liste(r)],
    lire=lambda a, _o: Requete("GET", f"/contacts/{quote(str(a['id_externe']), safe='')}"),
    lire_un=lambda r, _a, _o: _dossier(r or {}),
)
