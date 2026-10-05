"""L'analyse d'un run déjà lu (.mark, chantier langwatch-et-fenetre-du-run, lots 1 et 3).

La route de la fenêtre du run et la tâche des séries simulées (verdict de latence, coût de chaque
appel) en ont besoin toutes les deux : elle vit ici. La définition jouée (portes, champs de la
fiche) est celle que le run porte ; les réglages de la fenêtre (prix, seuils) sont ceux de
l'organisation. Le run doit avoir été lu DANS cette organisation par l'appelant.

Un appel simulé (lot 3) porte en plus son bloc « simulation » (scénario, verdict du juge,
critères, conversation), lu dans ``run.extra`` ; l'empreinte du jeton n'en sort jamais.
"""

from __future__ import annotations

from api.services.analyse_run.analyse import analyser_run
from api.services.analyse_run.cout import lire_reglages_fenetre
from api.services.appel_simule.entree import CLE_EXTRA
from api.services.workflow.fiche_au_fil_de_leau import CLE_CHAMPS
from api.services.workflow.workflow_graph import transition_tool_name


def _portes(definition) -> set[str] | None:
    if definition is None:
        return None
    aretes = (definition.workflow_json or {}).get("edges") or []
    return {
        transition_tool_name(label)
        for arete in aretes
        if isinstance(arete, dict)
        and isinstance(label := (arete.get("data") or {}).get("label"), str)
        and label
    }


def _champs_fiche(definition) -> list[str] | None:
    if definition is None:
        return None
    champs = (definition.workflow_configurations or {}).get(CLE_CHAMPS)
    if not isinstance(champs, list):
        return None
    return [
        c["nom"]
        for c in champs
        if isinstance(c, dict) and isinstance(c.get("nom"), str)
    ]


def bloc_simulation(run) -> dict | None:
    simulation = (getattr(run, "extra", None) or {}).get(CLE_EXTRA)
    if not isinstance(simulation, dict):
        return None
    return {cle: valeur for cle, valeur in simulation.items() if cle != "jeton_sha256"}


async def analyser_le_run(run, organization_id: int) -> dict:
    definition = run.definition
    analyse = analyser_run(
        {
            "id": run.id,
            "workflow_id": run.workflow_id,
            "definition_id": run.definition_id,
            "mode": run.mode,
            "usage_info": run.usage_info,
            "initial_context": run.initial_context,
            "gathered_context": run.gathered_context,
            "logs": run.logs,
        },
        portes=_portes(definition),
        champs_fiche=_champs_fiche(definition),
        reglages_fenetre=await lire_reglages_fenetre(organization_id),
    )
    simulation = bloc_simulation(run)
    if simulation is not None:
        analyse["simulation"] = simulation
    return analyse
