"""[.mark] Airtable (données): find and create a record (U3 sexies, point 8, F3).

State « À essayer ». Documentation read on 03/11/2026: https://airtable.com/developers/web/api/
list-records (``GET /v0/{baseId}/{tableIdOrName}``, ``filterByFormula`` URL-encoded, ``maxRecords``,
``fields``; answer ``records[]`` with ``id``, ``createdTime``, ``fields``). ⚠️ The page of
``create-records`` could not be read (connection reset twice): the body ``{"fields": {...}}`` with
``typecast`` and the answer's ``id`` are written from the usual shape, to check on a test base.
Through Nango's relay (integration ``airtable``).

- ``find_record`` (reads, may be anticipated): the record whose phone field holds the caller's number
  (international typing or national typing, as stored); returns the fields the client chose to read.
- ``create_record`` (writes): a record with the caller's identity in the fields the client named.
The base, table and field names are the client's settings: nothing comes from the model.
"""

from __future__ import annotations

from typing import Any
from urllib.parse import quote

from api.services.integrations.connectors.actions._commun import formes_du_numero, identite, nom_complet
from api.services.integrations.connectors.catalogue import (
    Action,
    Connecteur,
    ContexteAction,
    Parametre,
    declarer,
)
from api.services.integrations.connectors.nango import Requete

REGLAGES = {
    "base": "",  # app...
    "table": "",
    "champ_telephone": "Téléphone",
    "champ_nom": "Nom",
    "champ_mail": "Email",
    "champ_motif": "",  # empty = the reason is not written
    "champs_lus": "Nom",  # what find_record returns, comma separated
}


def _reglages(ctx: ContexteAction) -> dict:
    r = {**REGLAGES, **ctx.reglages}
    if not (str(r["base"]).startswith("app") and str(r["table"]).strip()):
        raise ValueError("Airtable: the base (app...) and the table are not set.")
    return r


def _chemin(r: dict) -> str:
    return f"/v0/{quote(str(r['base']), safe='')}/{quote(str(r['table']), safe='')}"


def _litteral(valeur: str) -> str:
    """A text inside an Airtable formula: quoted, quote and backslash escaped, so a value never
    breaks out of the string."""
    return '"' + valeur.replace("\\", "\\\\").replace('"', '\\"') + '"'


def _champ(nom: str) -> str:
    if "}" in nom or "{" in nom:
        raise ValueError("A field name cannot hold braces.")
    return "{" + nom + "}"


def _chercher(params: dict, ctx: ContexteAction) -> Requete:
    r = _reglages(ctx)
    formes = formes_du_numero(params.get("telephone") or ctx.modele.contact.telephone)
    if not formes:
        raise ValueError("Nothing to look the record up with: no phone number.")
    champ = _champ(str(r["champ_telephone"]))
    tests = ",".join(f"{champ}={_litteral(f)}" for f in formes)
    return Requete(
        "GET",
        _chemin(r),
        params={"filterByFormula": f"OR({tests})", "maxRecords": 1},
    )


def _resultat_recherche(reponse: Any, _params: dict, ctx: ContexteAction) -> dict:
    lus = [x.strip() for x in str({**REGLAGES, **ctx.reglages}["champs_lus"]).split(",") if x.strip()]
    records = (reponse or {}).get("records") or []
    if not records:
        return {"enregistrement": None, "aucun": True}
    champs = records[0].get("fields") or {}
    return {
        "enregistrement": {
            "identifiant": str(records[0].get("id")),
            "champs": {nom: champs.get(nom) for nom in lus if champs.get(nom) not in (None, "")},
        }
    }


def _creer(params: dict, ctx: ContexteAction) -> Requete:
    r = _reglages(ctx)
    i = identite(params, ctx)
    champs: dict[str, Any] = {
        r["champ_nom"]: nom_complet(i["prenom"], i["nom"]) or None,
        r["champ_telephone"]: i["telephone"],
        r["champ_mail"]: i["mail"],
    }
    if r.get("champ_motif") and ctx.modele.motif:
        champs[r["champ_motif"]] = ctx.modele.motif
    return Requete("POST", _chemin(r), json={"fields": {k: v for k, v in champs.items() if k and v}})


def _resultat_creation(reponse: Any, _params: dict, _ctx: ContexteAction) -> dict:
    if not (reponse or {}).get("id"):
        raise ValueError("Airtable gave no record.")
    return {"cree": True, "identifiant": str(reponse["id"])}


AIRTABLE = declarer(
    Connecteur(
        nom="airtable",
        libelle="Airtable",
        integration="airtable",
        actions=(
            Action(
                nom="find_record",
                description="Look the caller up in the business's Airtable table by his number.",
                parametres=(
                    Parametre("telephone", description="His phone number, if different from the one he calls from.", obligatoire=False),
                ),
                ecrit=False,
                anticipable_permis=True,
                preparer=_chercher,
                resultat=_resultat_recherche,
                reglages_par_defaut=REGLAGES,
            ),
            Action(
                nom="create_record",
                description="Add the caller to the business's Airtable table. Search first: never create twice.",
                parametres=(
                    Parametre("prenom", description="His first name.", obligatoire=False),
                    Parametre("nom", description="His last name.", obligatoire=False),
                    Parametre("mail", description="His e-mail address, as he says it.", obligatoire=False),
                    Parametre("telephone", description="His phone number, if different from the one he calls from.", obligatoire=False),
                ),
                ecrit=True,
                preparer=_creer,
                resultat=_resultat_creation,
                reglages_par_defaut=REGLAGES,
            ),
        ),
    )
)
