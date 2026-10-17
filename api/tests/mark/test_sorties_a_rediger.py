"""[.mark] Relecture du lot 6 d'orchestrateur-trois-cerveaux : une sortie encore « à rédiger ».

Le gabarit d'un collègue et la complétion d'un groupe posent une sortie « Fin » dont la condition et
l'étape d'arrivée portent le texte d'attente. Tant qu'il n'est pas rédigé, cette sortie n'est offerte
à aucune porte et le bloc « # Ton équipe » ne la cite pas ; rédigée, elle revient. Seul le texte
d'attente exact compte : toute autre condition (agents existants) est offerte comme avant.

| Test | Ce qu'il prouve |
|---|---|
| gabarit du collègue | la sortie Fin n'est pas dans les sorties de l'étape, la sortie de retour oui |
| texte rédigé | condition et fin écrites : la sortie Fin est offerte et citée |
"""

import copy

from api.services.groupe.groupe import graphe_minimal_du_specialise
from api.services.groupe.passations import A_REDIGER
from api.services.workflow.dto import ReactFlowDTO
from api.services.workflow.schema_du_parcours import _equipe_specialiste
from api.services.workflow.workflow_graph import WorkflowGraph


def _graphe(definition: dict) -> WorkflowGraph:
    return WorkflowGraph(ReactFlowDTO(nodes=definition["nodes"], edges=definition["edges"]))


def _sorties(graphe: WorkflowGraph, noeud: str) -> set[str]:
    return {arete.target for arete in graphe.nodes[noeud].out_edges}


def _ecrit(definition: dict) -> dict:
    ecrite = copy.deepcopy(definition)
    for noeud in ecrite["nodes"]:
        if noeud["data"].get("prompt") == A_REDIGER:
            noeud["data"]["prompt"] = "Une phrase écrite."
    for arete in ecrite["edges"]:
        if arete["data"].get("condition") == A_REDIGER:
            arete["data"]["condition"] = "Une condition écrite."
    return ecrite


def test_la_fin_a_rediger_du_gabarit_n_est_offerte_a_aucune_porte():
    definition = graphe_minimal_du_specialise()
    graphe = _graphe(definition)
    assert _sorties(graphe, "2") == {"3"}
    assert len(graphe.edges) == len(definition["edges"])
    equipe = " ".join(_equipe_specialiste(definition["nodes"]))
    assert "sortie Fin" not in equipe
    assert "sortie Retour au principal" in equipe


def test_la_fin_redigee_redevient_une_sortie():
    definition = _ecrit(graphe_minimal_du_specialise())
    assert _sorties(_graphe(definition), "2") == {"3", "4"}
    assert "sortie Fin" in " ".join(_equipe_specialiste(definition["nodes"]))

