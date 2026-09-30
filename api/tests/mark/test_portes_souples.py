"""[.mark] Les portes rendues au modèle : une porte prise est prise, quoi que tienne la fiche.

Chantier souplesse-portes (30/09/2026), décision S1 d'Evan, plan
`Labo-agent-vocal/plans/souplesse-portes/`. Le verrou « champs exigés sur une flèche » (C6, 29/09)
refusait une porte tant que la fiche ne tenait pas certains champs dans un certain état : le
parcours dépendait des modules de lecture (au run 906, un nom dit puis épelé n'était jamais
« épelé » et la porte redemandait l'épellation). Il est retiré en bloc : la fiche garde la
donnée, le modèle décide des portes.

Ces tests passent par les VRAIES routes HTTP du clavier, sur la base de test ; seul le modèle
(réponses écrites d'avance) est remplacé. Le premier et le troisième sont rouges sur `24936470`
(la porte y est refusée).

| Test | Ce qu'il prouve |
|---|---|
| run 906 | nom dit, puis épelé à la réplique suivante, puis la porte : elle est prise, la fiche garde le nom |
| fiche vide | une porte prise sans rien noter est prise |
| donnée ancienne | un agent enregistré avec `champs_requis` sur une flèche se charge sans erreur, la porte est prise |
"""

import copy
import uuid
from unittest.mock import AsyncMock, patch

import pytest

from api.tests.mark.test_clavier_porte_la_fiche import DEFINITION, _monter
from pipecat.tests import MockLLMService

PORTE = "nom_numero_et_adresse_notes"
NOM = {"nom": "nom", "origine": "dicte", "description": "Nom de famille"}
FICHE = {"fiche_au_fil_de_leau": True, "fiche_champs": [NOM]}


def _definition(champs_requis=None):
    """La définition du clavier, sa flèche nommée comme celle du n° 34 ; ``champs_requis``
    posé tel quel dans ses données, comme un agent enregistré avant le retrait."""
    definition = copy.deepcopy(DEFINITION)
    donnees = definition["edges"][0]["data"]
    donnees["label"] = PORTE
    if champs_requis is not None:
        donnees["champs_requis"] = champs_requis
    return definition


async def _messages(test_client_factory, user, workflow, tours):
    """Plusieurs messages de la personne ; chaque tour construit son modèle (clavier C8)."""
    llm = [MockLLMService(mock_steps=[], chunk_delay=0.001)]  # accueil (texte fixe)
    llm += [MockLLMService(mock_steps=repliques, chunk_delay=0.001) for _, repliques in tours]
    llm += [MockLLMService(mock_steps=[], chunk_delay=0.001) for _ in range(3)]
    async with test_client_factory(user) as client:
        with (
            patch("api.services.workflow.text_chat_runner.create_llm_service", side_effect=llm),
            patch(
                "api.services.workflow.text_chat_runner.db_client.has_active_recordings",
                new=AsyncMock(return_value=False),
            ),
        ):
            creee = await client.post(f"/api/v1/workflow/{workflow.id}/text-chat/sessions", json={})
            assert creee.status_code == 200, creee.text
            session = creee.json()
            revision, charge = session["revision"], None
            for message, _ in tours:
                reponse = await client.post(
                    f"/api/v1/workflow/{workflow.id}/text-chat/sessions/"
                    f"{session['workflow_run_id']}/messages",
                    json={"text": message, "expected_revision": revision},
                )
                assert reponse.status_code == 200, reponse.text
                charge = reponse.json()
                revision = charge["revision"]
            return charge


def _porte(tool_call_id: str):
    return MockLLMService.create_function_call_chunks(PORTE, {}, tool_call_id=tool_call_id)


@pytest.mark.asyncio
async def test_run_906_nom_dit_puis_epele_la_porte_est_prise(
    db_session, async_session, test_client_factory
):
    user, workflow = await _monter(db_session, async_session, FICHE, _definition(["nom"]))
    appel = uuid.uuid4().hex[:6]
    charge = await _messages(
        test_client_factory,
        user,
        workflow,
        [
            (
                "je m'appelle Chevalier",
                [
                    MockLLMService.create_function_call_chunks(
                        "noter_information", {"nom": "Chevalier"}, tool_call_id=f"note_{appel}_1"
                    ),
                    MockLLMService.create_text_chunks("Pouvez-vous me l'épeler ?"),
                ],
            ),
            (
                "c h e v a l i e r",
                [
                    MockLLMService.create_multiple_function_call_chunks(
                        [
                            {
                                "name": "noter_information",
                                "arguments": {"nom": "Chevalier"},
                                "tool_call_id": f"note_{appel}_2",
                            },
                            {"name": PORTE, "arguments": {}, "tool_call_id": f"porte_{appel}"},
                        ]
                    ),
                    MockLLMService.create_text_chunks("Merci, au revoir."),
                ],
            ),
        ],
    )
    assert charge["checkpoint"]["current_node_id"] == "end", charge["checkpoint"]
    contexte = charge["checkpoint"]["gathered_context"]
    assert contexte.get("nom") == "Chevalier", contexte


@pytest.mark.asyncio
async def test_une_porte_prise_sans_rien_noter_est_prise(
    db_session, async_session, test_client_factory
):
    user, workflow = await _monter(db_session, async_session, FICHE, _definition())
    charge = await _messages(
        test_client_factory,
        user,
        workflow,
        [("c'est tout pour moi", [_porte(f"porte_{uuid.uuid4().hex[:6]}"), MockLLMService.create_text_chunks("Au revoir.")])],
    )
    assert charge["checkpoint"]["current_node_id"] == "end", charge["checkpoint"]


@pytest.mark.asyncio
async def test_un_agent_enregistre_avec_champs_requis_se_charge_et_la_porte_est_prise(
    db_session, async_session, test_client_factory
):
    user, workflow = await _monter(db_session, async_session, FICHE, _definition(["nom"]))
    charge = await _messages(
        test_client_factory,
        user,
        workflow,
        [("c'est tout pour moi", [_porte(f"porte_{uuid.uuid4().hex[:6]}"), MockLLMService.create_text_chunks("Au revoir.")])],
    )
    assert charge["checkpoint"]["current_node_id"] == "end", charge["checkpoint"]
