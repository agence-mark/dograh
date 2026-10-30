"""[.mark] builder-agent-vocal : la seconde porte du moteur du builder (Claude Code par le serveur MCP).

Chaque action du registre du builder (``api/services/builder/actions``) est exposée ici comme outil MCP, avec le
MÊME schéma de paramètres. Son ``run`` ne contient aucune logique : il authentifie la clé d'API comme les autres
outils puis appelle ``registre.executer`` -- le chemin exact que l'écran emprunte. Les actions que le serveur
expose déjà nativement (``mcp=False`` : lire un agent, enregistrer en brouillon...) ne sont pas dupliquées.

L'action est cherchée dans le registre À CHAQUE appel (jamais gardée en copie) : un lot qui remplit un point
d'entrée n'a rien à changer ici.
"""

from __future__ import annotations

from typing import Any

from fastmcp.tools import Tool, ToolResult

from api.mcp_server.auth import authenticate_mcp_request
from api.services.builder import actions
from api.services.builder.actions.registre import PORTE_MCP, REGISTRE, Contexte, executer


class OutilDuBuilder(Tool):
    """Un outil MCP qui délègue au registre du builder."""

    async def run(self, arguments: dict[str, Any]) -> ToolResult:
        user = await authenticate_mcp_request()
        contexte = Contexte(user=user, workflow_id=None, porte=PORTE_MCP)
        resultat = await executer(self.name, arguments, contexte)
        return ToolResult(structured_content=resultat)


def outils_du_builder() -> list[OutilDuBuilder]:
    return [
        OutilDuBuilder(name=action.nom, description=action.description, parameters=action.schema())
        for action in actions.REGISTRE.values()
        if action.mcp
    ]


def inscrire(mcp: Any) -> None:
    for outil in outils_du_builder():
        mcp.add_tool(outil)


__all__ = ["OutilDuBuilder", "REGISTRE", "inscrire", "outils_du_builder"]
