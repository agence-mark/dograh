"""[.mark] La porte parlée : changer d'étape sans silence.

Plan ``Labo-agent-vocal/plans/porte-parlee/``. En mode Postscript, avec la case « Transitions in
the reply » (``portes_dans_la_reponse``), le modèle prend une porte DANS sa réponse :

    → nom_de_la_porte
    Quelle est la marque de votre appareil ?
    |||
    {"symptome": "..."}

La ligne ``→`` n'est jamais dite ; le code change d'étape à la fin de la réponse ; la phrase est
la « première réplique » de l'étape d'arrivée, un champ du nœud (D2).

⛔ Le modèle décide toujours de la porte ; le code exécute celle qui est écrite, si elle existe
dans l'étape en cours, sinon il ne fait rien et le trace. ⛔ Aucun mot de métier ici.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from api.services.workflow.workflow_graph import WorkflowGraph


def etapes_sans_premiere_replique(graphe: WorkflowGraph) -> list[str]:
    """D3 : les étapes où mène une porte et qui n'ont pas de première réplique,
    dans l'ordre du graphe. L'accueil n'en a jamais besoin (aucune porte n'y mène)."""
    cibles = {arete.target for arete in graphe.edges}
    return [
        noeud.name
        for noeud in graphe.nodes.values()
        if noeud.id in cibles and not noeud.is_start and not noeud.premiere_replique
    ]
