"""[.mark] RA-B, R4 (b) : une variable d'extraction ne porte pas le nom d'un champ de la fiche (audit 02 B1)."""

import pytest
from pydantic import ValidationError

from api.routes.workflow import UpdateWorkflowRequest


def _definition(nom_extrait: str) -> dict:
    return {
        "nodes": [
            {
                "id": "1",
                "type": "agentNode",
                "position": {"x": 0, "y": 0},
                "data": {
                    "name": "Étape",
                    "prompt": "x",
                    "extraction_enabled": True,
                    "extraction_variables": [{"name": nom_extrait, "type": "string", "prompt": "p"}],
                },
            }
        ],
        "edges": [],
    }


def _config(*champs: str) -> dict:
    return {"fiche_champs": [{"nom": c, "type": "string", "origine": "dicte"} for c in champs]}


def test_une_extraction_du_meme_nom_qu_un_champ_de_fiche_est_refusee():
    with pytest.raises(ValidationError) as erreur:
        UpdateWorkflowRequest(workflow_definition=_definition("objet"), workflow_configurations=_config("nom", "objet"))
    assert "objet" in str(erreur.value)


def test_une_extraction_d_un_autre_nom_passe():
    requete = UpdateWorkflowRequest(
        workflow_definition=_definition("ville"), workflow_configurations=_config("nom", "objet")
    )
    assert requete.workflow_definition is not None


def test_sans_fiche_ou_sans_definition_rien_n_est_refuse():
    UpdateWorkflowRequest(workflow_definition=_definition("objet"))
    UpdateWorkflowRequest(workflow_configurations=_config("objet"))
