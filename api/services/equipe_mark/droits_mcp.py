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


# --- Les trois gestes qui coûtent ou engagent, par la porte MCP (décision d'Evan du 09/11) ------------------------------------------------
# Chaque clé d'API porte trois interrupteurs (éteints par défaut) ; ils tiennent lieu de carte d'accord pour la porte MCP, qui n'en a pas. Un
# interrupteur allumé ne donne RIEN de plus que le rôle : il faut en plus que le rôle de la clé porte la permission du geste (table unique) et que
# le créateur de la clé l'ait (plafond). ``irreversible`` (supprimer, archiver) reste fermé à la porte MCP : aucun interrupteur ne l'ouvre.
GESTE_PUBLIER = "publier"
GESTE_TESTS_PAYANTS = "tests_payants"
GESTE_APPELS_REELS = "appels_reels"
# Les permissions qu'un geste exige (celles de ses actions dans ``familles_actions``) : pour allumer un interrupteur, il faut les avoir TOUTES soi-même.
GESTES_MCP: dict[str, frozenset[str]] = {
    GESTE_PUBLIER: frozenset({"agents.publier"}),
    GESTE_TESTS_PAYANTS: frozenset({"tests.jouer"}),
    GESTE_APPELS_REELS: frozenset({"agents.publier", "tests.jouer"}),  # départ d'une campagne, appel de test vers un vrai numéro
}
LIBELLES_DES_GESTES = {
    GESTE_PUBLIER: ("Publier par MCP", "Publish through MCP"),
    GESTE_TESTS_PAYANTS: ("Tests payants par MCP", "Paid tests through MCP"),
    GESTE_APPELS_REELS: ("Appels réels par MCP", "Real calls through MCP"),
}
FAMILLE_DU_GESTE = {"publication": GESTE_PUBLIER, "appels_reels": GESTE_APPELS_REELS}
ACTIONS_DE_TESTS_PAYANTS = frozenset({"tests_rejouer", "attaques_lancer", "attaques_rejouer"})


def geste_de_l_action(nom: str, famille: str | None) -> str | None:
    """L'interrupteur que cette action du builder exige à la porte MCP, ou ``None`` (aucun)."""
    if nom in ACTIONS_DE_TESTS_PAYANTS:
        return GESTE_TESTS_PAYANTS
    return FAMILLE_DU_GESTE.get(famille or "")


def refus_interrupteur_eteint(geste: str) -> dict:
    """Le refus, dans UN format (code, texte anglais, texte français, réglage à allumer)."""
    fr, en = LIBELLES_DES_GESTES[geste]
    return {
        "ok": False,
        "code": "mcp_interrupteur_eteint",
        "reglage": geste,
        "erreur": f"This API key may not do this through MCP: turn on « {en} » in the key's panel (Settings > Keys).",
        "erreur_fr": f"Cette clé d'API ne peut pas le faire par MCP : allumez « {fr} » dans le panneau de la clé (Réglages > Clés).",
    }
