"""[.mark] Builder, lot M : la sauvegarde avant modification (choix, éteint par défaut) et le rendu du graphe par le code.

* ``sauvegarde_prendre`` / ``sauvegarde_refuser`` : levée de la garde de ``sauvegarde.py`` ; le refus n'est posé qu'après la
  réponse explicite de la personne ;
* ``agent_montrer_le_graphe`` : le graphe du brouillon en texte et en Mermaid (``rendu_graphe.py``), aucun jeton, lecture seule.
"""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field

from api.services.builder import brouillon, rendu_graphe, sauvegarde
from api.services.builder.actions._commun import agent_de_l_organisation
from api.services.builder.actions.registre import Action, Contexte, enregistrer


class _Agent(BaseModel):
    workflow_id: int | None = Field(default=None, description="The agent; defaults to the conversation's agent.")


class _Refus(_Agent):
    raison: str = Field(min_length=1, max_length=300, description="What the person said, in a few words.")
    la_personne_a_dit_non: Literal[True] = Field(description="Only true if the person explicitly said she does not want a backup.")


class _Graphe(_Agent):
    format: Literal["texte", "mermaid", "les_deux"] = "les_deux"
    avec_les_changements_en_attente: bool = Field(default=False, description="Draw the graph as it would be once the pending operations apply.")


async def _prendre(contexte: Contexte, parametres: _Agent) -> dict[str, Any]:
    workflow = await agent_de_l_organisation(contexte, parametres.workflow_id)
    return {"ok": True, **await sauvegarde.prendre(contexte, workflow)}


async def _refuser(contexte: Contexte, parametres: _Refus) -> dict[str, Any]:
    workflow = await agent_de_l_organisation(contexte, parametres.workflow_id)
    await sauvegarde.refuser(contexte, workflow.id, parametres.raison)
    return {"ok": True, "refusee": True}


async def _montrer(contexte: Contexte, parametres: _Graphe) -> dict[str, Any]:
    workflow = await agent_de_l_organisation(contexte, parametres.workflow_id)
    graphe, version = await brouillon.source_courante(workflow)
    if parametres.avec_les_changements_en_attente:
        etat = await brouillon.lire_en_attente(contexte.organisation_id, workflow.id)
        if etat["operations"]:
            graphe = brouillon.appliquer(graphe, brouillon.operations_de(etat))
    rendu: dict[str, Any] = {"ok": True, "version": version, "noeuds": len((graphe or {}).get("nodes") or [])}
    if parametres.format in ("texte", "les_deux"):
        rendu["texte"] = rendu_graphe.en_texte(graphe)
    if parametres.format in ("mermaid", "les_deux"):
        rendu["mermaid"] = rendu_graphe.en_mermaid(graphe)
    return rendu


for _nom, _description, _parametres, _fonction, _ecriture in (
    (
        "sauvegarde_prendre",
        "Take a backup of the agent's draft graph before changing an existing agent (needed only when the backup rule is on). 'Revenir avant' restores it.",
        _Agent,
        _prendre,
        True,
    ),
    (
        "sauvegarde_refuser",
        "Record that the person explicitly does not want a backup of this agent. Ask her first; never decide for her.",
        _Refus,
        _refuser,
        True,
    ),
    (
        "agent_montrer_le_graphe",
        "Draw the agent's graph as text and as Mermaid, computed by the code (no model call). Read-only.",
        _Graphe,
        _montrer,
        False,
    ),
):
    enregistrer(
        Action(nom=_nom, description=_description, parametres=_parametres, fonction=_fonction, ecriture=_ecriture, groupe="construction")
    )
