"""[.mark] Clôture, lot A (D21) : la permission de CHAQUE outil MCP, dans la même table de droits que l'écran et l'API.

Les actions du builder exposées en MCP lisent leur permission dans ``familles_actions.PERMISSION_DE_LA_FAMILLE`` (la table des routes de l'écran).
Les outils natifs de Dograh sont rangés ici ; ``test_droits_mcp_inventaire.py`` échoue si un outil du serveur n'a pas sa ligne.

* une clé de permission (``agents.modifier``...) : l'outil ÉCRIT ; la clé doit porter cette permission (sa liste de rôle) ;
* ``LECTURE_AGENTS`` : lit les agents, les outils ou le builder d'un client : fermé à une clé de client sans rôle (D10) ;
* ``OUVERT`` : documentation, guide, types de nœuds, documents de connaissance : tout accès par clé valide.
"""

from __future__ import annotations

LECTURE_AGENTS = "lecture_agents"
OUVERT = "ouvert"

PERMISSION_DES_OUTILS_MCP: dict[str, str] = {
    "create_workflow": "agents.modifier",
    "save_workflow": "agents.modifier",
    "create_tool": "agents.modifier",
    "get_workflow": LECTURE_AGENTS,
    "get_workflow_code": LECTURE_AGENTS,
    "list_workflows": LECTURE_AGENTS,
    "list_tools": LECTURE_AGENTS,
    "list_credentials": LECTURE_AGENTS,
    "list_recordings": LECTURE_AGENTS,
    "list_documents": OUVERT,
    "get_node_type": OUVERT,
    "list_node_types": OUVERT,
    "get_voice_prompting_guide": OUVERT,
    "list_docs": OUVERT,
    "read_doc": OUVERT,
    "search_docs": OUVERT,
}
