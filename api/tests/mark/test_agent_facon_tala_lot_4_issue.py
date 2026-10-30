"""[.mark] agent-facon-tala, lot 4 (C4) : l'issue d'appel métier à TOUTE fin d'appel.

Avant : l'issue métier (liste ``call_dispositions`` de l'agent) n'était posée que quand l'agent prenait sa fin ;
un raccrochage, une inactivité ou la fin du clavier gardait ``user_hangup``.

| Test | Ce qu'il prouve |
|---|---|
| pures | l'issue floue vient de la liste de l'agent, jamais inventée ; la fiche est lue ; rien si la personne n'a pas parlé |
| invite | le classement lit la fiche quand on la lui donne, et son invite est inchangée sans fiche |
| téléphone | un RACCROCHAGE (vrai moteur, vraie fin d'appel) prend l'issue du classement, l'issue floue quand rien n'est retenu, l'état mécanique si la liste n'a pas d'issue floue ou si personne n'a parlé |
| clavier | la fin du clavier (route ``/end``, vraie base) prend l'issue métier, et l'issue floue sinon |
"""

from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest
from pipecat.utils.enums import EndTaskReason

from api.schemas.workflow_configurations import CallDispositionOption
from api.services.workflow.disposition_extraction import DispositionExtractionService
from api.services.workflow.issue_de_fin import (
    ISSUE_FLOUE,
    issue_de_secours,
    issue_finale,
    texte_de_la_fiche,
)
from api.services.workflow.pipecat_engine_variable_extractor import VariableExtractionManager
from api.tests.pipecat_test_utils import run_engine_test_pipeline
from api.tests.test_pipecat_engine_end_call import (
    EndCallTestHelper,
    create_engine_with_tracking,
)
from pipecat.tests import MockLLMService


def _liste(*codes):
    return [CallDispositionOption(code=c, description=f"Issue {c}.") for c in codes]


# --------------------------------------------------------------------------- #
# Les fonctions pures
# --------------------------------------------------------------------------- #


def test_l_issue_floue_vient_de_la_liste_jamais_inventee():
    assert issue_de_secours(_liste("devis_a_rappeler", ISSUE_FLOUE)) == ISSUE_FLOUE
    assert issue_de_secours(_liste("devis_a_rappeler")) is None
    assert issue_de_secours([]) is None


def test_l_issue_retenue_l_emporte_et_sans_parole_rien():
    options = _liste("devis_a_rappeler", ISSUE_FLOUE)
    assert issue_finale(options, "devis_a_rappeler", a_parle=True) == "devis_a_rappeler"
    assert issue_finale(options, None, a_parle=True) == ISSUE_FLOUE
    assert issue_finale(options, None, a_parle=False) is None
    assert issue_finale(_liste("devis_a_rappeler"), None, a_parle=True) is None


def test_la_fiche_se_lit_en_lignes_et_sans_fiche_rien():
    assert texte_de_la_fiche(None, {"a": 1}) is None
    assert texte_de_la_fiche(SimpleNamespace(), None) is None
    assert texte_de_la_fiche(SimpleNamespace(), {"x": 1}) is None  # illisible : le classement se fait sans


def test_le_classement_lit_la_fiche_et_sans_fiche_l_invite_est_celle_d_avant():
    import json

    from pipecat.processors.aggregators.llm_context import LLMContext

    contexte = LLMContext()
    contexte.set_messages([{"role": "user", "content": "Bonjour"}])
    service = DispositionExtractionService(
        llm=object(), context=contexte, options=_liste("a"), template_context={}
    )
    sans = service._build_user_prompt()
    avec = service._build_user_prompt("projet = poêle ; nom = Faucheux")
    assert avec.startswith(sans)
    assert "projet = poêle ; nom = Faucheux" in avec
    assert "record noted" in avec and "record noted" not in sans
    assert service._build_user_prompt(None) == sans
    json.dumps(sans)  # l'invite est du texte simple


# --------------------------------------------------------------------------- #
# Le téléphone : un vrai raccrochage
# --------------------------------------------------------------------------- #


async def _raccrocher(simple_workflow, options, *, retenue, a_parle=True):
    """Un appel au vrai moteur qui se termine par un raccrochage ; rend le contexte final et l'appel au
    classement."""
    aide = EndCallTestHelper()
    llm = MockLLMService(mock_steps=[MockLLMService.create_text_chunks("Bonjour !")], chunk_delay=0.001)
    engine, _tts, transport, task = await create_engine_with_tracking(
        simple_workflow, llm, aide, call_dispositions=options
    )

    async def raccrocher():
        await engine.set_node(engine.active_agent.workflow.start_node_id)
        if a_parle:
            engine.context.add_message({"role": "user", "content": "Je veux un devis."})
        await engine.end_call_with_reason(EndTaskReason.USER_HANGUP.value, abort_immediately=True)

    with (
        patch(
            "api.db:db_client.get_organization_id_by_workflow_run_id",
            new_callable=AsyncMock,
            return_value=1,
        ),
        patch("api.db:db_client.update_workflow_run", new_callable=AsyncMock),
        patch.object(
            VariableExtractionManager, "_perform_extraction", new_callable=AsyncMock, return_value={}
        ),
        patch.object(
            DispositionExtractionService, "extract", new_callable=AsyncMock, return_value=retenue
        ) as classement,
    ):
        await run_engine_test_pipeline(task, engine, transport, on_ready=raccrocher)
    return await engine.get_gathered_context(), classement


@pytest.mark.asyncio
async def test_un_raccrochage_prend_l_issue_retenue_par_le_classement(simple_workflow):
    contexte, classement = await _raccrocher(
        simple_workflow, _liste("devis_a_rappeler", ISSUE_FLOUE), retenue="devis_a_rappeler"
    )
    assert contexte["call_status"] == EndTaskReason.USER_HANGUP.value
    assert contexte["call_disposition"] == "devis_a_rappeler"
    assert contexte["mapped_call_disposition"] == "devis_a_rappeler"
    classement.assert_awaited_once()
    assert "fiche" in classement.await_args.kwargs  # la fiche est donnée au classement


@pytest.mark.asyncio
async def test_un_raccrochage_sans_motif_clair_prend_l_issue_floue_de_la_liste(simple_workflow):
    contexte, _ = await _raccrocher(
        simple_workflow, _liste("devis_a_rappeler", ISSUE_FLOUE), retenue=None
    )
    assert contexte["call_status"] == EndTaskReason.USER_HANGUP.value  # le mécanisme reste dit
    assert contexte["call_disposition"] == ISSUE_FLOUE
    assert contexte["mapped_call_disposition"] == ISSUE_FLOUE
    assert ISSUE_FLOUE in contexte["call_tags"]


@pytest.mark.asyncio
async def test_une_liste_sans_issue_floue_garde_l_etat_d_avant(simple_workflow):
    contexte, _ = await _raccrocher(simple_workflow, _liste("devis_a_rappeler"), retenue=None)
    assert contexte["call_disposition"] == EndTaskReason.USER_HANGUP.value


@pytest.mark.asyncio
async def test_personne_n_a_parle_aucune_issue_n_est_inventee(simple_workflow):
    contexte, _ = await _raccrocher(
        simple_workflow, _liste("devis_a_rappeler", ISSUE_FLOUE), retenue=None, a_parle=False
    )
    assert contexte["call_disposition"] == EndTaskReason.USER_HANGUP.value


# --------------------------------------------------------------------------- #
# Le clavier : la vraie route de fin de session
# --------------------------------------------------------------------------- #

ISSUES_DU_CLAVIER = [
    {"code": "devis_a_rappeler", "description": "La personne veut un devis."},
    {"code": ISSUE_FLOUE, "description": "Le motif n'est pas clair."},
]


async def _terminer_le_clavier(db_session, async_session, test_client_factory, issues, *, retenue):
    from api.tests.mark.test_passation_clavier import _dit, _groupe, _texte, _vide

    user, principal, _specialise = await _groupe(
        db_session, async_session, reglages_principal={"call_dispositions": issues}
    )
    async with test_client_factory(user) as client:
        with (
            patch(
                "api.services.workflow.text_chat_runner.create_llm_service",
                side_effect=[_vide(), _dit(_texte("Oui, je vous écoute.")), _vide()],
            ),
            patch(
                "api.services.workflow.text_chat_runner.db_client.has_active_recordings",
                new=AsyncMock(return_value=False),
            ),
        ):
            creee = (await client.post(f"/api/v1/workflow/{principal.id}/text-chat/sessions", json={})).json()
            tour = await client.post(
                f"/api/v1/workflow/{principal.id}/text-chat/sessions/{creee['workflow_run_id']}/messages",
                json={"text": "Je voudrais un devis.", "expected_revision": creee["revision"]},
            )
            assert tour.status_code == 200, tour.text
        with (
            patch(
                "api.services.workflow.text_chat_session_service.extract_text_chat_final_variables",
                new=AsyncMock(return_value={}),
            ),
            patch("api.services.workflow.text_chat_runner.create_llm_service"),
            patch.object(
                DispositionExtractionService,
                "extract",
                new_callable=AsyncMock,
                return_value=retenue,
            ) as classement,
            patch("api.tasks.arq.enqueue_job", AsyncMock()),
        ):
            fin = await client.post(
                f"/api/v1/workflow/{principal.id}/text-chat/sessions/{creee['workflow_run_id']}/end",
                json={"expected_revision": tour.json()["revision"]},
            )
    assert fin.status_code == 200, fin.text
    return fin.json()["gathered_context"], classement


@pytest.mark.asyncio
async def test_la_fin_du_clavier_prend_l_issue_metier(db_session, async_session, test_client_factory):
    contexte, classement = await _terminer_le_clavier(
        db_session, async_session, test_client_factory, ISSUES_DU_CLAVIER, retenue="devis_a_rappeler"
    )
    assert contexte["call_status"] == EndTaskReason.USER_HANGUP.value  # le mécanisme reste dit
    assert contexte["call_disposition"] == "devis_a_rappeler"
    assert contexte["mapped_call_disposition"] == "devis_a_rappeler"
    assert "devis_a_rappeler" in contexte["call_tags"]
    classement.assert_awaited_once()


@pytest.mark.asyncio
async def test_la_fin_du_clavier_sans_motif_clair_prend_l_issue_floue(
    db_session, async_session, test_client_factory
):
    contexte, _ = await _terminer_le_clavier(
        db_session, async_session, test_client_factory, ISSUES_DU_CLAVIER, retenue=None
    )
    assert contexte["call_disposition"] == ISSUE_FLOUE
    assert contexte["call_status"] == EndTaskReason.USER_HANGUP.value


@pytest.mark.asyncio
async def test_la_fin_du_clavier_sans_liste_d_issues_garde_l_etat_d_avant(
    db_session, async_session, test_client_factory
):
    contexte, classement = await _terminer_le_clavier(
        db_session, async_session, test_client_factory, [], retenue="devis_a_rappeler"
    )
    assert contexte["call_disposition"] == EndTaskReason.USER_HANGUP.value
    classement.assert_not_awaited()
