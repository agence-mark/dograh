"""[.mark] Builder : les opérations de construction, regroupées en UN brouillon (Q8, méthode Vercel).

Le cerveau envoie des opérations une par une (ajouter un nœud, une liaison, modifier un prompt...). Chacune est
renvoyée à l'écran, qui dessine le graphe sous les yeux. Elles attendent sur le disque
(``MARK_BUILDER:<agent>:brouillon``, partagé par l'écran et le MCP) et s'enregistrent d'un coup comme **une**
version brouillon, après la même validation que ``save_workflow``. Rien n'est publié.

Les opérations s'appliquent à une COPIE du graphe courant (le brouillon de l'agent s'il y en a un, sinon la
version publiée) ; si ce graphe change entre-temps, l'enregistrement est refusé (on jette ou on refait).
"""

from __future__ import annotations

import copy
from typing import Any, Literal

from pydantic import BaseModel, Field, ValidationError

from api.db import db_client
from api.services.builder import stock
from api.services.builder.constantes import cle_builder


class ErreurOperation(Exception):
    pass


class Operation(BaseModel):
    op: Literal[
        "ajouter_noeud",
        "modifier_noeud",
        "modifier_prompt",
        "supprimer_noeud",
        "ajouter_liaison",
        "modifier_liaison",
        "supprimer_liaison",
    ]
    id: str | None = Field(default=None, max_length=100, description="Node or edge identifier (generated for a new node).")
    type: str | None = Field(default=None, max_length=50, description="Node type, for ajouter_noeud (see list_node_types).")
    nom: str | None = Field(default=None, max_length=200, description="Node name.")
    prompt: str | None = Field(default=None, max_length=20000, description="Prompt of the node.")
    donnees: dict[str, Any] | None = Field(default=None, description="Other node fields, merged into the node data.")
    source: str | None = Field(default=None, max_length=100)
    target: str | None = Field(default=None, max_length=100)
    label: str | None = Field(default=None, max_length=200, description="Edge label.")
    condition: str | None = Field(default=None, max_length=2000, description="Edge condition.")


def _noeud(graphe: dict, identifiant: str | None) -> dict:
    noeud = next((n for n in graphe["nodes"] if n.get("id") == identifiant), None)
    if noeud is None:
        raise ErreurOperation(f"Unknown node: {identifiant!r}.")
    return noeud


def _identifiant_libre(graphe: dict) -> str:
    pris = {n.get("id") for n in graphe["nodes"]}
    n = len(pris) + 1
    while str(n) in pris:
        n += 1
    return str(n)


def appliquer_une(graphe: dict[str, Any], op: Operation) -> None:
    """Applique UNE opération au graphe (modifié en place). ``ErreurOperation`` sinon, rien n'est à moitié fait."""
    graphe.setdefault("nodes", [])
    graphe.setdefault("edges", [])
    if op.op == "ajouter_noeud":
        if not op.type or not op.nom:
            raise ErreurOperation("ajouter_noeud needs a type and a name.")
        identifiant = op.id or _identifiant_libre(graphe)
        if any(n.get("id") == identifiant for n in graphe["nodes"]):
            raise ErreurOperation(f"Node {identifiant!r} already exists.")
        donnees: dict[str, Any] = {"name": op.nom, **(op.donnees or {})}
        if op.prompt is not None:
            donnees["prompt"] = op.prompt
        graphe["nodes"].append({"id": identifiant, "type": op.type, "position": {"x": 0, "y": 0}, "data": donnees})
    elif op.op == "modifier_noeud":
        noeud = _noeud(graphe, op.id)
        donnees = dict(noeud.get("data") or {})
        donnees.update(op.donnees or {})
        if op.nom is not None:
            donnees["name"] = op.nom
        if op.prompt is not None:
            donnees["prompt"] = op.prompt
        noeud["data"] = donnees
    elif op.op == "modifier_prompt":
        if op.prompt is None:
            raise ErreurOperation("modifier_prompt needs a prompt.")
        noeud = _noeud(graphe, op.id)
        noeud["data"] = {**(noeud.get("data") or {}), "prompt": op.prompt}
    elif op.op == "supprimer_noeud":
        _noeud(graphe, op.id)
        graphe["nodes"] = [n for n in graphe["nodes"] if n.get("id") != op.id]
        graphe["edges"] = [e for e in graphe["edges"] if op.id not in (e.get("source"), e.get("target"))]
    elif op.op == "ajouter_liaison":
        if not (op.source and op.target and op.label and op.condition):
            raise ErreurOperation("ajouter_liaison needs source, target, label and condition.")
        _noeud(graphe, op.source)
        _noeud(graphe, op.target)
        identifiant = op.id or f"{op.source}-{op.target}"
        while any(e.get("id") == identifiant for e in graphe["edges"]):
            identifiant += "'"
        graphe["edges"].append(
            {"id": identifiant, "source": op.source, "target": op.target, "data": {"label": op.label, "condition": op.condition}}
        )
    elif op.op in ("modifier_liaison", "supprimer_liaison"):
        liaison = next((e for e in graphe["edges"] if e.get("id") == op.id), None)
        if liaison is None:
            raise ErreurOperation(f"Unknown edge: {op.id!r}.")
        if op.op == "supprimer_liaison":
            graphe["edges"] = [e for e in graphe["edges"] if e is not liaison]
        else:
            if op.source:
                _noeud(graphe, op.source)
                liaison["source"] = op.source
            if op.target:
                _noeud(graphe, op.target)
                liaison["target"] = op.target
            donnees = dict(liaison.get("data") or {})
            if op.label is not None:
                donnees["label"] = op.label
            if op.condition is not None:
                donnees["condition"] = op.condition
            liaison["data"] = donnees


def appliquer(graphe: dict[str, Any] | None, operations: list[Operation]) -> dict[str, Any]:
    """Une copie du graphe avec toutes les opérations appliquées dans l'ordre."""
    copie = copy.deepcopy(graphe) if graphe else {"nodes": [], "edges": []}
    for rang, op in enumerate(operations, start=1):
        try:
            appliquer_une(copie, op)
        except ErreurOperation as erreur:
            raise ErreurOperation(f"Operation {rang} ({op.op}): {erreur}") from None
    return copie


async def valider(graphe: dict[str, Any], organization_id: int) -> list[str]:
    """Les mêmes contrôles que ``save_workflow`` (forme, graphe, noms d'outils). Liste vide : valide."""
    from api.services.workflow.dto import ReactFlowDTO
    from api.services.workflow.tool_name_validation import validate_workflow_tool_name_collisions
    from api.services.workflow.workflow_graph import WorkflowGraph

    try:
        dto = ReactFlowDTO.model_validate(graphe)
    except ValidationError as erreur:
        return [f"{'.'.join(str(p) for p in e.get('loc', ()))}: {e.get('msg', 'invalid')}" for e in erreur.errors()[:8]]
    try:
        WorkflowGraph(dto)
    except Exception as erreur:  # noqa: BLE001 -- WorkflowGraph lève ValueError, parfois plus
        return [str(erreur)]
    collisions = await validate_workflow_tool_name_collisions(graphe, organization_id)
    return [c["message"] for c in collisions or []]


# --- le brouillon en attente, sur le disque ---------------------------------------------------------------------


def cle_du_brouillon(workflow_id: int) -> str:
    return cle_builder(workflow_id, "brouillon")


async def source_courante(workflow: Any) -> tuple[dict[str, Any] | None, int | None]:
    """(graphe, numéro de version) que les opérations visent : le brouillon de l'agent, sinon le publié."""
    from api.mcp_server.tools._workflow_projection import select_workflow_projection_source

    source = await select_workflow_projection_source(workflow)
    return source.payload, source.version_number


async def configurations_courantes(workflow: Any) -> dict[str, Any]:
    """Les réglages de l'agent (``workflow_configurations``) de la même copie que ``source_courante`` : le brouillon s'il y en a un."""
    draft = await db_client.get_draft_version(workflow.id)
    if draft is not None and getattr(draft, "workflow_json", None):
        return dict(getattr(draft, "workflow_configurations", None) or {})
    released = getattr(workflow, "released_definition", None)
    if released is not None and getattr(released, "workflow_json", None):
        return dict(getattr(released, "workflow_configurations", None) or {})
    return dict(getattr(workflow, "workflow_configurations", None) or {})


async def lire_en_attente(organization_id: int, workflow_id: int) -> dict[str, Any]:
    brut = await stock.lire(organization_id, cle_du_brouillon(workflow_id))
    return brut or {"operations": [], "base_version": None}


async def ecrire_en_attente(organization_id: int, workflow_id: int, etat: dict[str, Any]) -> None:
    await stock.ecrire(organization_id, cle_du_brouillon(workflow_id), etat)


async def modifier_en_attente(organization_id: int, workflow_id: int, transformer) -> dict[str, Any]:
    """Lecture-écriture du brouillon en attente sous condition (revue R6) : ``transformer(etat) -> etat`` est pure et rejouable."""
    rendu = await stock.modifier(
        organization_id, cle_du_brouillon(workflow_id), lambda brut: transformer(brut or {"operations": [], "base_version": None})
    )
    return rendu or {"operations": [], "base_version": None}


def operations_de(etat: dict[str, Any]) -> list[Operation]:
    return [Operation.model_validate(o) for o in etat.get("operations") or []]


async def enregistrer_le_brouillon(workflow: Any, organization_id: int) -> dict[str, Any]:
    """Enregistre les opérations en attente comme UNE version brouillon. Jamais une publication."""
    from api.services.workflow import schema_du_parcours
    from api.services.workflow.layout import reconcile_positions

    etat = await lire_en_attente(organization_id, workflow.id)
    operations = operations_de(etat)
    if not operations:
        return {"enregistre": False, "erreur": "No pending change."}
    graphe, version = await source_courante(workflow)
    if etat.get("base_version") != version:
        return {
            "enregistre": False,
            "erreur": "The agent's draft changed since these operations were prepared: discard them or redo them.",
        }
    try:
        nouveau = appliquer(graphe, operations)
    except ErreurOperation as erreur:
        return {"enregistre": False, "erreur": str(erreur)}
    nouveau = reconcile_positions(nouveau, graphe)
    erreurs = await valider(nouveau, organization_id)
    if erreurs:
        return {"enregistre": False, "erreur": "The graph is not valid.", "erreurs": erreurs}
    nouveau = await schema_du_parcours.a_l_enregistrement(workflow.id, organization_id, nouveau, None) or nouveau
    brouillon = await db_client.save_workflow_draft(workflow_id=workflow.id, workflow_definition=nouveau)
    deja = len(operations)

    def vider(courant):
        # Les opérations arrivées pendant l'enregistrement restent en attente, rebasées sur la version qu'on vient d'écrire.
        reste = list(courant.get("operations") or [])[deja:]
        return {"operations": reste, "base_version": brouillon.version_number}

    await modifier_en_attente(organization_id, workflow.id, vider)
    return {
        "enregistre": True,
        "version": brouillon.version_number,
        "statut": brouillon.status,
        "nombre_operations": len(operations),
        "noeuds": len(nouveau["nodes"]),
        "liaisons": len(nouveau["edges"]),
    }
