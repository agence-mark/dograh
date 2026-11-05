"""[.mark] Builder partie 3, N2 (sous-lot 1) : modifier les réglages d'un outil EXISTANT (audit 05 § 4 : tout réglage d'outil a son accès).

Le builder pouvait créer, essayer, passer à une version et supprimer un outil, pas en changer un réglage (corps et valeurs fixes d'une requête,
destination d'un transfert, phrase de fin d'appel, serveur MCP, règles d'une action de logiciel...). ``outil_modifier`` rejoue l'enregistrement
de la fenêtre de l'outil : la fonction de la route ``PUT /tools/{uuid}`` (mêmes validations, mêmes champs gardés par le serveur) avec la
définition COMPLÈTE : la configuration en place fusionnée avec les seuls réglages envoyés (``null`` retire un réglage).

L'état d'avant (nom, description, définition) est rangé dans la ligne du journal : « Annuler » le remet par la même route.
"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field

from api.services.builder.actions.entreprise import _ecran, _inscrire
from api.services.builder.actions.registre import Contexte, ErreurAction


def fusionner_la_config(en_place: dict[str, Any], envoye: dict[str, Any]) -> dict[str, Any]:
    """Les réglages envoyés sont posés dans ceux en place ; ``None`` retire le réglage ; un bloc (résolveur, règles) est fusionné."""
    sortie = dict(en_place)
    for cle, valeur in envoye.items():
        if valeur is None:
            sortie.pop(cle, None)
        elif isinstance(valeur, dict) and isinstance(sortie.get(cle), dict):
            sortie[cle] = fusionner_la_config(sortie[cle], valeur)
        else:
            sortie[cle] = valeur
    return sortie


class _OutilModifier(BaseModel):
    outil: str = Field(min_length=1, max_length=64, description="The tool uuid (list_tools gives it).")
    nom: str | None = Field(default=None, min_length=1, max_length=255, description="A new name, if it changes.")
    description: str | None = Field(default=None, max_length=2000, description="A new description for the model, if it changes.")
    reglages: dict[str, Any] = Field(
        default_factory=dict,
        description="ONLY the settings of the tool to change (its definition's config: url, method, body_template, preset_parameters, destination, "
        "context_mapping, messageType, workflow_id, ...); the others keep their value; null removes one.",
    )


async def _existant(contexte: Contexte, uuid: str):
    from api.db import db_client

    outil = await db_client.get_tool_by_uuid(uuid, contexte.organisation_id, include_archived=True)
    if outil is None:
        raise ErreurAction(f"Tool {uuid} not found.", "introuvable")
    return outil


def _corps(nom: str, description: str | None, definition: dict[str, Any]):
    from api.schemas.tool import UpdateToolRequest

    return UpdateToolRequest(name=nom, description=description or None, definition=definition)


async def _modifier(contexte: Contexte, p: _OutilModifier) -> dict[str, Any]:
    from api.routes.tool import update_tool

    if p.nom is None and p.description is None and not p.reglages:
        raise ErreurAction("Nothing to change: give a name, a description or settings.", "rien")
    outil = await _existant(contexte, p.outil)
    definition = dict(outil.definition or {})
    if "config" not in definition and p.reglages:
        raise ErreurAction("This kind of tool has no settings to change.", "sans_reglages")
    if p.reglages:
        definition["config"] = fusionner_la_config(dict(definition.get("config") or {}), p.reglages)
    try:
        corps = _corps(p.nom or outil.name, outil.description if p.description is None else p.description, definition)
    except ValueError as erreur:
        raise ErreurAction(f"Refused by the screen's checks: {str(erreur)[:300]}", "refus_ecran") from None
    rendu = await _ecran(update_tool(p.outil, corps, contexte.user))
    return {"ok": True, "outil": rendu}


async def _avant(contexte: Contexte, arguments: dict[str, Any]) -> dict[str, Any]:
    outil = await _existant(contexte, arguments.get("outil", ""))
    return {"outil": outil.tool_uuid, "nom": outil.name, "description": outil.description, "definition": outil.definition}


async def _remettre(contexte: Contexte, avant: dict[str, Any]) -> None:
    from api.routes.tool import update_tool

    await _ecran(update_tool(avant["outil"], _corps(avant["nom"], avant.get("description"), avant["definition"]), contexte.user))


_inscrire(
    "outil_modifier",
    "Change the settings of an EXISTING tool (what its window offers: request body and fixed values, destination of a transfer, end-of-call sentence, MCP server, software action). "
    "Send only the settings to change.",
    _OutilModifier,
    _modifier,
    ecriture=True,
    groupe="reglages",
    avant=_avant,
    defaire=_remettre,
)
