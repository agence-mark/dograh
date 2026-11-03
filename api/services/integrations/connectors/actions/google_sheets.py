"""[.mark] Google Sheets (données): one row per call, one row looked up (U3 sexies, point 8, F3).

State « À essayer ». Documentation read on 03/11/2026: Sheets API v4, ``spreadsheets.values.append``
(``POST /v4/spreadsheets/{id}/values/{range}:append``, ``valueInputOption`` required, ``insertDataOption``;
the answer holds ``updates``) and ``values.get`` (``GET .../values/{range}``, ``majorDimension``).
⚠️ The pages did not list the fields of ``ValueRange`` (``values``, ``majorDimension``) nor those of
``updates``: written from the usual shape, to check on the first test account.
Through Nango's relay (integration ``google-sheet``).

- ``append_row`` (writes): the sheet is the client's setting; the row is the date, the caller's name,
  number, e-mail, the reason and the model's note, in that order.
- ``find_row`` (reads, may be anticipated): the first row whose phone column holds the caller's number
  (any typing of it); returns the cells of the columns the client chose to read, nothing else.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any
from urllib.parse import quote

from api.services.integrations.connectors.actions._commun import formes_du_numero, nom_complet
from api.services.integrations.connectors.actions._donnees import chiffres_finaux, colonne_index
from api.services.integrations.connectors.catalogue import (
    Action,
    Connecteur,
    ContexteAction,
    Parametre,
    declarer,
)
from api.services.integrations.connectors.nango import Requete

REGLAGES = {
    "classeur": "",  # spreadsheet id
    "feuille": "Appels",
    "colonne_telephone": "C",  # where find_row looks the number up
    "colonnes_lues": "A,B",  # what find_row returns
}
MAX_LIGNES = 2000


def _classeur(ctx: ContexteAction) -> tuple[str, dict]:
    r = {**REGLAGES, **ctx.reglages}
    if not str(r.get("classeur") or "").strip():
        raise ValueError("Google Sheets: the spreadsheet is not set.")
    return quote(str(r["classeur"]).strip(), safe=""), r


def _ajouter(params: dict, ctx: ContexteAction) -> Requete:
    classeur, r = _classeur(ctx)
    c = ctx.modele.contact
    ligne = [
        datetime.now(UTC).strftime("%Y-%m-%d %H:%M"),
        nom_complet(c.prenom, c.nom),
        c.telephone or "",
        c.mail or "",
        ctx.modele.motif or "",
        str(params.get("note") or ""),
    ]
    return Requete(
        "POST",
        f"/v4/spreadsheets/{classeur}/values/{quote(str(r['feuille']), safe='')}:append",
        params={"valueInputOption": "RAW", "insertDataOption": "INSERT_ROWS"},
        json={"majorDimension": "ROWS", "values": [ligne]},
    )


def _resultat_ajout(reponse: Any, _params: dict, _ctx: ContexteAction) -> dict:
    if not ((reponse or {}).get("updates") or {}).get("updatedRows"):
        raise ValueError("Google Sheets added no row.")
    return {"ajoute": True}


def _chercher(params: dict, ctx: ContexteAction) -> Requete:
    classeur, r = _classeur(ctx)
    if not formes_du_numero(params.get("telephone") or ctx.modele.contact.telephone):
        raise ValueError("Nothing to look the row up with: no phone number.")
    return Requete(
        "GET",
        f"/v4/spreadsheets/{classeur}/values/{quote(str(r['feuille']), safe='')}",
        params={"majorDimension": "ROWS"},
    )


def _resultat_recherche(reponse: Any, params: dict, ctx: ContexteAction) -> dict:
    r = {**REGLAGES, **ctx.reglages}
    cherche = chiffres_finaux(params.get("telephone") or ctx.modele.contact.telephone)
    tel = colonne_index(r["colonne_telephone"])
    lues = [colonne_index(x) for x in str(r["colonnes_lues"]).split(",") if x.strip()]
    for ligne in ((reponse or {}).get("values") or [])[:MAX_LIGNES]:
        if tel < len(ligne) and cherche and chiffres_finaux(ligne[tel]) == cherche:
            return {"ligne": [str(ligne[i]) if i < len(ligne) else "" for i in lues]}
    return {"ligne": None, "aucun": True}


GOOGLE_SHEETS = declarer(
    Connecteur(
        nom="google_sheets",
        libelle="Google Sheets",
        integration="google-sheet",
        actions=(
            Action(
                nom="append_row",
                description="Add one line about this call to the business's spreadsheet.",
                parametres=(Parametre("note", description="What to keep, in one sentence.", obligatoire=False),),
                ecrit=True,
                preparer=_ajouter,
                resultat=_resultat_ajout,
                reglages_par_defaut=REGLAGES,
            ),
            Action(
                nom="find_row",
                description=(
                    "Look the caller up in the business's spreadsheet by his number. "
                    "Returns the columns the business chose to read."
                ),
                parametres=(
                    Parametre("telephone", description="His phone number, if different from the one he calls from.", obligatoire=False),
                ),
                ecrit=False,
                anticipable_permis=True,
                preparer=_chercher,
                resultat=_resultat_recherche,
                reglages_par_defaut=REGLAGES,
            ),
        ),
    )
)
