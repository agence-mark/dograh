"""[.mark] La trace du cerveau suit chaque agent de l'appel (fiabilite-orchestration, lot 8, R12).

Au 1464, la trace n'était branchée que sur le service du PREMIER agent : après la passation, le
collègue parlait sans trace, et les coupures du tour n'étaient pas explicables. Désormais la
trace est UNE par appel (celle du moteur) et se branche sur le service de chaque agent construit
à la passation et du cerveau de fond, case de CET agent allumée ; chaque entrée porte le nom.

| Test | Ce qu'il prouve |
|---|---|
| passation (R1) | par la vraie fabrique d'agents : l'accueil puis le collègue tracent, chacun sous son nom, dans la même liste |
| case du collègue éteinte | son service n'est pas tracé, celui de l'accueil l'est toujours |
| case de l'accueil éteinte | le collègue allumé trace quand même (la trace naît à sa construction) |
| sans nom | une entrée sans nom est celle d'avant, à l'octet |
| cerveau de fond (R1) | par la vraie préparation du fond : son service trace sous « <agent> (fond) » |
| fond éteint | case éteinte : le fond n'est pas tracé |
"""

from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest

from api.services.pipecat import agent_runtime_factory as fabrique_agents
from api.services.pipecat.trace_modele import (
    ATTRIBUT_TRACE,
    CLE_TRACE_REQUETES,
    TRACE_REQUETES,
    brancher_la_trace,
)
from api.services.travail.agent import preparer_le_travail
from api.tests.mark.test_agent_transfere_reglages_mark import (
    REGLAGES,
    WORKFLOW_ID,
    _configuration,
    _fabrique,
)
from api.tests.mark.test_trace_modele import _contexte, _service
from api.tests.mark.test_traversants_appel import DEFINITION


async def _construire_collegue(fabrique, services, reglages):
    workflow = SimpleNamespace(id=WORKFLOW_ID, name="Collègue")
    definition = SimpleNamespace(
        id=7,
        workflow_json=DEFINITION,
        workflow_configurations={**REGLAGES, **reglages},
        version_number=1,
        status="published",
    )
    with (
        patch.object(
            fabrique, "resolve_destination", AsyncMock(return_value=(workflow, definition))
        ),
        patch(
            "api.services.configuration.ai_model_configuration."
            "get_effective_ai_model_configuration_for_workflow",
            AsyncMock(return_value=_configuration()),
        ),
        patch.object(fabrique_agents, "create_llm_service", lambda *a, **k: services.pop(0)),
        patch.object(fabrique, "attach", AsyncMock()),
    ):
        return await fabrique.build(workflow_id=WORKFLOW_ID)


async def _repondre(service):
    flux = await service.get_chat_completions(_contexte())
    async for _ in flux:
        pass


@pytest.mark.asyncio
async def test_la_passation_trace_l_accueil_puis_le_collegue_chacun_sous_son_nom():
    fiche: dict = {}
    moteur = SimpleNamespace(_gathered_context=fiche)
    accueil, _ = _service()
    collegue, _ = _service()
    assert brancher_la_trace(moteur, accueil, {CLE_TRACE_REQUETES: True}, "Accueil")

    fabrique = _fabrique()
    fabrique._moteur_de_l_appel = lambda: moteur
    agent = await _construire_collegue(fabrique, [collegue], {CLE_TRACE_REQUETES: True})
    assert agent.llm is collegue

    await _repondre(accueil)
    await _repondre(collegue)
    entrees = fiche[TRACE_REQUETES]
    assert [e["agent"] for e in entrees] == ["Accueil", "Collègue"]
    assert all(e["fin"] == "complet" and e["morceaux"] for e in entrees)
    assert collegue.mark_trace is getattr(moteur, ATTRIBUT_TRACE)


@pytest.mark.asyncio
async def test_la_case_eteinte_du_collegue_laisse_son_service_sans_trace():
    fiche: dict = {}
    moteur = SimpleNamespace(_gathered_context=fiche)
    accueil, _ = _service()
    collegue, _ = _service()
    brancher_la_trace(moteur, accueil, {CLE_TRACE_REQUETES: True}, "Accueil")
    fabrique = _fabrique()
    fabrique._moteur_de_l_appel = lambda: moteur
    await _construire_collegue(fabrique, [collegue], {})

    assert collegue.mark_trace is None
    await _repondre(collegue)
    await _repondre(accueil)
    assert [e["agent"] for e in fiche[TRACE_REQUETES]] == ["Accueil"]


@pytest.mark.asyncio
async def test_le_collegue_allume_trace_meme_si_l_accueil_ne_l_etait_pas():
    fiche: dict = {}
    moteur = SimpleNamespace(_gathered_context=fiche)
    collegue, _ = _service()
    fabrique = _fabrique()
    fabrique._moteur_de_l_appel = lambda: moteur
    await _construire_collegue(fabrique, [collegue], {CLE_TRACE_REQUETES: True})
    await _repondre(collegue)
    [entree] = fiche[TRACE_REQUETES]
    assert entree["agent"] == "Collègue"


@pytest.mark.asyncio
async def test_sans_nom_l_entree_est_celle_d_avant():
    fiche: dict = {}
    service, _ = _service()
    brancher_la_trace(SimpleNamespace(_gathered_context=fiche), service, {CLE_TRACE_REQUETES: True})
    await _repondre(service)
    assert "agent" not in fiche[TRACE_REQUETES][0]


async def _fond(reglages_agent):
    fiche: dict = {}
    moteur = SimpleNamespace(
        _gathered_context=fiche,
        travaux=[],
        _get_organization_id=AsyncMock(return_value=1),
        _agent_factory=None,
        sans_sortie_audio=False,
    )
    service, _ = _service()
    agent = SimpleNamespace(
        reglages=reglages_agent,
        workflow_name="Accueil",
        visit_id="v1",
        travail=None,
        user_config=SimpleNamespace(),
        runtime_configuration={},
    )

    async def preparation(run_configs, *a, **k):
        from api.services.travail.reglages import ReglagesTravail

        return ReglagesTravail.depuis(run_configs), service

    gardes = AsyncMock()
    with (
        patch("api.services.travail.agent.preparer_le_service_du_travail", preparation),
        patch("api.services.travail.agent.TravailDeLAgent", lambda **k: SimpleNamespace(
            worker=SimpleNamespace(context=None), **k)),
        patch("api.services.panne.garde_modele.garder_le_fond", gardes),
    ):
        travail = await preparer_le_travail(moteur, agent)
    return fiche, service, travail


@pytest.mark.asyncio
async def test_le_cerveau_de_fond_trace_sous_le_nom_de_son_agent():
    fiche, service, travail = await _fond({"travail_actif": True, CLE_TRACE_REQUETES: True})
    assert travail is not None
    await _repondre(service)
    [entree] = fiche[TRACE_REQUETES]
    assert entree["agent"] == "Accueil (fond)" and entree["morceaux"]


@pytest.mark.asyncio
async def test_le_fond_case_eteinte_n_est_pas_trace():
    fiche, service, travail = await _fond({"travail_actif": True})
    assert travail is not None and service.mark_trace is None
    await _repondre(service)
    assert TRACE_REQUETES not in fiche
