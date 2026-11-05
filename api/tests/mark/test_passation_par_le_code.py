"""[.mark] Builder partie 3, lot P (P3) : une passe de moins, la passation prise par le code à l'arrivée (réglage d'étape
``passation_par_le_code``, éteint par défaut).

Le vrai moteur, le vrai coordinateur et les vrais gestionnaires d'outils (le pipeline fendu de ``TransferHarness``) ;
seuls les modèles, la voix et la base sont remplacés. L'accueil a deux étapes : « Accueil » (départ) et « Rendez-vous »,
qui porte l'outil de passation vers le collègue ; une porte mène de l'une à l'autre (prise sur la fiche par le code,
ou écrite par l'agent).

| Groupe | Ce qu'il prouve |
|---|---|
| allumé | à l'arrivée sur l'étape, le code passe la main tout de suite : annonce de l'outil, collègue installé, aucune requête de plus au modèle de l'accueil |
| éteint (défaut) | comportement d'avant : le modèle de l'accueil est relancé dans l'étape, aucune passation n'est lancée par le code |
| garde-fous | deux outils de passation dans l'étape, ou une passation refusée (plafond, renvoi immédiat) : le code ne choisit pas, le modèle reparle |
| schéma | éteint = rien n'est écrit dans le JSON de l'agent ; le réglage vit dans la section « Passage » de l'étape |
"""

import asyncio
from unittest.mock import AsyncMock, patch

import pytest
from pipecat.tests import MockLLMService

from api.services.workflow.dto import (
    AgentNodeData,
    EdgeDataDTO,
    EndCallNodeData,
    Position,
    ReactFlowDTO,
    RFEdgeDTO,
    RFNodeDTO,
    StartCallNodeData,
)
from api.services.workflow.pipecat_engine_custom_tools import CustomToolManager
from api.services.workflow.workflow_graph import WorkflowGraph
from api.tests.mark.banc_voix import brancher_la_parole_locale, voix_de_l_appel
from api.tests.mark.test_passation_rapide_groupe import GROUPE, PATCH_OUTILS, _sonnerie
from api.tests.test_agent_transfer import (
    DESTINATION_WORKFLOW_ID,
    TRANSFER_TOOL_UUID,
    TransferAgentTool,
    TransferHarness,
    build_agent_workflow,
)

ANNONCE = "Je vous passe ma collègue des rendez-vous."


def _accueil(
    *, par_le_code: bool | None, outils: list[str] | None = None
) -> WorkflowGraph:
    commun = {
        "allow_interrupt": True,
        "add_global_prompt": False,
        "extraction_enabled": False,
    }
    return WorkflowGraph(
        ReactFlowDTO(
            nodes=[
                RFNodeDTO(
                    id="start",
                    type="startCall",
                    position=Position(x=0, y=0),
                    data=StartCallNodeData(
                        name="Accueil",
                        prompt="Tu accueilles.",
                        is_start=True,
                        greeting=None,
                        **commun,
                    ),
                ),
                RFNodeDTO(
                    id="rdv",
                    type="agentNode",
                    position=Position(x=0, y=100),
                    data=AgentNodeData(
                        name="Rendez-vous",
                        prompt="Tu passes la main au collègue des rendez-vous.",
                        tool_uuids=outils
                        if outils is not None
                        else [TRANSFER_TOOL_UUID],
                        passation_par_le_code=par_le_code,
                        **commun,
                    ),
                ),
                RFNodeDTO(
                    id="end",
                    type="endCall",
                    position=Position(x=0, y=200),
                    data=EndCallNodeData(
                        name="Fin", prompt="Au revoir.", is_end=True, **commun
                    ),
                ),
            ],
            edges=[
                RFEdgeDTO(
                    id="start-rdv",
                    source="start",
                    target="rdv",
                    data=EdgeDataDTO(
                        label="Vers rendez-vous", condition="Il veut un rendez-vous."
                    ),
                ),
                RFEdgeDTO(
                    id="rdv-end",
                    source="rdv",
                    target="end",
                    data=EdgeDataDTO(label="Fin", condition="Fini."),
                ),
            ],
        )
    )


async def _monter(*, par_le_code: bool | None, outils: list[str] | None = None):
    harness = TransferHarness()
    accueil_llm = MockLLMService(mock_steps=[], chunk_delay=0.001)
    with voix_de_l_appel() as banc:
        await harness.build(
            source_llm=accueil_llm,
            destination_llm=MockLLMService(
                mock_steps=[
                    MockLLMService.create_text_chunks(
                        "Bonjour, je prends votre rendez-vous."
                    )
                ],
                chunk_delay=0.001,
            ),
            source_workflow=_accueil(par_le_code=par_le_code, outils=outils),
            destination_workflow=build_agent_workflow(name="Specialise", greeting=None),
        )
    brancher_la_parole_locale(harness, banc)
    engine = harness.engine
    engine.reglages_appel = dict(GROUPE)
    engine.active_agent.reglages = dict(GROUPE)
    engine._get_organization_id = AsyncMock(return_value=1)
    await harness.start()
    return harness, banc, accueil_llm


async def _arriver_sur_l_etape(harness, outils):
    """L'accueil est sur « Accueil » ; la porte vers « Rendez-vous » est prise par le code (passage sur la fiche)."""
    engine = harness.engine
    with patch(PATCH_OUTILS, AsyncMock(return_value=outils)):
        engine.lire_outils = AsyncMock(return_value=outils)
        engine._custom_tool_manager = CustomToolManager(engine)
        await engine.set_node("start")
        relances: list = []
        mettre = engine.active_agent.queue_frame

        async def noter(frame, *args, **kwargs):
            if type(frame).__name__ == "LLMRunFrame":
                relances.append(frame)
            return await mettre(frame, *args, **kwargs)

        engine.active_agent.queue_frame = noter
        porte = engine.active_agent.current_node.out_edges[0].get_function_name()
        etat = await engine.prendre_porte_ecrite(
            porte, relancer=True, choisie_par_le_code=True
        )
        coordinateur = engine.transfer_coordinator
        if coordinateur._task is not None:
            await asyncio.wait_for(coordinateur._task, 20)
        await asyncio.sleep(0.2)
    return etat, relances


@pytest.mark.asyncio
async def test_allume_le_code_passe_la_main_a_l_arrivee_sans_relancer_l_accueil(
    monkeypatch,
):
    _sonnerie(monkeypatch)
    harness, banc, _llm = await _monter(par_le_code=True)
    engine = harness.engine
    accueil = engine.active_agent
    try:
        etat, relances = await _arriver_sur_l_etape(
            harness, [TransferAgentTool(message=ANNONCE)]
        )
        assert etat == "prise"
        [issue] = engine.transfer_coordinator.completed
        assert (
            issue["outcome"] == "completed"
            and issue["destination_workflow_id"] == DESTINATION_WORKFLOW_ID
        )
        assert engine.active_agent is not accueil
        # Aucune requête de plus au modèle de l'accueil ; l'annonce de l'outil est dite, une fois.
        assert relances == []
        assert banc.voix.received_texts.count(ANNONCE) == 1
        passations = engine._gathered_context.get("passations") or []
        assert any(p.get("raison") == "Transfer to Billing" for p in passations)
    finally:
        await harness.stop()


@pytest.mark.asyncio
@pytest.mark.parametrize("reglage", [None, False], ids=["absent", "éteint"])
async def test_eteint_le_modele_de_l_accueil_reparle_comme_avant(monkeypatch, reglage):
    _sonnerie(monkeypatch)
    harness, _banc, _llm = await _monter(par_le_code=reglage)
    engine = harness.engine
    try:
        etat, relances = await _arriver_sur_l_etape(
            harness, [TransferAgentTool(message=ANNONCE)]
        )
        assert etat == "prise"
        assert engine.transfer_coordinator.completed == []
        assert len(relances) == 1, (
            "le modèle de l'accueil doit être relancé dans l'étape"
        )
    finally:
        await harness.stop()


@pytest.mark.asyncio
async def test_deux_outils_de_passation_le_code_ne_choisit_pas(monkeypatch):
    _sonnerie(monkeypatch)
    second = TransferAgentTool(message=ANNONCE)
    second.tool_uuid = "tool-transfer-agent-2"
    second.name = "Transfer to Support"
    harness, _banc, _llm = await _monter(
        par_le_code=True, outils=[TRANSFER_TOOL_UUID, second.tool_uuid]
    )
    engine = harness.engine
    try:
        etat, relances = await _arriver_sur_l_etape(
            harness, [TransferAgentTool(message=ANNONCE), second]
        )
        assert etat == "prise"
        assert engine.transfer_coordinator.completed == []
        assert len(relances) == 1
    finally:
        await harness.stop()


@pytest.mark.asyncio
async def test_une_passation_refusee_laisse_le_modele_reparler(monkeypatch):
    _sonnerie(monkeypatch)
    harness, _banc, _llm = await _monter(par_le_code=True)
    engine = harness.engine
    # Plafond du groupe atteint : la passation est refusée (tracée), l'accueil garde la main et reparle.
    engine.reglages_appel = {**GROUPE, "plafond_passations": 0}
    monkeypatch.setattr(
        "api.services.workflow.pipecat_engine_custom_tools.refus_de_passation",
        lambda *a, **k: "plafond",
    )
    try:
        etat, relances = await _arriver_sur_l_etape(
            harness, [TransferAgentTool(message=ANNONCE)]
        )
        assert etat == "prise"
        assert engine.transfer_coordinator.completed == []
        assert len(relances) == 1
    finally:
        await harness.stop()


def test_le_schema_n_ecrit_rien_quand_c_est_eteint_et_range_le_reglage_dans_passage():
    from api.services.workflow.dto import _sanitize_node

    for valeur in (None, False, ""):
        noeud = {
            "id": "n",
            "type": "agentNode",
            "data": {"name": "E", "passation_par_le_code": valeur},
        }
        assert "passation_par_le_code" not in _sanitize_node(noeud)["data"]
    allume = {
        "id": "n",
        "type": "agentNode",
        "data": {"name": "E", "passation_par_le_code": True},
    }
    assert _sanitize_node(allume)["data"]["passation_par_le_code"] is True
    assert AgentNodeData.model_fields["passation_par_le_code"].default is None
