"""[.mark] Builder partie 3, sous-lot 2 (SE-8 / A-10) : le déploiement progressif sur TOUS les chemins de création d'un appel.

| Chemin | Clé de répartition | Test (vraie fonction de création du run) |
|---|---|---|
| téléphonie entrante | numéro de l'appelant | ``_create_inbound_workflow_run`` |
| téléphonie sortante directe | numéro appelé | route ``/telephony/initiate-call`` |
| appel déclenché par l'API (agent public) | numéro appelé | route ``/public/agent/{trigger}`` |
| flux d'agent entrant | numéro de l'appelant donné par le fournisseur | websocket ``/agent-stream`` |
| widget du site | jeton du site + adresse du visiteur | route ``/public/embed/init`` (vraie base) |
| campagne | campagne + contact | ``CampaignCallDispatcher.dispatch_call`` |
| ARI entrant | numéro de l'appelant | ``ARIConnection._handle_inbound_stasis_start`` |
| transfert vers un agent | l'appel qui transfère | ``AgentRuntimeFactory.resolve_destination`` |

Chaque test joue DEUX clés, une de chaque côté de la part (50 %), et exige la bonne version pour chacune : si la part n'est pas
appliquée, tout part sur la version publiée et le côté « ancienne version » échoue (R1). Aucun appel réel, rien n'est dépensé.
"""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock, patch

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from api.services.publication import deploiement

ANCIENNE, NOUVELLE = 11, 12
ACTIF = {"publication": {"deploiement": {"actif": True}}}
# [.mark] SA-L3b : la répartition entre branches (une branche à 50 % sur la nouvelle version, la principale épinglée sur l'ancienne).
LIGNE = [
    {"branche": 2, "principale": False, "part": 50, "definition": NOUVELLE},
    {"branche": 1, "principale": True, "part": 50, "definition": ANCIENNE},
]
WF = 33


def _definition_publiee():
    return SimpleNamespace(
        id=NOUVELLE,
        status="published",
        workflow_json={"nodes": [], "edges": []},
        template_context_variables={},
        workflow_configurations=ACTIF,
    )


def _workflow(workflow_id: int = WF):
    return SimpleNamespace(
        id=workflow_id,
        user_id=99,
        organization_id=11,
        status="active",
        workflow_uuid="workflow-uuid-123",
        released_definition=_definition_publiee(),
        current_definition=None,
        template_context_variables={},
    )


def _lire_definitions(workflow):
    ancienne = SimpleNamespace(id=ANCIENNE, status="archived", workflow_json={"nodes": [], "edges": []})
    table = {ANCIENNE: ancienne, NOUVELLE: workflow.released_definition}

    async def lire(_workflow_id, definition_id, _organisation):
        return table.get(definition_id)

    return AsyncMock(side_effect=lire)


@pytest.fixture(autouse=True)
def _ligne_du_deploiement(request):
    """Une répartition à 50 % est en cours pour l'agent : la lecture des branches est la seule chose remplacée (sauf pour le widget du
    site, qui joue de vraies branches en base)."""
    if request.node.name.startswith("test_widget_du_site"):
        yield
        return
    with patch.object(deploiement, "lire", new=AsyncMock(return_value=LIGNE)):
        yield


def _numero(cote: int, workflow_id: int = WF, prefixe: str = "0611") -> str:
    """Un numéro dont la place tombe du côté voulu (``cote`` = la version attendue)."""
    for n in range(500):
        numero = f"{prefixe}{n:06d}"
        if deploiement.version_attribuee(LIGNE, workflow_id, numero) == cote:
            return numero
    raise AssertionError("no number found for this side")


def _cle(cote: int, fabrique, workflow_id: int = WF) -> str:
    for n in range(500):
        valeur = fabrique(n)
        if deploiement.version_attribuee(LIGNE, workflow_id, None, valeur) == cote:
            return valeur
    raise AssertionError("no key found for this side")


COTES = (ANCIENNE, NOUVELLE)


# --- la règle de la clé -----------------------------------------------------------------------------------------------------------


def test_chaque_cle_est_stable_et_les_deux_cotes_existent():
    for fabrique in (lambda n: deploiement.cle_campagne(4, f"0611{n:06d}"), lambda n: deploiement.cle_site(9, f"203.0.113.{n}"), deploiement.cle_appel):
        vues = {deploiement.version_attribuee(LIGNE, WF, None, fabrique(n)) for n in range(80)}
        assert vues == {ANCIENNE, NOUVELLE}
        assert deploiement.version_attribuee(LIGNE, WF, None, fabrique(3)) == deploiement.version_attribuee(LIGNE, WF, None, fabrique(3))


def test_une_cle_vide_garde_la_version_d_avant_et_le_contact_a_une_seule_forme():
    assert deploiement.version_attribuee(LIGNE, WF, None, "") == ANCIENNE
    assert deploiement.cle_site(9, "") == "" and deploiement.cle_campagne(4, " ") == ""
    assert deploiement.version_attribuee(LIGNE, WF, None, deploiement.cle_site(9, "")) == ANCIENNE  # visiteur sans adresse
    assert deploiement.cle_campagne(4, "+33 6 11 00 00 01") == deploiement.cle_campagne(4, "06 11 00 00 01")
    assert deploiement.appelant_du_flux({"From": "+33611000001"}) == "+33611000001"
    assert deploiement.appelant_du_flux({"x": "y"}) == ""


def test_la_part_depend_de_la_cle_pas_du_numero_seul():
    # une campagne et un widget ne partagent pas la place d'un numéro : les chemins ne se contaminent pas
    n = "0611000001"
    assert deploiement.cle_campagne(4, n) != deploiement.cle_campagne(5, n)
    assert deploiement.part_de_cle(WF, "campagne:4:611000001") == deploiement.part_de_cle(WF, deploiement.cle_campagne(4, n))


async def test_eteint_aucun_chemin_ne_lit_la_ligne():
    from api.services.workflow.run_creation import definition_to_run

    workflow = _workflow()
    workflow.released_definition.workflow_configurations = None
    deploiement.lire.side_effect = AssertionError("must not be read when off")
    client = SimpleNamespace(get_workflow_definition=_lire_definitions(workflow))
    assert await definition_to_run(client, workflow, cle_de_repartition="site:1:x") is workflow.released_definition
    assert await definition_to_run(client, workflow, appelant="0611000001") is workflow.released_definition


# --- téléphonie entrante -----------------------------------------------------------------------------------------------------------


@pytest.mark.parametrize("cote", COTES)
async def test_telephonie_entrante(cote):
    from api.routes.telephony import _create_inbound_workflow_run

    workflow = _workflow()
    donnees = SimpleNamespace(
        call_id="c1", from_number=_numero(cote), to_number="0100000000", account_id=None, from_country="FR", to_country="FR", raw_data={}
    )
    with patch("api.routes.telephony.db_client") as db:
        db.get_workflow = AsyncMock(return_value=workflow)
        db.get_workflow_definition = _lire_definitions(workflow)
        db.create_workflow_run = AsyncMock(return_value=SimpleNamespace(id=501))
        await _create_inbound_workflow_run(WF, 99, 11, "twilio", donnees, 55)
    assert db.create_workflow_run.await_args.kwargs["definition_id"] == cote


# --- téléphonie sortante directe ---------------------------------------------------------------------------------------------------


def _provider():
    return SimpleNamespace(
        PROVIDER_NAME="twilio",
        WEBHOOK_ENDPOINT="twilio/voice",
        validate_config=Mock(return_value=True),
        initiate_call=AsyncMock(
            return_value=SimpleNamespace(
                call_id="CA123", status="queued", caller_number="+15550001111", provider_metadata={"call_id": "CA123"}
            )
        ),
    )


def _concurrence(mock):
    mock.acquire_org_slot = AsyncMock(return_value=object())
    mock.bind_workflow_run = AsyncMock()
    mock.release_workflow_run_slot = AsyncMock()
    mock.release_slot = AsyncMock()


@pytest.mark.parametrize("cote", COTES)
def test_telephonie_sortante_directe(cote):
    from api.routes.telephony import router
    from api.services.auth.depends import get_user
    from api.tests.test_telephony_routes import _stub_outbound_setup_lookup

    app = FastAPI()
    app.include_router(router)
    app.dependency_overrides[get_user] = lambda: SimpleNamespace(id=7, selected_organization_id=11)
    workflow = _workflow()
    with (
        patch("api.routes.telephony.db_client") as db,
        patch("api.routes.telephony.call_concurrency") as concurrence,
        patch(
            "api.routes.telephony.authorize_workflow_run_start",
            new=AsyncMock(return_value=SimpleNamespace(has_quota=True, error_message="")),
        ),
        patch("api.routes.telephony.get_telephony_provider_by_id", new=AsyncMock(return_value=_provider())),
        patch("api.routes.telephony.get_backend_endpoints", new=AsyncMock(return_value=("https://api.example.com", "wss://x"))),
    ):
        _concurrence(concurrence)
        db.get_user_configurations = AsyncMock(return_value=SimpleNamespace(test_phone_number=None))
        db.get_default_telephony_configuration = AsyncMock(return_value=SimpleNamespace(id=55))
        _stub_outbound_setup_lookup(db)
        db.get_workflow = AsyncMock(return_value=workflow)
        db.get_draft_version = AsyncMock(return_value=None)  # pas de brouillon : la version publiée, donc la répartition
        db.get_workflow_definition = _lire_definitions(workflow)
        db.create_workflow_run = AsyncMock(return_value=SimpleNamespace(id=501, name="WR", initial_context={}))
        db.update_workflow_run = AsyncMock()
        reponse = TestClient(app).post("/telephony/initiate-call", json={"workflow_id": WF, "phone_number": _numero(cote)})
    assert reponse.status_code == 200, reponse.text
    assert db.create_workflow_run.await_args.kwargs["definition_id"] == cote


# --- appel déclenché par l'API ----------------------------------------------------------------------------------------------------


@pytest.mark.parametrize("cote", COTES)
def test_appel_declenche_par_l_api(cote):
    from api.routes.public_agent import router
    from api.tests.test_public_agent_routes import _provider as fournisseur

    app = FastAPI()
    app.include_router(router)
    workflow = _workflow()
    workflow.released_definition.workflow_json = {"nodes": [{"type": "trigger", "data": {"trigger_path": "t-1"}}], "edges": []}
    with (
        patch("api.routes.public_agent.db_client") as db,
        patch("api.routes.public_agent.call_concurrency") as concurrence,
        patch(
            "api.routes.public_agent.authorize_workflow_run_start",
            new=AsyncMock(return_value=SimpleNamespace(has_quota=True, error_message="")),
        ),
        patch("api.routes.public_agent.get_telephony_provider_by_id", new=AsyncMock(return_value=fournisseur())),
        patch("api.routes.public_agent.get_backend_endpoints", new=AsyncMock(return_value=("https://api.example.com", "wss://x"))),
        patch(
            "api.routes.public_agent.resolve_outbound_configuration_id",
            new=AsyncMock(side_effect=lambda configuration, _org, **_k: configuration or 55),
        ),
    ):
        _concurrence(concurrence)
        db.validate_api_key = AsyncMock(return_value=SimpleNamespace(id=7, organization_id=11, created_by=22))
        db.get_agent_trigger_by_path = AsyncMock(return_value=SimpleNamespace(workflow_id=WF, organization_id=11, state="active"))
        db.get_workflow = AsyncMock(return_value=workflow)
        db.get_workflow_definition = _lire_definitions(workflow)
        db.get_default_telephony_configuration = AsyncMock(return_value=SimpleNamespace(id=55))
        db.create_workflow_run = AsyncMock(return_value=SimpleNamespace(id=501))
        db.update_workflow_run = AsyncMock()
        reponse = TestClient(app).post("/public/agent/t-1", headers={"X-API-Key": "k"}, json={"phone_number": _numero(cote)})
    assert reponse.status_code == 200, reponse.text
    assert db.create_workflow_run.await_args.kwargs["definition_id"] == cote


# --- flux d'agent entrant ----------------------------------------------------------------------------------------------------------


@pytest.mark.parametrize("cote", COTES)
async def test_flux_d_agent_entrant(cote):
    from api.routes.agent_stream import agent_stream_websocket

    websocket = SimpleNamespace(query_params={"From": _numero(cote)}, accept=AsyncMock(), close=AsyncMock())
    workflow = _workflow()
    fournisseur = SimpleNamespace(handle_external_websocket=AsyncMock())
    with (
        patch("api.routes.agent_stream.telephony_registry") as registre,
        patch("api.routes.agent_stream.db_client") as db,
        patch("api.routes.agent_stream.call_concurrency") as concurrence,
        patch(
            "api.routes.agent_stream.authorize_workflow_run_start",
            new=AsyncMock(return_value=SimpleNamespace(has_quota=True, error_message=None)),
        ),
    ):
        _concurrence(concurrence)
        concurrence.unregister_active_call = AsyncMock()
        registre.get_optional.return_value = SimpleNamespace(provider_cls=lambda _c: fournisseur)
        db.get_workflow_by_uuid_unscoped = AsyncMock(return_value=workflow)
        db.get_workflow_definition = _lire_definitions(workflow)
        db.create_workflow_run = AsyncMock(return_value=SimpleNamespace(id=44))
        db.update_workflow_run = AsyncMock()
        await agent_stream_websocket(websocket, "cloudonix", "agent-uuid")
    assert db.create_workflow_run.await_args.kwargs["definition_id"] == cote


async def test_flux_d_agent_sans_numero_garde_la_version_d_avant():
    from api.routes.agent_stream import agent_stream_websocket

    websocket = SimpleNamespace(query_params={}, accept=AsyncMock(), close=AsyncMock())
    workflow = _workflow()
    with (
        patch("api.routes.agent_stream.telephony_registry") as registre,
        patch("api.routes.agent_stream.db_client") as db,
        patch("api.routes.agent_stream.call_concurrency") as concurrence,
        patch(
            "api.routes.agent_stream.authorize_workflow_run_start",
            new=AsyncMock(return_value=SimpleNamespace(has_quota=True, error_message=None)),
        ),
    ):
        _concurrence(concurrence)
        concurrence.unregister_active_call = AsyncMock()
        registre.get_optional.return_value = SimpleNamespace(
            provider_cls=lambda _c: SimpleNamespace(handle_external_websocket=AsyncMock())
        )
        db.get_workflow_by_uuid_unscoped = AsyncMock(return_value=workflow)
        db.get_workflow_definition = _lire_definitions(workflow)
        db.create_workflow_run = AsyncMock(return_value=SimpleNamespace(id=44))
        db.update_workflow_run = AsyncMock()
        await agent_stream_websocket(websocket, "cloudonix", "agent-uuid")
    assert db.create_workflow_run.await_args.kwargs["definition_id"] == ANCIENNE


# --- widget du site (vraie base) ---------------------------------------------------------------------------------------------------


@pytest.mark.parametrize("cote", COTES)
async def test_widget_du_site(cote, db_session, async_session):
    from api.tests.mark.equipe_commun import client_http
    from api.tests.mark.site_commun import creer_agent_avec_jeton, limiteur_en_memoire

    organisation_id, _, workflow, jeton = await creer_agent_avec_jeton(db_session, async_session)
    ancienne = workflow.released_definition_id
    await db_session.save_workflow_draft(workflow.id, workflow_definition={"nodes": [], "edges": []}, workflow_configurations=ACTIF)
    nouvelle = (await db_session.publish_workflow_draft(workflow.id)).id
    # [.mark] SA-L3b : de VRAIES branches en base (aucune doublure de la lecture) : la principale reste épinglée sur l'ancienne
    # version, une branche à 50 % sert la nouvelle.
    await db_session.epingler_la_principale(organisation_id, workflow.id, ancienne)
    branche, _ = await db_session.creer_une_branche(organisation_id, workflow.id, "Essai", depuis_definition_id=nouvelle, user_id=None)
    toutes = await db_session.lister_les_branches(organisation_id, workflow.id)
    await db_session.regler_la_repartition(organisation_id, workflow.id, {b.id: (50 if b.id == branche.id else 50) for b in toutes})
    parts = await deploiement.lire(organisation_id, workflow.id)
    visiteur = next(
        a
        for a in (f"203.0.113.{n}" for n in range(250))
        if deploiement.version_attribuee(parts, workflow.id, None, deploiement.cle_site(jeton.id, a)) == (nouvelle if cote == NOUVELLE else ancienne)
    )
    with (
        patch("api.routes.public_embed.adresse_du_visiteur", return_value=visiteur),
        limiteur_en_memoire(),
    ):
        async with client_http() as c:
            reponse = await c.post("/api/v1/public/embed/init", json={"token": jeton.token}, headers={"Origin": "https://client.fr"})
    assert reponse.status_code == 200, reponse.text
    run = await db_session.get_workflow_run_by_id(reponse.json()["workflow_run_id"]) if hasattr(db_session, "get_workflow_run_by_id") else None
    if run is None:
        from api.db.models import WorkflowRunModel

        run = await async_session.get(WorkflowRunModel, reponse.json()["workflow_run_id"])
    assert run.definition_id == (nouvelle if cote == NOUVELLE else ancienne)


# --- campagne ----------------------------------------------------------------------------------------------------------------------


@pytest.mark.parametrize("cote", COTES)
async def test_campagne(cote):
    from api.services.campaign import campaign_call_dispatcher as module

    workflow = _workflow()
    contact = next(
        c
        for c in (f"0611{n:06d}" for n in range(500))
        if deploiement.version_attribuee(LIGNE, WF, None, deploiement.cle_campagne(4, c)) == cote
    )
    campagne = SimpleNamespace(
        id=4, workflow_id=WF, organization_id=11, created_by=7, orchestrator_metadata={}, telephony_configuration_id=55, rate_limit_per_second=1
    )
    lancee = SimpleNamespace(id=9, context_variables={"phone_number": contact}, source_uuid="s")
    fournisseur = SimpleNamespace(PROVIDER_NAME="twilio", WEBHOOK_ENDPOINT="twilio/voice", from_numbers=["+15550000000"])
    dispatcher = module.CampaignCallDispatcher()
    with (
        patch.object(module, "db_client", new=AsyncMock()) as db,
        patch.object(module, "call_concurrency", new=AsyncMock()),
        patch.object(module, "authorize_workflow_run_start", new=AsyncMock(return_value=SimpleNamespace(has_quota=False, error_message="stop"))),
        patch.object(module.rate_limiter, "select_from_number", new=AsyncMock(return_value="+15550000000")),
        patch.object(dispatcher, "get_provider_for_campaign", new=AsyncMock(return_value=fournisseur)),
    ):
        db.get_workflow = AsyncMock(return_value=workflow)
        db.get_workflow_definition = _lire_definitions(workflow)
        db.create_workflow_run = AsyncMock(return_value=SimpleNamespace(id=700))
        with pytest.raises(Exception):  # noqa: B017 -- le quota refuse APRÈS la création du run : seule la création compte ici
            await dispatcher.dispatch_call(lancee, campagne, SimpleNamespace(slot_id="s", scope_key="k"))
    assert db.create_workflow_run.await_args.kwargs["definition_id"] == cote


async def test_campagne_dont_la_variante_fixe_sa_version_n_est_pas_repartie():
    from api.services.campaign import campaign_call_dispatcher as module

    workflow = _workflow()
    split = {"seed": "x", "revision": 1, "variants": [{"id": "33:11", "workflow_id": WF, "workflow_definition_id": ANCIENNE, "weight": 100}]}
    campagne = SimpleNamespace(
        id=4, workflow_id=WF, organization_id=11, created_by=7, orchestrator_metadata={"traffic_split": split},
        telephony_configuration_id=55, rate_limit_per_second=1,
    )
    dispatcher = module.CampaignCallDispatcher()
    with (
        patch.object(module, "db_client", new=AsyncMock()) as db,
        patch.object(module, "call_concurrency", new=AsyncMock()),
        patch.object(module, "authorize_workflow_run_start", new=AsyncMock(return_value=SimpleNamespace(has_quota=False, error_message="stop"))),
        patch.object(module.rate_limiter, "select_from_number", new=AsyncMock(return_value="+1")),
        patch.object(
            dispatcher,
            "get_provider_for_campaign",
            new=AsyncMock(return_value=SimpleNamespace(PROVIDER_NAME="twilio", WEBHOOK_ENDPOINT="w", from_numbers=["+1"])),
        ),
    ):
        db.get_workflow = AsyncMock(return_value=workflow)
        db.get_workflow_definition = _lire_definitions(workflow)
        db.create_workflow_run = AsyncMock(return_value=SimpleNamespace(id=700))
        with pytest.raises(Exception):  # noqa: B017
            await dispatcher.dispatch_call(
                SimpleNamespace(id=9, context_variables={"phone_number": _numero(NOUVELLE)}, source_uuid="s"),
                campagne,
                SimpleNamespace(slot_id="s", scope_key="k"),
            )
    assert db.create_workflow_run.await_args.kwargs["definition_id"] == ANCIENNE  # la variante l'a fixée : pas de tirage


# --- ARI entrant -------------------------------------------------------------------------------------------------------------------


@pytest.mark.parametrize("cote", COTES)
async def test_ari_entrant(cote):
    from api.services.telephony import ari_manager

    workflow = _workflow()
    connexion = ari_manager.ARIConnection(
        organization_id=11, telephony_configuration_id=7, ari_endpoint="http://pbx.example.com:8088", app_name="dograh",
        app_password="x", ws_client_name="w",
    )
    evenement = {"channel": {"caller": {"number": _numero(cote)}, "dialplan": {"exten": "100"}, "name": "PJSIP/x"}}
    with (
        patch.object(ari_manager, "db_client", new=AsyncMock()) as db,
        patch.object(ari_manager, "call_concurrency", new=AsyncMock()),
        patch.object(
            ari_manager, "authorize_workflow_run_start", new=AsyncMock(return_value=SimpleNamespace(has_quota=False, error_message="stop"))
        ),
        patch.object(ari_manager, "mark_workflow_run_failed", new=AsyncMock()),
        patch.object(connexion, "_delete_channel", new=AsyncMock()),
        patch.object(connexion, "_capture_external_pbx_call", new=AsyncMock(return_value={})),
    ):
        db.find_active_phone_number_for_inbound = AsyncMock(
            return_value=SimpleNamespace(telephony_configuration_id=7, inbound_workflow_id=WF, address="100")
        )
        db.get_workflow = AsyncMock(return_value=workflow)
        db.get_workflow_definition = _lire_definitions(workflow)
        db.create_workflow_run = AsyncMock(return_value=SimpleNamespace(id=800))
        await connexion._handle_inbound_stasis_start("ch-1", "Ring", evenement)
    assert db.create_workflow_run.await_args.kwargs["definition_id"] == cote


# --- transfert vers un agent -------------------------------------------------------------------------------------------------------


@pytest.mark.parametrize("cote", COTES)
async def test_transfert_vers_un_agent(cote):
    from api.services.pipecat import agent_runtime_factory as module

    # Les deux côtés se jouent avec deux appels différents (la clé est l'appel qui transfère).
    appel = next(
        i for i in range(1, 500) if deploiement.version_attribuee(LIGNE, WF, None, deploiement.cle_appel(i)) == cote
    )
    workflow = _workflow()
    fabrique = module.AgentRuntimeFactory(
        organization_id=11, workflow_run_id=appel, call_worker=Mock(), audio_config=None, callbacks_factory=Mock()
    )
    with patch.object(module, "db_client", new=AsyncMock()) as db:
        db.get_workflow = AsyncMock(return_value=workflow)
        db.get_workflow_definition = _lire_definitions(workflow)
        _, definition = await fabrique.resolve_destination(WF)
    assert definition.id == cote
