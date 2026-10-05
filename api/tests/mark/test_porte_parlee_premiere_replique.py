"""[.mark] Le champ « première réplique » du nœud (plan porte-parlee, lot 2).

Plan `Labo-agent-vocal/plans/porte-parlee/`, D2 et D3 : un champ des étapes de conversation et de
fin, dans la fenêtre du nœud du graphe ; vide = absent ; l'écran signale les étapes où mène une
porte sans première réplique, sans bloquer.

| Test | Ce qu'il prouve |
|---|---|
| catalogue | le formulaire du nœud (généré depuis le catalogue servi à l'écran et au MCP) a le champ, juste après le prompt, sur l'étape et la fin seulement |
| enregistrement | le nettoyage de la route garde le champ sur l'étape et la fin ; un agent sans le champ ressort à l'identique |
| graphe | le nœud expose la première réplique ; vide ou blanc = absent |
| avertissement | la liste des étapes atteintes par une porte sans première réplique (jamais l'accueil) |
| miroir | la fixture des specs lue par le test d'écran est celle du serveur |
"""

import copy
import json
from pathlib import Path

import pytest

from api.services.workflow.dto import ReactFlowDTO, sanitize_workflow_definition
from api.services.workflow.node_specs import all_specs
from api.services.workflow.porte_parlee import etapes_sans_premiere_replique
from api.services.workflow.workflow_graph import WorkflowGraph
from api.tests.mark.test_clavier_porte_la_fiche import DEFINITION

CHAMP = "premiere_replique"
FIXTURE = (
    Path(__file__).resolve().parents[3]
    / "ui/src/components/mark/graphe/specs-premiere-replique.json"
)


def _specs() -> dict:
    return {spec.name: spec for spec in all_specs()}


def _definition_a_trois_etapes() -> dict:
    """Accueil → étape → fin, la fin atteinte aussi depuis l'accueil."""
    definition = copy.deepcopy(DEFINITION)
    definition["nodes"].insert(
        1,
        {
            "id": "etape",
            "type": "agentNode",
            "position": {"x": 0, "y": 100},
            "data": {"name": "Etape", "prompt": "Tu poses la question."},
        },
    )
    definition["edges"].append(
        {
            "id": "start-etape",
            "source": "start",
            "target": "etape",
            "data": {"label": "vers_etape", "condition": "Quand il faut."},
        }
    )
    definition["edges"].append(
        {
            "id": "etape-end",
            "source": "etape",
            "target": "end",
            "data": {"label": "vers_fin", "condition": "Quand c'est fini."},
        }
    )
    return definition


def _noeud(definition: dict, identifiant: str) -> dict:
    return next(n for n in definition["nodes"] if n["id"] == identifiant)


def _graphe(definition: dict) -> WorkflowGraph:
    return WorkflowGraph(ReactFlowDTO.model_validate(definition))


# --------------------------------------------------------------------------- #
# 1. Le catalogue des nœuds (ce que l'écran et le MCP lisent)
# --------------------------------------------------------------------------- #


@pytest.mark.parametrize("type_", ["agentNode", "endCall"])
def test_le_champ_suit_le_prompt(type_):
    noms = [p.name for p in _specs()[type_].properties]
    assert noms[noms.index("prompt") + 1] == CHAMP
    champ = next(p for p in _specs()[type_].properties if p.name == CHAMP)
    assert champ.display_name == "First reply"
    assert champ.type == "mention_textarea"
    assert '"Transitions in the reply"' in champ.description
    assert not champ.required


@pytest.mark.parametrize("type_", ["startCall", "globalNode"])
def test_ni_l_accueil_ni_le_global_n_ont_le_champ(type_):
    assert CHAMP not in [p.name for p in _specs()[type_].properties]


# --------------------------------------------------------------------------- #
# 2. L'enregistrement
# --------------------------------------------------------------------------- #


def test_le_nettoyage_garde_le_champ_sur_l_etape_et_la_fin():
    definition = _definition_a_trois_etapes()
    for identifiant in ("start", "etape", "end"):
        _noeud(definition, identifiant)["data"][CHAMP] = "Bonjour {{nom}}."
    propre = sanitize_workflow_definition(definition)
    assert _noeud(propre, "etape")["data"][CHAMP] == "Bonjour {{nom}}."
    assert _noeud(propre, "end")["data"][CHAMP] == "Bonjour {{nom}}."
    assert CHAMP not in _noeud(propre, "start")["data"]


def test_un_agent_sans_le_champ_ressort_a_l_identique():
    definition = _definition_a_trois_etapes()
    assert sanitize_workflow_definition(copy.deepcopy(definition)) == definition
    graphe = _graphe(definition)
    assert all(n.premiere_replique is None for n in graphe.nodes.values())


# --------------------------------------------------------------------------- #
# 3. Le graphe
# --------------------------------------------------------------------------- #


@pytest.mark.parametrize(
    "valeur, lue",
    [
        ("  Quelle marque ?  ", "Quelle marque ?"),
        ("", None),
        ("   \n", None),
        (None, None),
    ],
)
def test_le_noeud_expose_la_premiere_replique(valeur, lue):
    definition = _definition_a_trois_etapes()
    _noeud(definition, "etape")["data"][CHAMP] = valeur
    assert _graphe(definition).nodes["etape"].premiere_replique == lue


# --------------------------------------------------------------------------- #
# 4. L'avertissement (D3)
# --------------------------------------------------------------------------- #


def test_les_etapes_sans_premiere_replique_sont_listees_sans_l_accueil():
    definition = _definition_a_trois_etapes()
    assert etapes_sans_premiere_replique(_graphe(definition)) == ["Etape", "End"]
    _noeud(definition, "etape")["data"][CHAMP] = "Quelle marque ?"
    assert etapes_sans_premiere_replique(_graphe(definition)) == ["End"]
    _noeud(definition, "end")["data"][CHAMP] = "Au revoir."
    assert etapes_sans_premiere_replique(_graphe(definition)) == []


# --------------------------------------------------------------------------- #
# 5. Le miroir lu par le test d'écran
# --------------------------------------------------------------------------- #


def test_la_fixture_de_l_ecran_est_le_catalogue_du_serveur():
    """Le test d'écran rend la fenêtre du nœud depuis cette fixture : elle doit être
    le catalogue servi par ``/node-types``, sinon il prouverait un écran qui n'existe pas.
    Régénérer : ``python -m api.tests.mark.test_porte_parlee_premiere_replique``."""
    assert json.loads(FIXTURE.read_text(encoding="utf-8")) == _fixture()


def _fixture() -> dict:
    specs = _specs()
    return {
        type_: specs[type_].model_dump(mode="json")
        for type_ in ("agentNode", "endCall")
    }


if __name__ == "__main__":
    FIXTURE.parent.mkdir(parents=True, exist_ok=True)
    FIXTURE.write_text(
        json.dumps(_fixture(), ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    print(f"écrit : {FIXTURE}")
