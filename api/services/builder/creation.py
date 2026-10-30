"""[.mark] Builder : créer l'agent d'une demande (remplace ``POST /workflow/create/template``, service hébergé de Dograh).

Plus d'appel au service hébergé : la demande (sens de l'appel, cas d'usage, description) devient le **contexte de
l'agent** (couche 2) et l'agent naît comme un squelette NEUTRE (départ -> fin), à construire avec le builder. Rien
n'est inventé : les textes du squelette disent seulement qu'ils sont à définir ; aucun contenu de prompt d'agent.
"""

from __future__ import annotations

from typing import Any

from api.db import db_client
from api.services.builder import contexte
from api.services.groupe.reglages import CONFIGURATION_DE_CREATION
from api.services.workflow.dto import ReactFlowDTO
from api.services.workflow.layout import reconcile_positions

A_DEFINIR = "À définir avec le builder."


def squelette() -> dict[str, Any]:
    graphe = {
        "nodes": [
            {"id": "1", "type": "startCall", "position": {"x": 0, "y": 0}, "data": {"name": "Départ", "prompt": A_DEFINIR}},
            {"id": "2", "type": "endCall", "position": {"x": 0, "y": 0}, "data": {"name": "Fin", "prompt": A_DEFINIR}},
        ],
        "edges": [{"id": "1-2", "source": "1", "target": "2", "data": {"label": "Terminé", "condition": A_DEFINIR}}],
    }
    reconcile_positions(graphe, None)
    ReactFlowDTO.model_validate(graphe)  # le squelette doit toujours être valide
    return graphe


def nom_de_l_agent(use_case: str, call_type: str) -> str:
    nom = f"{use_case.strip()} - {call_type.strip()}".strip(" -")
    return nom[:120] or "Nouvel agent"


async def creer(user: Any, call_type: str, use_case: str, activity_description: str):
    """Crée l'agent squelette et note la demande dans son contexte. Rend le workflow créé."""
    workflow = await db_client.create_workflow(
        nom_de_l_agent(use_case, call_type),
        squelette(),
        user.id,
        user.selected_organization_id,
        workflow_configurations=CONFIGURATION_DE_CREATION,
    )
    notes = f"Demande initiale\nSens de l'appel : {call_type}\nCas d'usage : {use_case}\nDescription : {activity_description}"
    await contexte.ecrire_notes(user.selected_organization_id, workflow.id, notes)
    return workflow
