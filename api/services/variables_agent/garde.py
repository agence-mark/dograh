"""[.mark] U3 bis (E62) : la garde de publication des variables et la recherche des champs qui citent une variable.

Une version dont un champ cite une clé absente du catalogue est refusée (même forme que les tests obligatoires). Le
refus nomme la clé, l'étape et le champ. Interrupteur d'urgence : celui de la garde de publication
(``MARK_PUBLICATION_SANS_GARDE``), géré par l'appelant. Une erreur interne ne bloque jamais une publication.
"""

from __future__ import annotations

import re
from typing import Any

from loguru import logger

from api.services.variables_agent import citations as cit
from api.services.variables_agent.catalogue import catalogue_de, cles_connues


async def cles_inconnues_du_brouillon(workflow: Any, brouillon: Any, organization_id: int) -> list[dict[str, Any]]:
    """``[{cle, champ, etape}]`` des citations que le catalogue ne connaît pas. Ne lève jamais."""
    try:
        graphe = getattr(brouillon, "workflow_json", None)
        configs = getattr(brouillon, "workflow_configurations", None)
        if not isinstance(graphe, dict):
            graphe = None
        if not isinstance(configs, dict):
            configs = None
        citations = cit.citations_de(graphe, configs)
        if not citations:
            return []
        essai = getattr(workflow, "template_context_variables", None)
        catalogue = await catalogue_de(organization_id, graphe, configs, essai if isinstance(essai, dict) else None)
        vues: set[tuple[str, str]] = set()
        sortie = []
        for c in cit.inconnues(citations, cles_connues(catalogue)):
            if (c.cle, c.champ) in vues:
                continue
            vues.add((c.cle, c.champ))
            sortie.append({"cle": c.cle, "champ": c.champ, "etape": c.etape})
        return sortie
    except Exception as erreur:  # noqa: BLE001 -- jamais une raison de rater une publication
        logger.warning(f"[.mark] Garde des variables : calcul impossible ({erreur!r})")
        return []


def champs_citant(cle: str, agents: list[tuple[int, str, dict | None, dict | None]]) -> list[dict[str, Any]]:
    """Pure. ``agents`` = (id, nom, graphe, réglages). Les champs qui citent ``{{cle}}`` (avec ou sans repli)."""
    motif = re.compile(r"\{\{\s*" + re.escape(cle) + r"\s*(?:\|[^}]*)?\}\}")
    sortie = []
    for identifiant, nom, graphe, configs in agents:
        for chemin, etape, texte in cit.textes_de(graphe, configs):
            if motif.search(texte or ""):
                sortie.append({"agent_id": identifiant, "agent": nom, "etape": etape, "champ": chemin})
    return sortie


async def champs_citant_dans_l_organisation(organization_id: int, cle: str) -> list[dict[str, Any]]:
    from api.db import db_client

    agents = []
    for workflow in await db_client.list_workflows_for_model_configuration_migration(organization_id):
        brouillon = await db_client.get_draft_version(workflow.id)
        if brouillon is not None:
            agents.append((workflow.id, workflow.name, brouillon.workflow_json, brouillon.workflow_configurations))
    return champs_citant(cle, agents)


