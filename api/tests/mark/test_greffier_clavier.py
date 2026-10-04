"""[.mark] Le greffier au clavier (plan mode-prise-de-notes, partie 2, lot 12).

Règle C8 (correctifs-banc-34) : le clavier construit l'appel comme le téléphone. En mode greffier,
le même déclencheur est placé juste après le modèle de l'agent, et le tour attend la passe du
greffier (bornée) pour que la fiche du tour la contienne.

Par les VRAIES routes HTTP du clavier ; seuls les modèles (agent et greffier, réponses écrites
d'avance) sont remplacés.

| Test | Ce qu'il prouve |
|---|---|
| fiche | la passe du greffier remplit la fiche du tour, source `greffier`, trace « ecrit » |
| agent | l'agent dit sa phrase telle quelle et n'a pas l'outil de note |
| estampille | le run dit le mode joué et le modèle du greffier, jamais sa clé |
| repli | un greffier impossible à construire : le clavier joue le mode outil, estampillé tel |
"""

import json
from unittest.mock import patch

import pytest

from api.services.pipecat import greffier as module
from api.services.pipecat.greffier import CLE_ESTAMPILLE, ECRIT, TRACE_GREFFIER
from api.services.workflow.fiche_au_fil_de_leau import (
    CLE_JOURNAL,
    CLE_MODE,
    MODE_GREFFIER,
    MODE_OUTIL,
    brancher_noter_information,
)
from api.tests.mark.test_clavier_porte_la_fiche import FICHE, _converser, _monter
from api.tests.mark.test_greffier import _Modele
from pipecat.tests import MockLLMService

GREFFIER = {
    **FICHE,
    CLE_MODE: MODE_GREFFIER,
    "greffier_llm": {"api_key": "cle-propre-au-greffier-de-test"},
}
ESTAMPILLE = {"provider": "mistral", "model": "mistral-large-2512"}


@pytest.mark.asyncio
async def test_au_clavier_le_greffier_remplit_la_fiche(
    db_session, async_session, test_client_factory
):
    modele = _Modele({"nom": "Lemaire"})
    user, workflow = await _monter(db_session, async_session, GREFFIER)
    with patch.object(module, "service_du_greffier", return_value=(modele, ESTAMPILLE)):
        charge, run_id = await _converser(
            test_client_factory,
            user,
            workflow,
            [MockLLMService.create_text_chunks("Merci, que puis-je faire pour vous ?")],
            "je m'appelle Lemaire",
        )
    fiche = charge["checkpoint"]["gathered_context"]
    assert fiche.get("nom") == "Lemaire", fiche
    assert any(
        e.get("champ") == "nom" and e.get("source") == MODE_GREFFIER
        for e in fiche.get(CLE_JOURNAL) or []
    ), fiche.get(CLE_JOURNAL)
    assert [t["etat"] for t in fiche.get(TRACE_GREFFIER) or []][-1] == ECRIT
    assert any("je m'appelle Lemaire" in lu for lu in modele.lus)
    run = await db_session.get_workflow_run_by_id(run_id)
    assert (run.gathered_context or {}).get("nom") == "Lemaire", run.gathered_context
    runtime = run.initial_context["runtime_configuration"]
    assert runtime[CLE_MODE] == MODE_GREFFIER
    assert runtime[CLE_ESTAMPILLE] == ESTAMPILLE
    assert "cle-propre-au-greffier" not in json.dumps(run.initial_context)


@pytest.mark.asyncio
async def test_au_clavier_l_agent_parle_sans_l_outil_de_note(
    db_session, async_session, test_client_factory
):
    user, workflow = await _monter(db_session, async_session, GREFFIER)
    agent = MockLLMService.create_text_chunks("Merci, que puis-je faire pour vous ?")
    with (
        patch.object(
            module, "service_du_greffier", return_value=(_Modele({}), ESTAMPILLE)
        ),
        patch(
            "api.services.workflow.pipecat_engine.brancher_noter_information",
            wraps=brancher_noter_information,
        ) as outil,
    ):
        charge, _ = await _converser(
            test_client_factory, user, workflow, [agent], "je m'appelle Lemaire"
        )
    outil.assert_not_called()
    assert "Merci, que puis-je faire pour vous ?" in json.dumps(
        charge, ensure_ascii=False
    )


@pytest.mark.asyncio
async def test_au_clavier_un_greffier_impossible_joue_le_mode_outil(
    db_session, async_session, test_client_factory
):
    user, workflow = await _monter(db_session, async_session, GREFFIER)
    with (
        patch.object(module, "service_du_greffier", side_effect=ValueError("panne")),
        patch(
            "api.services.workflow.pipecat_engine.brancher_noter_information",
            wraps=brancher_noter_information,
        ) as outil,
    ):
        charge, run_id = await _converser(
            test_client_factory,
            user,
            workflow,
            [MockLLMService.create_text_chunks("Merci.")],
            "je m'appelle Lemaire",
        )
    run = await db_session.get_workflow_run_by_id(run_id)
    runtime = run.initial_context["runtime_configuration"]
    assert runtime[CLE_MODE] == MODE_OUTIL
    assert CLE_ESTAMPILLE not in runtime
    assert TRACE_GREFFIER not in charge["checkpoint"]["gathered_context"]
    outil.assert_called()  # le mode outil rend l'outil de note à l'agent
