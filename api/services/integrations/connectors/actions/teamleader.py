"""[.mark] Teamleader Focus (CRM): actions and translator « dossier » (U3 sexies, point 8, F2).

State « À essayer ». Teamleader Focus API (https://developer.focus.teamleader.eu/), every call a
``POST`` on ``<resource>.<verb>``; through Nango's relay (integration ``teamleader-focus``).
Read in the documentation: ``contacts.list`` filters (``email``, ``term``) and ``contacts.add``
(``first_name``, ``last_name``, ``emails[{type,email}]``, ``telephones[{type,number}]``).
⚠ ``deals.create`` follows the documented shape (``lead.customer``, ``title``, ``phase_id``,
``responsible_user_id``) but its page could not be read at writing time: to check at the first trial.
No ``add_call_note``: the documentation read does not give a note endpoint on a contact, and an
endpoint guessed is worse than none.

- ``find_contact``: ``contacts.list`` with ``term`` = the number in international form (or the
  e-mail in ``filter.email``).
- ``create_contact``: ``contacts.add``; ``create_deal``: ``deals.create``.
"""

from __future__ import annotations

from typing import Any

from api.services.integrations.connectors.actions._commun import (
    action_affaire,
    action_creer_contact,
    action_trouver,
    criteres,
    declarer_dossier,
    formes_du_numero,
    identite,
    nom_complet,
    resultat_creation,
    titre_affaire,
    trouves,
)
from api.services.integrations.connectors.catalogue import (
    Connecteur,
    ContexteAction,
    declarer,
)
from api.services.integrations.connectors.nango import Requete

REGLAGES_CONTACT: dict = {}
REGLAGES_AFFAIRE = {"proprietaire": "", "phase": "", "departement": ""}  # Teamleader uuids


def _recherche(formes: list[str], mail: str | None) -> Requete:
    filtre = {"term": formes[0]} if formes else {"email": mail}
    return Requete("POST", "/contacts.list", json={"filter": filtre, "page": {"size": 3, "number": 1}})


def _chercher(params: dict, ctx: ContexteAction) -> Requete:
    formes, mail = criteres(params, ctx)
    return _recherche(formes, mail)


def _liste(reponse: Any) -> list[dict]:
    return [c for c in (reponse or {}).get("data") or [] if isinstance(c, dict)]


def _resultat_recherche(reponse: Any, _params: dict, _ctx: ContexteAction) -> dict:
    return trouves([(c.get("id"), nom_complet(c.get("first_name"), c.get("last_name"))) for c in _liste(reponse)])


def _creer(params: dict, ctx: ContexteAction) -> Requete:
    i = identite(params, ctx)
    corps: dict[str, Any] = {"first_name": i["prenom"] or "", "last_name": i["nom"] or "Appelant"}
    if i["mail"]:
        corps["emails"] = [{"type": "primary", "email": i["mail"]}]
    if i["telephone"]:
        corps["telephones"] = [{"type": "mobile", "number": i["telephone"]}]
    return Requete("POST", "/contacts.add", json=corps)


def _affaire(params: dict, ctx: ContexteAction) -> Requete:
    r = {**REGLAGES_AFFAIRE, **ctx.reglages}
    corps: dict[str, Any] = {
        "lead": {"customer": {"type": "contact", "id": str(params["identifiant"])}},
        "title": titre_affaire(params, ctx),
    }
    for cle, champ in (("proprietaire", "responsible_user_id"), ("phase", "phase_id"), ("departement", "department_id")):
        if r.get(cle):
            corps[champ] = str(r[cle])
    return Requete("POST", "/deals.create", json=corps)


TEAMLEADER = declarer(
    Connecteur(
        nom="teamleader",
        libelle="Teamleader",
        integration="teamleader-focus",
        actions=(
            action_trouver(_chercher, _resultat_recherche),
            action_creer_contact(_creer, resultat_creation("data.id"), REGLAGES_CONTACT),
            action_affaire(_affaire, resultat_creation("data.id"), REGLAGES_AFFAIRE),
        ),
    )
)


def _dossier(c: dict) -> dict:
    valeurs = {
        "id_externe": str(c.get("id")),
        "nom": c.get("last_name"),
        "prenom": c.get("first_name"),
        "mail": next((e.get("email") for e in c.get("emails") or [] if isinstance(e, dict) and e.get("email")), None),
        "telephones": [t.get("number") for t in c.get("telephones") or [] if isinstance(t, dict) and t.get("number")],
    }
    return {k: v for k, v in valeurs.items() if v not in (None, "", [])}


declarer_dossier(
    systeme="teamleader",
    libelle="Teamleader",
    integration="teamleader-focus",
    chercher=lambda a, _o: _recherche(formes_du_numero(a.get("telephone")), None),
    lire_liste=lambda r, _a, _o: [_dossier(c) for c in _liste(r)],
    lire=lambda a, _o: Requete("POST", "/contacts.info", json={"id": str(a["id_externe"])}),
    lire_un=lambda r, _a, _o: _dossier((r or {}).get("data") or {}),
)
