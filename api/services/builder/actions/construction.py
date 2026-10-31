"""[.mark] Builder : les actions de construction.

1. Les outils du serveur MCP de l'amont appelés COMME FONCTIONS (lire un agent, types de nœuds, catalogue, créer,
   enregistrer en brouillon, créer un outil, guide de prompts). La fonction appelée est celle que le serveur MCP
   expose : on la cherche dans son module à chaque appel, jamais une copie. ``mcp=False`` : déjà inscrites au MCP.
2. Les opérations de construction regroupées en un brouillon (``brouillon.py``) : exposées aux deux portes.

⛔ Construire (enregistrer, opérer) exige un document de conception APPROUVÉ (B36). Rien ne publie : ``save_workflow``
écrit un brouillon, ``create_workflow`` n'est permis que dans une conversation sans agent.
"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field

import importlib

from api.schemas.tool import CreateToolRequest
from api.services.builder import brouillon, conception
from api.services.builder.actions._commun import (
    agent_de_l_organisation,
    appeler_la_fonction_mcp,
    identifiant_agent,
)
from api.services.builder.actions.registre import Action, Contexte, ErreurAction, enregistrer


# --- 1. les fonctions du serveur MCP -----------------------------------------------------------------------------


class _Statut(BaseModel):
    status: str | None = Field(default="active", description="active | archived | null for all.")


class _Agent(BaseModel):
    workflow_id: int | None = Field(default=None, description="The agent; defaults to the conversation's agent.")


class _Rien(BaseModel):
    pass


class _TypeDeNoeud(BaseModel):
    name: str


class _Enregistrer(BaseModel):
    workflow_id: int | None = None
    code: str = Field(description="The full SDK TypeScript source of the agent.")


class _Creer(BaseModel):
    code: str


class _Enregistrements(BaseModel):
    workflow_id: int | None = None


class _Guide(BaseModel):
    stage: str | None = None
    topic: str | None = None
    node_type: str | None = None


class _CreerUnOutil(BaseModel):
    request: CreateToolRequest


def _outil_mcp(module: str, nom_fonction: str):
    """La fonction que le serveur MCP expose, relue sur son module À CHAQUE appel (jamais une copie). Le module
    est importé à l'appel, pas ici : importer ``api.mcp_server`` charge tout le serveur, qui lit ce registre."""
    return getattr(importlib.import_module(f"api.mcp_server.tools.{module}"), nom_fonction)


def _adaptateur(module: str, nom_fonction: str, *, avec_agent: bool = False):
    async def fonction(contexte: Contexte, parametres: BaseModel) -> dict[str, Any]:
        arguments = parametres.model_dump(exclude_none=False)
        if avec_agent:
            arguments["workflow_id"] = identifiant_agent(contexte, arguments.get("workflow_id"))
        elif "workflow_id" in arguments and arguments["workflow_id"] is None:
            arguments.pop("workflow_id")
        # La fonction est relue sur le module à chaque appel : c'est bien celle que le serveur MCP expose.
        resultat = await appeler_la_fonction_mcp(contexte, _outil_mcp(module, nom_fonction), **arguments)
        return resultat if isinstance(resultat, dict) else {"resultat": resultat}

    return fonction


def _inscrire_lecture(nom: str, description: str, parametres: type[BaseModel], module: str, fonction: str, **options: Any) -> None:
    enregistrer(
        Action(
            nom=nom,
            description=description,
            parametres=parametres,
            fonction=_adaptateur(module, fonction, **options),
            mcp=False,
            groupe="construction",
        )
    )


_inscrire_lecture("list_workflows", "List the agents of the organization.", _Statut, "workflows", "list_workflows")
_inscrire_lecture("get_workflow", "Read an agent (SDK code view).", _Agent, "workflows", "get_workflow", avec_agent=True)
_inscrire_lecture(
    "get_workflow_code", "Read the SDK TypeScript code of an agent, to edit it.", _Agent, "get_workflow_code", "get_workflow_code", avec_agent=True
)
_inscrire_lecture("list_node_types", "List the node types.", _Rien, "node_types", "list_node_types")
_inscrire_lecture("get_node_type", "Describe one node type.", _TypeDeNoeud, "node_types", "get_node_type")
_inscrire_lecture("list_tools", "List the tools of the organization.", _Statut, "catalog", "list_tools")
_inscrire_lecture("list_documents", "List the knowledge-base documents.", _Rien, "catalog", "list_documents")
_inscrire_lecture("list_credentials", "List the credentials (names only).", _Rien, "catalog", "list_credentials")
_inscrire_lecture("list_recordings", "List the recordings of an agent.", _Enregistrements, "catalog", "list_recordings")
_inscrire_lecture(
    "get_voice_prompting_guide", "Fetch the staged voice-prompting guidance.", _Guide, "voice_prompting_guide", "get_voice_prompting_guide"
)


async def _creer_un_outil(contexte: Contexte, parametres: _CreerUnOutil) -> dict[str, Any]:
    return await appeler_la_fonction_mcp(contexte, _outil_mcp("tool_creation", "create_tool"), request=parametres.request)


enregistrer(
    Action(
        nom="create_tool",
        description="Create a reusable tool the agent can call. A tool that writes must first return what to re-read and act only on a yes.",
        parametres=_CreerUnOutil,
        fonction=_creer_un_outil,
        ecriture=True,
        mcp=False,
        groupe="construction",
    )
)


async def _enregistrer_le_code(contexte: Contexte, parametres: _Enregistrer) -> dict[str, Any]:
    identifiant = identifiant_agent(contexte, parametres.workflow_id)
    try:
        await conception.exiger_approuvee(contexte.organisation_id, identifiant)
    except conception.ErreurConception as erreur:
        raise ErreurAction(str(erreur), "conception") from None
    return await appeler_la_fonction_mcp(contexte, _outil_mcp("save_workflow", "save_workflow"), workflow_id=identifiant, code=parametres.code)


enregistrer(
    Action(
        nom="save_workflow",
        description="Save the full SDK source of an agent as a DRAFT (validated). Never publishes. Needs an approved design document.",
        parametres=_Enregistrer,
        fonction=_enregistrer_le_code,
        ecriture=True,
        mcp=False,
        groupe="construction",
    )
)


async def _creer_un_agent(contexte: Contexte, parametres: _Creer) -> dict[str, Any]:
    if contexte.workflow_id is not None:
        raise ErreurAction("This conversation already has its agent: use the draft operations or save_workflow.")
    return await appeler_la_fonction_mcp(contexte, _outil_mcp("create_workflow", "create_workflow"), code=parametres.code)


enregistrer(
    Action(
        nom="create_workflow",
        description="Create a new agent from SDK source (only in a conversation that has no agent yet).",
        parametres=_Creer,
        fonction=_creer_un_agent,
        ecriture=True,
        mcp=False,
        groupe="construction",
    )
)


# --- 2. les opérations regroupées en un brouillon ------------------------------------------------------------------


class _Operations(BaseModel):
    workflow_id: int | None = None
    operations: list[brouillon.Operation] = Field(min_length=1, max_length=40)


async def _exiger_la_conception(contexte: Contexte, identifiant: int) -> None:
    try:
        await conception.exiger_approuvee(contexte.organisation_id, identifiant)
    except conception.ErreurConception as erreur:
        raise ErreurAction(str(erreur), "conception") from None


async def _operer(contexte: Contexte, parametres: _Operations) -> dict[str, Any]:
    workflow = await agent_de_l_organisation(contexte, parametres.workflow_id)
    await _exiger_la_conception(contexte, workflow.id)
    org = contexte.organisation_id
    graphe, version = await brouillon.source_courante(workflow)
    nouvelles = [o.model_dump(exclude_none=True) for o in parametres.operations]

    def ajouter(etat):
        if etat["operations"] and etat.get("base_version") != version:
            raise ErreurAction("The draft changed since the pending operations were prepared: discard them first (brouillon_jeter).")
        try:
            brouillon.appliquer(graphe, [*brouillon.operations_de(etat), *parametres.operations])
        except brouillon.ErreurOperation as erreur:
            raise ErreurAction(str(erreur), "operation") from None
        return {"operations": [*etat["operations"], *nouvelles], "base_version": version}

    # Deux appels simultanés ajoutent chacun leurs opérations : aucune ne s'écrase (revue R6).
    nouvel_etat = await brouillon.modifier_en_attente(org, workflow.id, ajouter)
    return {
        "ok": True,
        "operations": [o.model_dump(exclude_none=True) for o in parametres.operations],
        "en_attente": len(nouvel_etat["operations"]),
    }


async def _voir(contexte: Contexte, parametres: _Agent) -> dict[str, Any]:
    workflow = await agent_de_l_organisation(contexte, parametres.workflow_id)
    etat = await brouillon.lire_en_attente(contexte.organisation_id, workflow.id)
    graphe, _version = await brouillon.source_courante(workflow)
    resultat: dict[str, Any] = {"ok": True, "en_attente": etat["operations"], "noeuds": len((graphe or {}).get("nodes", []))}
    if etat["operations"]:
        apres = brouillon.appliquer(graphe, brouillon.operations_de(etat))
        resultat["erreurs_de_validation"] = await brouillon.valider(apres, contexte.organisation_id)
        resultat["noeuds_apres"] = len(apres["nodes"])
    return resultat


async def _enregistrer_le_brouillon(contexte: Contexte, parametres: _Agent) -> dict[str, Any]:
    workflow = await agent_de_l_organisation(contexte, parametres.workflow_id)
    await _exiger_la_conception(contexte, workflow.id)
    resultat = await brouillon.enregistrer_le_brouillon(workflow, contexte.organisation_id)
    if resultat.get("enregistre"):
        resultat["carte"] = {"type": "changements", **{k: v for k, v in resultat.items() if k != "enregistre"}}
    return {"ok": bool(resultat.get("enregistre")), **resultat}


async def _jeter(contexte: Contexte, parametres: _Agent) -> dict[str, Any]:
    workflow = await agent_de_l_organisation(contexte, parametres.workflow_id)
    await brouillon.ecrire_en_attente(contexte.organisation_id, workflow.id, {"operations": [], "base_version": None})
    return {"ok": True}


for _nom, _description, _parametres, _fonction, _ecriture in (
    (
        "brouillon_operation",
        "Add construction operations (add/modify/remove a node, an edge, a prompt). Each is shown on the graph as it comes; they are grouped into ONE draft saved by brouillon_enregistrer. Needs an approved design document.",
        _Operations,
        _operer,
        True,
    ),
    ("brouillon_voir", "Show the pending operations and whether the resulting graph is valid.", _Agent, _voir, False),
    (
        "brouillon_enregistrer",
        "Save the pending operations as ONE draft version of the agent (validated; never published).",
        _Agent,
        _enregistrer_le_brouillon,
        True,
    ),
    ("brouillon_jeter", "Throw away the pending operations (the saved draft is untouched).", _Agent, _jeter, True),
):
    enregistrer(
        Action(
            nom=_nom,
            description=_description,
            parametres=_parametres,
            fonction=_fonction,
            ecriture=_ecriture,
            groupe="construction",
        )
    )
