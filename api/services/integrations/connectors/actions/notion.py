"""[.mark] Notion (données): a page per call in the team's database (U3 sexies, point 8, F3).

State « À essayer ». Documentation read on 03/11/2026: https://developers.notion.com/reference/post-page
(``POST /v1/pages``; ``parent`` is a ``page_id``, a ``data_source_id`` or a ``database_id``; under a data
source the properties follow its schema, the title as ``{"title": [{"text": {"content": ...}}]}``;
``children`` up to 100 blocks; the header ``Notion-Version`` is required; the answer is the page,
``id`` included; the integration must be shared with the parent). The version header is added by
Nango's relay for its ``notion`` provider: not verified here (the page of the query endpoint, read
too, is deprecated for data sources). Through Nango's relay (integration ``notion``).

- ``create_page`` (writes): the data source (or database) and the name of its title property are the
  client's settings; the page holds the caller's name and number, the reason and the model's note.
Nothing is searched: Notion's search page was not read.
"""

from __future__ import annotations

from typing import Any

from api.services.integrations.connectors.actions._commun import nom_complet
from api.services.integrations.connectors.catalogue import (
    Action,
    Connecteur,
    ContexteAction,
    Parametre,
    declarer,
)
from api.services.integrations.connectors.nango import Requete

REGLAGES = {"type_parent": "data_source_id", "parent": "", "propriete_titre": "Name"}
PARENTS_PERMIS = ("data_source_id", "database_id")


def _bloc(texte: str) -> dict:
    return {
        "object": "block",
        "type": "paragraph",
        "paragraph": {"rich_text": [{"type": "text", "text": {"content": texte[:1900]}}]},
    }


def _preparer(params: dict, ctx: ContexteAction) -> Requete:
    r = {**REGLAGES, **ctx.reglages}
    if r["type_parent"] not in PARENTS_PERMIS or not str(r["parent"]).strip():
        raise ValueError("Notion: the database is not set.")
    c = ctx.modele.contact
    titre = ctx.modele.motif or f"Appel de {nom_complet(c.prenom, c.nom) or c.telephone or 'un appelant'}"
    lignes = [str(params["resume"]).strip()]
    if c.telephone:
        lignes.append(f"Téléphone : {c.telephone}")
    return Requete(
        "POST",
        "/v1/pages",
        json={
            "parent": {r["type_parent"]: str(r["parent"]).strip()},
            "properties": {
                str(r["propriete_titre"]): {"title": [{"text": {"content": titre[:200]}}]},
            },
            "children": [_bloc(ligne) for ligne in lignes],
        },
    )


def _resultat(reponse: Any, _params: dict, _ctx: ContexteAction) -> dict:
    if not (reponse or {}).get("id"):
        raise ValueError("Notion gave no page.")
    return {"cree": True, "identifiant": str(reponse["id"])}


NOTION = declarer(
    Connecteur(
        nom="notion",
        libelle="Notion",
        integration="notion",
        actions=(
            Action(
                nom="create_page",
                description="Write a page about this call in the team's Notion database.",
                parametres=(Parametre("resume", description="What the caller asked and what was agreed, in two or three sentences."),),
                ecrit=True,
                preparer=_preparer,
                resultat=_resultat,
                reglages_par_defaut=REGLAGES,
            ),
        ),
    )
)
