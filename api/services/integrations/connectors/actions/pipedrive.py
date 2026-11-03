"""[.mark] Pipedrive (CRM): actions and translator « dossier » (U3 sexies, point 8, F2).

State « À essayer »: written from Pipedrive's public documentation (API v2 for persons, deals and
search, v1 for notes, https://developers.pipedrive.com/docs/api/v1), proven on answers recorded in a
file. Through Nango's relay (integration ``pipedrive``, which knows the company's domain).

- ``find_contact``: ``GET /api/v2/persons/search`` on the phone field (the last nine digits, so the
  international and the national typing both match) or the e-mail field.
- ``create_contact``: ``POST /api/v2/persons``; owner = the client's setting.
- ``add_call_note``: ``POST /api/v1/notes`` on the person.
- ``create_deal``: ``POST /api/v2/deals`` in the pipeline and stage of the settings.
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

REGLAGES_CONTACT = {"proprietaire": ""}  # Pipedrive user id; empty = the connected user
REGLAGES_AFFAIRE = {"proprietaire": "", "pipeline": "", "etape": ""}  # ids; empty = Pipedrive's default


def _neuf_chiffres(forme: str) -> str:
    return "".join(c for c in forme if c.isdigit())[-9:]


def _recherche(formes: list[str], mail: str | None) -> Requete:
    if formes:
        terme, champs = _neuf_chiffres(formes[0]), "phone"
    else:
        terme, champs = str(mail), "email"
    return Requete(
        "GET",
        "/api/v2/persons/search",
        params={"term": terme, "fields": champs, "limit": 3},
    )


def _chercher(params: dict, ctx: ContexteAction) -> Requete:
    formes, mail = criteres(params, ctx)
    return _recherche(formes, mail)


def _items(reponse: Any) -> list[dict]:
    return [
        i.get("item") or {}
        for i in ((reponse or {}).get("data") or {}).get("items") or []
        if isinstance(i, dict)
    ]


def _lire_recherche(reponse: Any, _params: dict, _ctx: ContexteAction) -> dict:
    return trouves([(p.get("id"), p.get("name")) for p in _items(reponse)])


def _creer(params: dict, ctx: ContexteAction) -> Requete:
    i = identite(params, ctx)
    r = {**REGLAGES_CONTACT, **ctx.reglages}
    corps: dict[str, Any] = {"name": nom_complet(i["prenom"], i["nom"]) or i["telephone"] or i["mail"]}
    if i["mail"]:
        corps["emails"] = [{"value": i["mail"], "primary": True, "label": "work"}]
    if i["telephone"]:
        corps["phones"] = [{"value": i["telephone"], "primary": True, "label": "mobile"}]
    if r.get("proprietaire"):
        corps["owner_id"] = int(r["proprietaire"])
    return Requete("POST", "/api/v2/persons", json=corps)


def _note(params: dict, ctx: ContexteAction) -> Requete:
    return Requete(
        "POST",
        "/api/v1/notes",
        json={
            "content": texte_de_la_note(params, ctx).replace("\n", "<br>"),
            "person_id": int(params["identifiant"]),
        },
    )


def _affaire(params: dict, ctx: ContexteAction) -> Requete:
    r = {**REGLAGES_AFFAIRE, **ctx.reglages}
    corps: dict[str, Any] = {"title": titre_affaire(params, ctx), "person_id": int(params["identifiant"])}
    for cle, champ in (("proprietaire", "owner_id"), ("pipeline", "pipeline_id"), ("etape", "stage_id")):
        if r.get(cle):
            corps[champ] = int(r[cle])
    return Requete("POST", "/api/v2/deals", json=corps)


PIPEDRIVE = declarer(
    Connecteur(
        nom="pipedrive",
        libelle="Pipedrive",
        integration="pipedrive",
        actions=(
            action_trouver(_chercher, _lire_recherche),
            action_creer_contact(_creer, resultat_creation("data.id"), REGLAGES_CONTACT),
            action_note(_note, resultat_note),
            action_affaire(_affaire, resultat_creation("data.id"), REGLAGES_AFFAIRE),
        ),
    )
)


def _dossier(personne: dict) -> dict:
    telephones = [p.get("value") for p in personne.get("phones") or [] if isinstance(p, dict) and p.get("value")]
    mails = [e.get("value") for e in personne.get("emails") or [] if isinstance(e, dict) and e.get("value")]
    valeurs = {
        "id_externe": str(personne.get("id")),
        "nom": personne.get("name"),
        "mail": mails[0] if mails else None,
        "telephones": telephones,
    }
    return {k: v for k, v in valeurs.items() if v not in (None, "", [])}


def _chercher_dossier(a: dict, _o) -> Requete:
    formes = formes_du_numero(a.get("telephone"))
    if formes:
        return _recherche(formes, None)
    return Requete(
        "GET", "/api/v2/persons/search", params={"term": str(a.get("reference") or ""), "limit": 3}
    )


declarer_dossier(
    systeme="pipedrive",
    libelle="Pipedrive",
    integration="pipedrive",
    chercher=_chercher_dossier,
    lire_liste=lambda r, _a, _o: [
        {"id_externe": str(p["id"]), "nom": p.get("name")} for p in _items(r) if p.get("id")
    ],
    lire=lambda a, _o: Requete("GET", f"/api/v2/persons/{quote(str(a['id_externe']), safe='')}"),
    lire_un=lambda r, _a, _o: _dossier((r or {}).get("data") or {}),
)
