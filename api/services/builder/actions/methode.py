"""[.mark] Builder : la méthode et les conventions, lues par Claude Code (MCP) avant de construire (U7, M2).

Le builder de l'écran reçoit sa méthode dans sa consigne système (``methode.systeme_complet``) ; Claude Code, lui, passe par
le serveur MCP. Ces deux actions lui rendent EXACTEMENT les mêmes textes (mêmes fonctions de lecture) : les deux portes
construisent avec la même méthode. Lecture seule, ni l'une ni l'autre n'écrit.
"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field

from api.services.builder import contexte as contexte_agent
from api.services.builder import methode
from api.services.builder.actions.registre import Action, Contexte, enregistrer


class _Rien(BaseModel):
    pass


class _Methode(BaseModel):
    workflow_id: int | None = Field(default=None, description="The agent: adds the recipe it is built with and its construction method.")


async def _methode(contexte: Contexte, parametres: _Methode) -> dict[str, Any]:
    identifiant = parametres.workflow_id if parametres.workflow_id is not None else contexte.workflow_id
    recette = await methode.section_de_la_recette(contexte.organisation_id, identifiant)
    return {
        "ok": True,
        "methode": await methode.charger_methode(),
        **({"recette": recette} if recette else {}),
        "suite": "Then read the conventions (builder_conventions), the sheets of the families (bibliotheque_lister) and the recipes "
        "(bibliotheque_lister with a family, then bibliotheque_lire) before building. A candidate is not proven: say so.",
    }


async def _conventions(contexte: Contexte, parametres: _Rien) -> dict[str, Any]:
    return {"ok": True, "conventions": await contexte_agent.conventions()}


for _nom, _description, _fonction, _parametres in (
    (
        "builder_methode",
        "Read the .mark method for building a voice agent (the same text the builder of the screen follows). Read it FIRST, before building or editing anything. Give workflow_id to get the recipe of that agent too.",
        _methode,
        _Methode,
    ),
    (
        "builder_conventions",
        "Read the .mark conventions (layer 1 of the builder's context). Read them before building or editing an agent.",
        _conventions,
        _Rien,
    ),
):
    enregistrer(
        Action(nom=_nom, description=_description, parametres=_parametres, fonction=_fonction, ecriture=False, groupe="bibliotheque")
    )
