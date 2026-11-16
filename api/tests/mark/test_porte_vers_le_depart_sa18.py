"""[.mark] SA-18, lot C (C17) : une porte vers l'étape de départ est refusée à l'enregistrement, pas en pleine passation.

Avant : ``PUT /workflow/{id}`` l'acceptait ; l'erreur « Start Call cannot have incoming edges » tombait au lancement d'un appel, à la passation.
"""

from api.routes.workflow import _edges_into_start_validation_errors


def _definition(*aretes):
    return {
        "nodes": [{"id": "1", "type": "startCall"}, {"id": "2", "type": "agentNode"}, {"id": "3", "type": "endCall"}],
        "edges": [{"id": f"e{i}", "source": s, "target": t} for i, (s, t) in enumerate(aretes)],
    }


def test_une_porte_vers_le_depart_est_refusee_avec_son_arete():
    erreurs = _edges_into_start_validation_errors(_definition(("1", "2"), ("2", "1")))
    assert [(e["id"], e["message"]) for e in erreurs] == [("e1", "Start Call cannot have incoming edges")]


def test_un_graphe_sans_porte_vers_le_depart_passe():
    assert _edges_into_start_validation_errors(_definition(("1", "2"), ("2", "3"))) == []


def test_une_definition_vide_ou_incomplete_ne_leve_rien():
    assert _edges_into_start_validation_errors(None) == []
    assert _edges_into_start_validation_errors({}) == []
    assert _edges_into_start_validation_errors({"nodes": "x", "edges": []}) == []
    assert _edges_into_start_validation_errors({"nodes": [{"id": "1", "type": "startCall"}], "edges": [None, {"target": "1"}]})[0]["id"] is None
