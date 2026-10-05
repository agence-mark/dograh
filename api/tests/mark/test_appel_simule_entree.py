"""[.mark] L'entrée audio des appels simulés (chantier langwatch-et-fenetre-du-run, lot 3, L8, L9, L19).

Ce que la route doit garantir, avant tout pipeline : un jeton faux, absent ou celui d'un autre run est
refusé ; un run déjà joué est refusé (usage unique) ; le flux doit suivre le protocole Twilio
(``connected`` puis ``start``). Le bon jeton passe le run à « running » et joue le pipeline de
l'organisation du run. Et un appel simulé ne compose jamais de vrai numéro (renvoi en mode d'essai),
ni ne compte de téléphonie dans son coût.
"""

from __future__ import annotations

import json
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from starlette.websockets import WebSocketDisconnect

from api.enums import WorkflowRunMode, WorkflowRunState
from api.routes import appel_simule as route
from api.services.analyse_run.analyse import analyser_run
from api.services.analyse_run.cout import CANAUX_SANS_TELEPHONIE
from api.services.appel_simule import pipeline
from api.services.appel_simule.entree import (
    CLE_EXTRA,
    adresse_ws,
    empreinte,
    jeton_valide,
    run_branchable,
)
from api.services.pipecat.audio_config import create_audio_config
from api.services.workflow.renvoi_en_test import MODES_DE_TEST

JETON = "jeton-du-run-12"
ORGANISATION = 7


def _run(
    run_id=12,
    *,
    jeton=JETON,
    mode=WorkflowRunMode.SIMULATED.value,
    state=WorkflowRunState.INITIALIZED.value,
):
    return SimpleNamespace(
        id=run_id,
        workflow_id=34,
        mode=mode,
        state=state,
        extra={CLE_EXTRA: {"serie": 1, "jeton_sha256": empreinte(jeton)}},
        workflow=SimpleNamespace(organization_id=ORGANISATION, user_id=3),
    )


# --- Le jeton et l'usage unique ---------------------------------------------------------------


def test_seul_le_jeton_du_run_est_valide():
    run = _run()
    assert jeton_valide(run, JETON)
    assert not jeton_valide(run, "un-autre-jeton")
    assert not jeton_valide(run, "")
    assert not jeton_valide(run, None)
    assert not jeton_valide(SimpleNamespace(extra={}), JETON)
    assert not jeton_valide(SimpleNamespace(extra=None), JETON)


def test_l_empreinte_seule_est_rangee_jamais_le_jeton():
    rangee = _run().extra[CLE_EXTRA]
    assert JETON not in json.dumps(rangee)
    assert rangee["jeton_sha256"] == empreinte(JETON)


def test_seul_un_run_simule_pas_encore_joue_est_branchable():
    assert run_branchable(_run())
    assert not run_branchable(_run(state=WorkflowRunState.RUNNING.value))
    assert not run_branchable(_run(state=WorkflowRunState.COMPLETED.value))
    assert not run_branchable(_run(mode=WorkflowRunMode.TWILIO.value))
    assert not run_branchable(None)


def test_le_jeton_est_dans_le_chemin_de_l_adresse():
    assert (
        adresse_ws("wss://api.exemple.fr/", 12, JETON)
        == f"wss://api.exemple.fr/api/v1/appel-simule/ws/12/{JETON}"
    )


# --- La route ---------------------------------------------------------------------------------


@pytest.fixture
def banc():
    """La route avec la base, la concurrence, le quota et le pipeline simulés."""
    runs = {12: _run(12), 13: _run(13, jeton="jeton-du-run-13")}
    db = MagicMock()
    db.get_workflow_run_by_id = AsyncMock(side_effect=lambda i: runs.get(i))
    db.update_workflow_run = AsyncMock()
    concurrence = MagicMock()
    concurrence.acquire_org_slot = AsyncMock(return_value="place")
    concurrence.bind_workflow_run = AsyncMock()
    concurrence.release_slot = AsyncMock()
    concurrence.unregister_active_call = AsyncMock()
    jouer = AsyncMock()
    echec = AsyncMock()
    quota = AsyncMock(return_value=SimpleNamespace(has_quota=True, error_message=None))
    app = FastAPI()
    app.include_router(route.router, prefix="/api/v1")
    reserves: set[int] = set()

    async def reserver(run_id):
        # Comme le SET NX de Redis : un seul branchement obtient le run.
        if run_id in reserves:
            return False
        reserves.add(run_id)
        return True

    with (
        patch.object(route, "reserver_le_branchement", side_effect=reserver),
        patch.object(route, "db_client", db),
        patch.object(route, "call_concurrency", concurrence),
        patch.object(route, "jouer_appel_simule", jouer),
        patch.object(route, "mark_workflow_run_failed", echec),
        patch.object(route, "authorize_workflow_run_start", quota),
        patch.object(route.run_pipeline, "register_worker_active_call"),
        patch.object(route.run_pipeline, "unregister_worker_active_call"),
    ):
        yield SimpleNamespace(
            client=TestClient(app),
            db=db,
            jouer=jouer,
            echec=echec,
            quota=quota,
            concurrence=concurrence,
        )


DEBUT = (
    {"event": "connected", "protocol": "Call", "version": "1.0.0"},
    {"event": "start", "start": {"streamSid": "MZ-sim", "callSid": "CA-sim"}},
)


def _fermeture(client, chemin, messages=()):
    with client.websocket_connect(chemin) as ws:
        for message in messages:
            ws.send_text(json.dumps(message))
        with pytest.raises(WebSocketDisconnect) as fin:
            ws.receive_text()
    return fin.value.code


def test_un_jeton_faux_est_refuse_avant_tout(banc):
    assert _fermeture(banc.client, "/api/v1/appel-simule/ws/12/faux", DEBUT) == 4401
    banc.db.update_workflow_run.assert_not_awaited()
    banc.concurrence.acquire_org_slot.assert_not_awaited()
    banc.jouer.assert_not_awaited()


def test_le_jeton_d_un_autre_run_est_refuse(banc):
    assert (
        _fermeture(banc.client, "/api/v1/appel-simule/ws/12/jeton-du-run-13", DEBUT)
        == 4401
    )
    banc.jouer.assert_not_awaited()


def test_un_run_inconnu_est_refuse(banc):
    assert _fermeture(banc.client, f"/api/v1/appel-simule/ws/99/{JETON}", DEBUT) == 4401
    banc.jouer.assert_not_awaited()


def test_le_bon_jeton_joue_le_run_dans_son_organisation(banc):
    _fermeture(banc.client, f"/api/v1/appel-simule/ws/12/{JETON}", DEBUT)
    banc.db.update_workflow_run.assert_awaited_once_with(
        run_id=12, state=WorkflowRunState.RUNNING.value
    )
    banc.jouer.assert_awaited_once()
    assert banc.jouer.await_args.kwargs == {
        "workflow_run_id": 12,
        "organization_id": ORGANISATION,
        "stream_sid": "MZ-sim",
        "call_sid": "CA-sim",
    }
    banc.concurrence.unregister_active_call.assert_awaited_once_with(12)


def test_le_jeton_ne_sert_qu_une_fois(banc):
    _fermeture(banc.client, f"/api/v1/appel-simule/ws/12/{JETON}", DEBUT)
    # La base a enregistré « running » : le second branchement lit ce nouvel état.
    banc.db.get_workflow_run_by_id.side_effect = lambda i: _run(
        i, state=WorkflowRunState.RUNNING.value
    )
    assert _fermeture(banc.client, f"/api/v1/appel-simule/ws/12/{JETON}", DEBUT) == 4409
    assert banc.jouer.await_count == 1


def test_un_run_d_un_autre_mode_est_refuse_meme_avec_le_jeton(banc):
    banc.db.get_workflow_run_by_id.side_effect = lambda i: _run(
        i, mode=WorkflowRunMode.TWILIO.value
    )
    assert _fermeture(banc.client, f"/api/v1/appel-simule/ws/12/{JETON}", DEBUT) == 4409
    banc.jouer.assert_not_awaited()


def test_un_flux_hors_protocole_est_refuse_et_le_run_marque_en_echec(banc):
    code = _fermeture(
        banc.client,
        f"/api/v1/appel-simule/ws/12/{JETON}",
        ({"event": "media"}, {"event": "start"}),
    )
    assert code == 4400
    banc.echec.assert_awaited_once()
    banc.jouer.assert_not_awaited()


def test_un_start_sans_flux_est_refuse(banc):
    code = _fermeture(
        banc.client,
        f"/api/v1/appel-simule/ws/12/{JETON}",
        (DEBUT[0], {"event": "start", "start": {}}),
    )
    assert code == 4400
    banc.jouer.assert_not_awaited()


def test_sans_quota_le_pipeline_ne_part_pas(banc):
    banc.quota.return_value = SimpleNamespace(
        has_quota=False, error_message="Quota exceeded"
    )
    assert _fermeture(banc.client, f"/api/v1/appel-simule/ws/12/{JETON}", DEBUT) == 1008
    banc.echec.assert_awaited_once()
    banc.jouer.assert_not_awaited()


# --- Le transport : protocole Twilio, aucune téléphonie -----------------------------------------


def test_le_serialiseur_n_a_ni_identifiants_ni_raccrochage():
    serialiseur = pipeline.serialiseur_sans_telephonie("MZ-sim", "CA-sim")
    assert serialiseur._params.auto_hang_up is False
    assert serialiseur._account_sid is None


def test_l_audio_est_celui_d_un_appel_telephonique():
    audio = create_audio_config(pipeline.FOURNISSEUR_AUDIO)
    assert audio.transport_in_sample_rate == 8000
    assert audio.transport_out_sample_rate == 8000


# --- Jamais de vrai numéro, jamais de téléphonie comptée ----------------------------------------


def test_un_renvoi_dans_un_appel_simule_reste_un_essai():
    assert WorkflowRunMode.SIMULATED.value in MODES_DE_TEST


def test_la_fenetre_du_run_dit_appelant_simule_sans_telephonie():
    assert WorkflowRunMode.SIMULATED.value in CANAUX_SANS_TELEPHONIE
    analyse = analyser_run({"id": 12, "mode": "simulated", "logs": {}})
    assert analyse["summary"]["channel"] == "simulated"


# --- Corrections de la revue du 05/10 ------------------------------------------------------------


def test_deux_branchements_avec_le_bon_jeton_un_seul_passe(banc):
    """L'état du run est encore « initialized » pour le second (lecture d'avant la mise à jour) :
    seule la réservation atomique l'arrête."""
    _fermeture(banc.client, f"/api/v1/appel-simule/ws/12/{JETON}", DEBUT)
    assert _fermeture(banc.client, f"/api/v1/appel-simule/ws/12/{JETON}", DEBUT) == 4409
    assert banc.jouer.await_count == 1


def test_un_client_muet_libere_la_place(banc):
    with patch.object(route, "DELAI_DEBUT_S", 0.2):
        assert _fermeture(banc.client, f"/api/v1/appel-simule/ws/12/{JETON}") == 4400
    banc.echec.assert_awaited_once()
    banc.concurrence.unregister_active_call.assert_awaited_once_with(12)
    banc.jouer.assert_not_awaited()


def test_le_jeton_est_masque_dans_les_journaux_d_uvicorn():
    import logging

    record = logging.LogRecord(
        "uvicorn.error",
        logging.INFO,
        __file__,
        1,
        '%s - "WebSocket %s" [accepted]',
        ("127.0.0.1:5000", f"/api/v1/appel-simule/ws/12/{JETON}"),
        None,
    )
    assert route.MasquerLeJeton().filter(record)
    assert JETON not in record.getMessage()
    assert "/api/v1/appel-simule/ws/12/***" in record.getMessage()
    filtres = logging.getLogger("uvicorn.error").filters
    assert any(isinstance(f, route.MasquerLeJeton) for f in filtres)


async def test_un_appel_simule_est_un_essai_sans_autre_lecture():
    from api.services.workflow import renvoi_en_test

    with patch.object(renvoi_en_test, "db_client") as db:
        db.run_vient_du_widget = AsyncMock(return_value=True)
        assert await renvoi_en_test.est_un_essai(_run())
        db.run_vient_du_widget.assert_not_awaited()


async def test_le_run_simule_joue_le_brouillon_et_ses_variables():
    from api.services.appel_simule import entree
    from api.services.workflow.run_creation import WorkflowRunInputs

    preparer = AsyncMock(
        return_value=WorkflowRunInputs(
            definition_id=9, initial_context={"nom_magasin": "Test"}, use_draft=True
        )
    )
    db = MagicMock()
    db.create_workflow_run = AsyncMock(return_value=SimpleNamespace(id=12))
    db.update_workflow_run = AsyncMock()
    with (
        patch.object(entree, "prepare_workflow_run_inputs", preparer),
        patch.object(entree, "db_client", db),
    ):
        await entree.creer_run_simule(
            SimpleNamespace(id=34), user_id=3, organization_id=7, simulation={}
        )
    assert preparer.await_args.kwargs == {
        "use_draft": True,
        "include_template_context": True,
    }
    kwargs = db.create_workflow_run.await_args.kwargs
    assert kwargs["use_draft"] is True and kwargs["definition_id"] == 9
    assert kwargs["initial_context"]["nom_magasin"] == "Test"
    assert kwargs["initial_context"]["provider"] == "simulated"
