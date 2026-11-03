"""[.mark] Builder (U3, E30) : lire et poser les ÉTIQUETTES d'un agent, par les deux portes.

Reprend ``services/etiquettes`` (le même code que l'écran : mêmes limites, même cloisonnement par organisation, une
étiquette nouvelle est créée pour toute l'organisation). L'agent est relu avec l'organisation de l'utilisateur : une
étiquette ne se pose jamais sur l'agent d'un autre client.
"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field

from api.services.builder.actions._commun import agent_de_l_organisation
from api.services.builder.actions.registre import Action, Contexte, ErreurAction, enregistrer
from api.services.etiquettes import stockage


class _Etiquettes(BaseModel):
    workflow_id: int | None = Field(default=None, description="The agent (default: the conversation's agent).")
    etiquettes: list[str] | None = Field(
        default=None,
        max_length=stockage.PAR_AGENT_MAX,
        description=(
            "The labels the agent carries from now on (they REPLACE the previous ones; an empty list removes them all). "
            "A new label is created for the whole organization. Omit to only read the agent's labels."
        ),
    )


async def _etiquettes(contexte: Contexte, parametres: _Etiquettes) -> dict[str, Any]:
    agent = await agent_de_l_organisation(contexte, parametres.workflow_id)
    try:
        if parametres.etiquettes is not None:
            vue = await stockage.poser(contexte.organisation_id, agent.id, parametres.etiquettes)
        else:
            vue = await stockage.lire(contexte.organisation_id)
    except stockage.ErreurEtiquette as erreur:
        raise ErreurAction(str(erreur), "etiquettes") from None
    return {
        "ok": True,
        "workflow_id": agent.id,
        "etiquettes_de_l_agent": vue["par_agent"].get(agent.id, []),
        "etiquettes_de_l_organisation": [e["nom"] for e in vue["etiquettes"]],
    }


enregistrer(
    Action(
        nom="etiquettes_agent",
        description=(
            "Read or set the labels of an agent (a mark that crosses the folders: recipe, model, bench). "
            "Giving 'etiquettes' replaces the agent's labels; a label without any agent disappears from the list filter."
        ),
        parametres=_Etiquettes,
        fonction=_etiquettes,
        ecriture=True,
        groupe="etiquettes",
    )
)
