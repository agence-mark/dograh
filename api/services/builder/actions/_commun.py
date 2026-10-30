"""[.mark] Builder : aides communes aux actions (agent de l'organisation, appel d'un outil du serveur MCP)."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from api.db import db_client
from api.services.builder.actions.registre import Contexte, ErreurAction
from api.services.builder.identite import UTILISATEUR_DIRECT


def identifiant_agent(contexte: Contexte, demande: int | None) -> int:
    identifiant = demande if demande is not None else contexte.workflow_id
    if identifiant is None:
        raise ErreurAction("Say which agent (workflow_id): this conversation has none.")
    return identifiant


async def agent_de_l_organisation(contexte: Contexte, demande: int | None):
    """L'agent, lu AVEC l'organisation de l'utilisateur (isolation entre clients). 404 sinon."""
    identifiant = identifiant_agent(contexte, demande)
    workflow = await db_client.get_workflow(identifiant, organization_id=contexte.organisation_id)
    if not workflow:
        raise ErreurAction(f"Agent {identifiant} not found.", "introuvable")
    return workflow


async def appeler_la_fonction_mcp(contexte: Contexte, fonction: Callable[..., Any], **arguments: Any) -> Any:
    """Appelle une fonction de ``api/mcp_server/tools/`` comme fonction, au nom de l'utilisateur déjà authentifié."""
    jeton = UTILISATEUR_DIRECT.set(contexte.user)
    try:
        return await fonction(**arguments)
    finally:
        UTILISATEUR_DIRECT.reset(jeton)


async def agent_verifie(contexte: Contexte, demande: int | None) -> int:
    """L'identifiant de l'agent, après avoir vérifié qu'il est bien de l'organisation de l'utilisateur."""
    return (await agent_de_l_organisation(contexte, demande)).id
