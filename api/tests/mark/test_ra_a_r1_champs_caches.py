"""RA-A, R1 (audit du 04/11, rouge n° 1) : le builder n'efface plus aucun réglage d'étape.

Le code que le builder lit (``get_workflow_code``) ne porte pas les champs ``spec_exclude`` du DTO
(``retour_au_principal``, ``travail_de_fond``, ``fins``, ``condition_sur_la_fiche`` d'une liaison...).
``save_workflow`` remplaçait tout : un aller-retour les effaçait en silence. Ce test traverse la vraie
route (vrai validateur Node), seule la base est remplacée.
"""

from __future__ import annotations

import re
import shutil
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from api.mcp_server.tools.get_workflow_code import get_workflow_code
from api.mcp_server.tools.save_workflow import save_workflow

pytestmark = pytest.mark.skipif(
    shutil.which("node") is None, reason="node binary not available"
)

CHAMPS_CACHES_ETAPE = {
    "retour_au_principal": True,
    "etape_de_retour": True,
    "travail_de_fond": True,
    "verite_des_actions": False,
    "declenchement_de_l_action": "automatique",
    "demande_type": "Cherche un creneau pour {{nom}}",
    "conditions_de_champs": [{"champ": "adresse", "si": "type", "vaut": "domicile"}],
    "mcp_tool_filters": {"serveur": ["outil_a"]},
}
FINS = [{"champ": "refus", "vaut": "oui", "phrase": "Tres bien, bonne journee."}]
CONDITION_LIAISON = {"etape_complete": False, "champ": "refus", "vaut": "oui"}


def _stocke() -> dict:
    def noeud(i, type_, x, **data):
        return {"id": i, "type": type_, "position": {"x": x, "y": 0}, "data": data}

    return {
        "nodes": [
            noeud("1", "startCall", 0, name="Accueil", prompt="Bonjour"),
            noeud("2", "agentNode", 400, name="Rdv", prompt="Prends le rendez-vous", **CHAMPS_CACHES_ETAPE),
            noeud("3", "agentNode", 800, name="Autre", prompt="Autre chose", travail_de_fond=True),
            noeud("4", "endCall", 1200, name="Fin", prompt="Au revoir", fins=FINS),
        ],
        "edges": [
            {"id": "1-2", "source": "1", "target": "2",
             "data": {"label": "Rdv", "condition": "veut un rdv", "condition_sur_la_fiche": CONDITION_LIAISON}},
            {"id": "2-3", "source": "2", "target": "3", "data": {"label": "Autre", "condition": "autre"}},
            {"id": "2-4", "source": "2", "target": "4", "data": {"label": "Fin", "condition": "fini"}},
            {"id": "3-4", "source": "3", "target": "4", "data": {"label": "Fin bis", "condition": "fini aussi"}},
        ],
    }


@pytest.fixture
def banc():
    stocke = _stocke()
    user = MagicMock()
    user.selected_organization_id = 1
    user.id = 1
    wf = SimpleNamespace(
        id=1, organization_id=1, name="test", current_definition=None,
        released_definition=None, workflow_definition=None, workflow_configurations={},
    )
    sauve = AsyncMock(return_value=SimpleNamespace(version_number=2, status="draft"))
    draft = SimpleNamespace(workflow_json=stocke, version_number=1, workflow_configurations={})
    with (
        patch("api.mcp_server.tools.save_workflow.authenticate_mcp_request", AsyncMock(return_value=user)),
        patch("api.mcp_server.tools.get_workflow_code.authenticate_mcp_request", AsyncMock(return_value=user)),
        patch("api.mcp_server.tools.save_workflow.db_client.get_workflow", AsyncMock(return_value=wf)),
        patch("api.mcp_server.tools.get_workflow_code.db_client.get_workflow", AsyncMock(return_value=wf)),
        patch("api.mcp_server.tools.save_workflow.db_client.get_draft_version", AsyncMock(return_value=draft)),
        patch("api.mcp_server.tools.save_workflow.db_client.save_workflow_draft", sauve),
        patch("api.mcp_server.tools.save_workflow.db_client.update_workflow", AsyncMock()),
    ):
        yield stocke, sauve


def _par_nom(payload, nom):
    return next(n for n in payload["nodes"] if n["data"].get("name") == nom)["data"]


def _liaison(payload, source, cible):
    return next(e for e in payload["edges"] if e["source"] == source and e["target"] == cible)


@pytest.mark.asyncio
async def test_aller_retour_garde_les_reglages_caches(banc):
    stocke, sauve = banc
    code = (await get_workflow_code(1))["code"]
    res = await save_workflow(1, code)
    assert res["saved"] is True, res
    ecrit = sauve.call_args.kwargs["workflow_definition"]
    etape = _par_nom(ecrit, "Rdv")
    for champ, valeur in CHAMPS_CACHES_ETAPE.items():
        assert etape.get(champ) == valeur, f"{champ} perdu par l'aller-retour"
    assert _par_nom(ecrit, "Autre").get("travail_de_fond") is True
    assert _par_nom(ecrit, "Fin").get("fins") == FINS
    assert _liaison(ecrit, "1", "2")["data"].get("condition_sur_la_fiche") == CONDITION_LIAISON


@pytest.mark.asyncio
async def test_une_etape_et_une_liaison_supprimees_restent_supprimees(banc):
    stocke, sauve = banc
    code = (await get_workflow_code(1))["code"]
    # On retire l'étape « Autre » et ses liaisons du code.
    code = re.sub(r"const autre = .*?\}\)\);\n", "", code, flags=re.S)
    code = re.sub(r"wf\.edge\((?:(?!wf\.edge).)*?label: \"(?:Autre|Fin bis)\"(?:(?!wf\.edge).)*?\}\);\n", "", code, flags=re.S)
    assert "autre" not in code
    res = await save_workflow(1, code)
    assert res["saved"] is True, res
    ecrit = sauve.call_args.kwargs["workflow_definition"]
    assert all(n["data"].get("name") != "Autre" for n in ecrit["nodes"])
    assert all(e["data"]["label"] not in ("Autre", "Fin bis") for e in ecrit["edges"])
    # L'étape gardée garde ses réglages cachés.
    assert _par_nom(ecrit, "Rdv").get("retour_au_principal") is True


@pytest.mark.asyncio
async def test_un_champ_visible_modifie_dans_le_code_l_emporte(banc):
    stocke, sauve = banc
    code = (await get_workflow_code(1))["code"]
    assert "Prends le rendez-vous" in code
    res = await save_workflow(1, code.replace("Prends le rendez-vous", "Nouveau texte"))
    assert res["saved"] is True, res
    etape = _par_nom(sauve.call_args.kwargs["workflow_definition"], "Rdv")
    assert etape["prompt"] == "Nouveau texte"
    assert etape.get("retour_au_principal") is True
