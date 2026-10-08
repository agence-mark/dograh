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

from collections.abc import Callable
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from api.services.workflow.workflow_graph import Node, WorkflowGraph

# Le repère de la ligne de porte, en tête de réponse (D4).
FLECHE = "→"

# D4, D5, D11 : ce que le code ajoute après la consigne du post-scriptum, sur les
# étapes qui ont des portes. Forme du rejeu 2 (05/10), plus la phrase D11 (les
# portes manquées à l'accueil). Générique : tout le reste vient du graphe et des
# champs de l'écran. Consigne restée en français (D15, rejeu 3).
CONSIGNE_DES_PORTES = """# Les portes de cette étape
Quand tu prends une porte, ta réponse commence par une ligne seule : « → » suivi du nom exact de la porte. Cette ligne n'est jamais dite à la personne. Ensuite, ta phrase, qui est la première réplique de l'étape d'arrivée (liste plus bas), puis le séparateur et ta note, comme d'habitude.
Quand on reste dans cette étape, pas de ligne « → » : ta phrase, le séparateur, ta note.
Une seule porte par réponse. Dès que ce que dit la personne correspond à une porte, tu la prends dans cette réponse : tu ne poses jamais la question de l'étape suivante sans prendre sa porte.

{portes}

# La première réplique des étapes où mènent tes portes
{premieres}"""

# Plan postscriptum-note-d-abord (S1, Q1) : porte → note → phrase.
CONSIGNE_DES_PORTES_NOTE_D_ABORD = """# Les portes de cette étape
Quand tu prends une porte, ta réponse commence par une ligne seule : « → » suivi du nom exact de la porte. Cette ligne n'est jamais dite à la personne. Ensuite ta note, puis le séparateur, puis ta phrase : la première réplique de l'étape d'arrivée (liste plus bas), réglée sur la fiche avec ta note. Si elle demande ce que tu viens de noter ou ce que la fiche a déjà, tu ne le demandes pas : tu poses sa question sur la première chose qui manque encore.
Quand on reste dans cette étape, pas de ligne « → » : ta note, le séparateur, ta phrase.
Une porte dont la condition demande que la fiche porte quelque chose se juge sur la fiche ET sur ta note de cette réponse. Ta note n'y ajoute que ce qui manque encore à la fiche et que la personne a dit : ce que la fiche porte déjà ne se réécrit jamais, même pour prendre une porte. Une porte ne se prend jamais sur une information qui n'a été ni notée avant, ni écrite dans cette note.
Une seule porte par réponse. Dès que ce que dit la personne correspond à une porte, tu la prends dans cette réponse : tu ne poses jamais la question de l'étape suivante sans prendre sa porte.

{portes}

# La première réplique des étapes où mènent tes portes
{premieres}"""

# D3 : une étape d'arrivée sans première réplique écrite à l'écran.
SANS_PREMIERE_REPLIQUE = "pose la première question de cette étape."


def etapes_sans_premiere_replique(graphe: WorkflowGraph) -> list[str]:
    """D3 : les étapes où mène une porte et qui n'ont pas de première réplique,
    dans l'ordre du graphe. L'accueil n'en a jamais besoin (aucune porte n'y mène)."""
    cibles = {arete.target for arete in graphe.edges}
    return [
        noeud.name
        for noeud in graphe.nodes.values()
        if noeud.id in cibles and not noeud.is_start and not noeud.premiere_replique
    ]


def consigne_des_portes(
    noeud: Node,
    graphe: WorkflowGraph,
    rendre: Callable[[str], str],
    note_d_abord: bool = False,
) -> str | None:
    """D5 : le bloc des portes de l'étape (``nom → étape : condition``), puis une
    fois la première réplique de chaque étape d'arrivée de CES portes, rendue avec
    les variables de l'appel comme le prompt. ``None`` : l'étape n'a pas de porte.

    D21 (Evan, 05/10) : seulement les étapes d'arrivée, jamais toutes les étapes.
    Une première réplique peut porter ce que l'agent ne doit pas avoir sous les
    yeux ailleurs (l'adresse du magasin, donc sa commune, dans celle d'« infos ») :
    l'étape des coordonnées, qui ne mène pas à « infos », ne la voit jamais."""
    if not noeud.out_edges:
        return None
    portes = "\n".join(
        f"- {arete.get_function_name()} → étape {graphe.nodes[arete.target].name} : "
        f"{arete.condition}"
        for arete in noeud.out_edges
    )
    arrivees = list(dict.fromkeys(arete.target for arete in noeud.out_edges))
    premieres = "\n".join(
        f"- {etape.name} : "
        f"{rendre(etape.premiere_replique) if etape.premiere_replique else SANS_PREMIERE_REPLIQUE}"
        for etape in (graphe.nodes[cible] for cible in arrivees)
    )
    consigne = CONSIGNE_DES_PORTES_NOTE_D_ABORD if note_d_abord else CONSIGNE_DES_PORTES
    return consigne.format(portes=portes, premieres=premieres)
