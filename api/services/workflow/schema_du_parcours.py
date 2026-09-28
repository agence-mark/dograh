"""[.mark] Chantier correctifs-modules, lot 4 bis : le schéma du parcours.

Plan : ``Labo-agent-vocal/plans/correctifs-modules/2026-09-28-plan-correctifs-modules.md``.

Réglage d'agent ``generer_schema_parcours`` (« Generate the flow map »), éteint par
défaut. Allumé, chaque enregistrement de l'agent lit son graphe et écrit :

- à la fin du prompt global, un bloc ``<parcours>`` : chaque étape, et sous elle
  ses portes (le nom de la fonction que le modèle appelle → l'étape d'arrivée) ;
- à la fin du prompt de chaque étape, ``<position>Tu es ici : <étape></position>``.

Pourquoi dans le code : écrit à la main (le ``schema.js`` des agents de la
refonte), le schéma finit faux dès qu'une porte change. Généré à l'enregistrement,
il ne peut pas diverger du graphe.

⛔ Ce qui n'y entre jamais : autre chose que les noms d'étapes et de portes
(aucun rôle, aucun mot de métier). ⛔ Les blocs sont délimités et remplacés à
chaque enregistrement : jamais empilés, jamais au contact du texte écrit à la main
(une ligne vide les sépare). Éteint : les blocs laissés sont retirés, et un agent
qui n'en a jamais eu s'enregistre exactement comme avant.
"""

from __future__ import annotations

import copy
import re
from typing import Any

from api.services.workflow.workflow_graph import transition_tool_name

CLE_REGLAGE = "generer_schema_parcours"

DEBUT_PARCOURS, FIN_PARCOURS = "<parcours>", "</parcours>"
DEBUT_POSITION, FIN_POSITION = "<position>", "</position>"
# Les étapes d'un appel ; le nœud global, les déclencheurs et les webhooks n'en sont pas.
TYPES_ETAPE = ("startCall", "agentNode", "endCall")
TYPE_GLOBAL = "globalNode"

_BLOCS = re.compile(
    rf"\s*(?:{re.escape(DEBUT_PARCOURS)}.*?{re.escape(FIN_PARCOURS)}"
    rf"|{re.escape(DEBUT_POSITION)}.*?{re.escape(FIN_POSITION)})",
    re.DOTALL,
)


def retirer(prompt: str | None) -> str | None:
    """Le prompt sans les blocs générés. Sans bloc, le prompt tel quel."""
    if not prompt or (DEBUT_PARCOURS not in prompt and DEBUT_POSITION not in prompt):
        return prompt
    return _BLOCS.sub("", prompt).rstrip()


def _ajouter(prompt: str | None, bloc: str) -> str:
    texte = (prompt or "").rstrip()
    return f"{texte}\n\n{bloc}" if texte else bloc


def _nom(noeud: dict) -> str:
    return str((noeud.get("data") or {}).get("name") or noeud.get("id"))


def _ordre_des_etapes(etapes: list[dict], edges: list[dict]) -> list[dict]:
    """Dans l'ordre d'un appel : en largeur depuis l'étape de départ, puis les
    étapes qu'aucune porte n'atteint, dans l'ordre du graphe."""
    par_id = {n["id"]: n for n in etapes}
    depart = [n["id"] for n in etapes if n.get("type") == "startCall"]
    vues: list[str] = list(depart)
    for courante in vues:
        for edge in edges:
            if edge.get("source") == courante and edge.get("target") in par_id and edge["target"] not in vues:
                vues.append(edge["target"])
    vues += [n["id"] for n in etapes if n["id"] not in vues]
    return [par_id[i] for i in vues]


def parcours(definition: dict) -> str:
    """Le bloc ``<parcours>`` du graphe."""
    noeuds = definition.get("nodes") or []
    edges = definition.get("edges") or []
    etapes = [n for n in noeuds if n.get("type") in TYPES_ETAPE]
    par_id = {n["id"]: n for n in etapes}
    lignes = [DEBUT_PARCOURS]
    for etape in _ordre_des_etapes(etapes, edges):
        lignes.append(_nom(etape))
        for edge in edges:
            if edge.get("source") != etape["id"] or edge.get("target") not in par_id:
                continue
            porte = transition_tool_name(str((edge.get("data") or {}).get("label") or ""))
            lignes.append(f"  {porte} → {_nom(par_id[edge['target']])}")
    lignes.append(FIN_PARCOURS)
    return "\n".join(lignes)


def appliquer(definition: dict | None, allume: bool) -> dict | None:
    """La définition avec les blocs à jour (allumé) ou retirés (éteint).

    Toujours une copie ; une définition sans bloc, éteinte, revient identique."""
    if not definition:
        return definition
    resultat = copy.deepcopy(definition)
    bloc = parcours(resultat) if allume else None
    for noeud in resultat.get("nodes") or []:
        data = noeud.get("data")
        if not isinstance(data, dict) or not isinstance(data.get("prompt"), (str, type(None))):
            continue
        type_noeud = noeud.get("type")
        if type_noeud != TYPE_GLOBAL and type_noeud not in TYPES_ETAPE:
            continue
        propre = retirer(data.get("prompt"))
        if allume and type_noeud == TYPE_GLOBAL:
            propre = _ajouter(propre, bloc)
        elif allume:
            propre = _ajouter(propre, f"{DEBUT_POSITION}Tu es ici : {_nom(noeud)}{FIN_POSITION}")
        if propre != data.get("prompt"):
            data["prompt"] = propre
    return resultat


def reglage_allume(configurations: dict | None) -> bool | None:
    """La valeur de la case dans ces configurations, ``None`` si elle n'y est pas."""
    if not configurations or CLE_REGLAGE not in configurations:
        return None
    return bool(configurations[CLE_REGLAGE])


async def a_l_enregistrement(
    workflow_id: int,
    organization_id: int,
    definition: dict | None,
    configurations: dict | None,
) -> dict | None:
    """La définition à enregistrer, ou ``None`` s'il n'y a rien à écrire.

    - Le graphe est enregistré : ses blocs suivent la case (celle de cet
      enregistrement, sinon celle déjà enregistrée).
    - La case seule est enregistrée : le graphe enregistré est mis à jour, et
      renvoyé seulement s'il change.
    """
    from api.db import db_client

    allume = reglage_allume(configurations)
    if allume is None and definition is None:
        return None
    existante = None
    if allume is None or definition is None:
        workflow = await db_client.get_workflow(workflow_id, organization_id=organization_id)
        if workflow is None:
            return definition
        brouillon = await db_client.get_draft_version(workflow_id)
        active = brouillon or workflow.released_definition
        if active is None:
            return definition
        if allume is None:
            allume = bool(reglage_allume(active.workflow_configurations))
        existante = active.workflow_json
    if definition is not None:
        return appliquer(definition, allume)
    nouvelle = appliquer(existante, allume)
    return nouvelle if nouvelle != existante else None
