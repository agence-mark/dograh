"""[.mark] Non-regression test for the business address.

The questions this file answers:

    Do the two save routes (organization, agent) store a valid address and
    refuse one whose commune does not exist or does not carry its postal code?
    Is the agent's address preferred to the organization's? Does every call,
    by phone and on the keyboard, receive ``adresse_etablissement`` -- and
    does an address problem never cost the call?

Why it exists
-------------
Decisions D2 to D4 of 2026-09-16: the address lives on the organization,
overridable per agent, and is handed to the agent in a variable. The town
recognition also takes its location clue from it. 🔴 An address the call no
longer receives fails in silence: the agent simply stops knowing where the
shop is, and recognition loses the clue that separated "Bovet" from Boves.

⚠️ What this file does NOT prove: that the screen shows the fields. That is
``ui/src/components/mark/``.
"""

import inspect
import re
from datetime import UTC, datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from api.routes import organization as route_organisation
from api.routes.workflow import router as routeur_agent
from api.schemas.organization_preferences import (
    AdresseEtablissement,
    OrganizationPreferences,
)
from api.services.auth.depends import get_user, get_user_with_selected_organization
from api.services.communes import adresse as module_adresse
from api.services.communes.adresse import (
    injecter_adresse_etablissement,
    lire_adresse_etablissement,
    resoudre_adresse,
    texte_adresse,
)
from api.services.pipecat import run_pipeline
from api.services.workflow import text_chat_runner

ORGANISATION = 11

SAINT_MAXIMIN = {
    "code_postal": "60740",
    "code_insee": "60589",
    "commune": "Saint-Maximin",
    "voie": "12 rue de la Gare",
}
SENLIS = {"code_postal": "60300", "code_insee": "60612", "commune": "Senlis"}


def _utilisateur():
    return SimpleNamespace(id=1, provider_id="provider-1", selected_organization_id=ORGANISATION)


# --------------------------------------------------------------------------- #
# 1. Organization: PUT /organizations/preferences
# --------------------------------------------------------------------------- #


def _application_organisation() -> FastAPI:
    app = FastAPI()
    app.include_router(route_organisation.router)
    app.dependency_overrides[get_user_with_selected_organization] = _utilisateur
    return app


def _enregistrer_preferences(corps: dict, deja_enregistre: dict | None = None):
    """PUT the preferences through the real route AND upstream's partial update
    (`update_organization_preferences`, 4e6cb22b); only the storage is faked.

    ``deja_enregistre`` is what the organization had stored before.
    """
    from api.schemas.call_events import CallEventsSettings
    from api.schemas.organization_preferences import (
        OrganizationPreferences,
        OrganizationPreferencesResponse,
    )
    from api.services import organization_preferences as service_preferences

    stockees = {"valeur": OrganizationPreferences.model_validate(deja_enregistre or {})}

    async def ecrire(_org, preferences):
        stockees["valeur"] = preferences
        return preferences

    async def relire(_org):
        return OrganizationPreferencesResponse(
            **stockees["valeur"].model_dump(exclude={"call_events"}),
            call_events=CallEventsSettings(),
        )

    ecriture = AsyncMock(side_effect=ecrire)
    with (
        patch.object(
            service_preferences,
            "get_organization_preferences",
            AsyncMock(side_effect=lambda _org: stockees["valeur"]),
        ),
        patch.object(service_preferences, "upsert_organization_preferences", ecriture),
        patch.object(
            service_preferences,
            "get_organization_preferences_response",
            AsyncMock(side_effect=relire),
        ),
    ):
        reponse = TestClient(_application_organisation()).put("/organizations/preferences", json=corps)
    ecrit = ecriture.await_args.args[1] if ecriture.await_count else None
    return reponse, ecrit


def test_preferences_l_adresse_survit_a_un_enregistrement_qui_ne_l_envoie_pas():
    """Collision 7 of the 25/09 analysis: upstream now updates the preferences
    PARTIALLY. An organization's address must survive a save from a screen that
    only sends the time zone -- and must never be validated again when absent."""
    reponse, ecrit = _enregistrer_preferences(
        {"timezone": "Europe/Paris"},
        deja_enregistre={"adresse_etablissement": SAINT_MAXIMIN},
    )
    assert reponse.status_code == 200, reponse.text
    assert ecrit.adresse_etablissement.model_dump() == SAINT_MAXIMIN
    assert ecrit.timezone == "Europe/Paris"
    assert reponse.json()["adresse_etablissement"] == SAINT_MAXIMIN


def test_preferences_adresse_valide_relue_a_lidentique():
    reponse, ecrit = _enregistrer_preferences({"timezone": "Europe/Paris", "adresse_etablissement": SAINT_MAXIMIN})
    assert reponse.status_code == 200, reponse.text
    assert reponse.json()["adresse_etablissement"] == SAINT_MAXIMIN
    assert ecrit.adresse_etablissement.model_dump() == SAINT_MAXIMIN
    # The other preferences travel with it.
    assert ecrit.timezone == "Europe/Paris"


def test_preferences_sans_adresse_acceptees():
    reponse, ecrit = _enregistrer_preferences({"timezone": "Europe/Paris"})
    assert reponse.status_code == 200, reponse.text
    assert ecrit.adresse_etablissement is None


@pytest.mark.parametrize(
    "adresse,message",
    [
        ({**SAINT_MAXIMIN, "code_insee": "60999"}, "Unknown commune"),
        ({**SAINT_MAXIMIN, "code_postal": "60300"}, "does not have the postal code 60300"),
    ],
    ids=["commune-inconnue", "commune-hors-du-code"],
)
def test_preferences_adresse_fausse_refusee_en_422(adresse, message):
    reponse, ecrit = _enregistrer_preferences({"adresse_etablissement": adresse})
    assert reponse.status_code == 422
    assert message in reponse.text
    assert ecrit is None


def test_preferences_code_postal_mal_forme_refuse():
    reponse, ecrit = _enregistrer_preferences({"adresse_etablissement": {**SAINT_MAXIMIN, "code_postal": "6074"}})
    assert reponse.status_code == 422
    assert ecrit is None


def test_le_nom_enregistre_est_le_nom_officiel():
    """The INSEE code is the reference: a name typed by hand is not stored."""
    reponse, ecrit = _enregistrer_preferences(
        {"adresse_etablissement": {**SAINT_MAXIMIN, "commune": "st maximin"}}
    )
    assert reponse.status_code == 200, reponse.text
    assert ecrit.adresse_etablissement.commune == "Saint-Maximin"


# --------------------------------------------------------------------------- #
# 2. Agent: PUT /workflow/{id}
# --------------------------------------------------------------------------- #


def _enregistrer_agent(configurations: dict):
    app = FastAPI()
    app.include_router(routeur_agent)
    app.dependency_overrides[get_user] = _utilisateur
    workflow = SimpleNamespace(
        id=1,
        workflow_uuid="uuid-1",
        name="Agent de test",
        status="active",
        created_at=datetime.now(UTC),
        updated_at=datetime.now(UTC),
        current_definition_id=1,
        call_disposition_codes={},
        released_definition=SimpleNamespace(
            workflow_json={},
            workflow_configurations={},
            template_context_variables={},
            version_number=1,
            status="published",
        ),
    )
    with (
        patch("api.routes.workflow.db_client") as base,
        patch(
            "api.routes.workflow.apply_external_pbx_mapping_policy",
            AsyncMock(side_effect=lambda configurations, **_: configurations),
        ),
        patch(
            "api.routes.workflow.get_resolved_ai_model_configuration",
            AsyncMock(return_value=SimpleNamespace(effective=None, source="none", organization_configuration=None)),
        ),
        patch("api.routes.workflow.UserConfigurationValidator") as validateur,
    ):
        validateur.return_value.validate = AsyncMock(return_value=None)
        base.get_workflow = AsyncMock(return_value=workflow)
        base.get_draft_version = AsyncMock(return_value=None)
        base.update_workflow = AsyncMock(return_value=workflow)
        base.sync_triggers_for_workflow = AsyncMock(return_value=None)
        reponse = TestClient(app).put(
            "/workflow/1", json={"name": "Agent de test", "workflow_configurations": configurations}
        )
        ecrit = (
            base.update_workflow.await_args.kwargs["workflow_configurations"]
            if base.update_workflow.await_count
            else None
        )
        return reponse, ecrit


def test_agent_adresse_valide_ecrite():
    reponse, ecrit = _enregistrer_agent({"adresse_etablissement": SENLIS})
    assert reponse.status_code == 200, reponse.text
    assert ecrit["adresse_etablissement"] == SENLIS


def test_agent_adresse_vide_acceptee():
    reponse, ecrit = _enregistrer_agent({"adresse_etablissement": None})
    assert reponse.status_code == 200, reponse.text
    # Absent or null: either way the agent falls back to the organization.
    assert ecrit.get("adresse_etablissement") is None


@pytest.mark.parametrize(
    "adresse",
    [{**SENLIS, "code_insee": "60999"}, {**SENLIS, "code_postal": "60740"}],
    ids=["commune-inconnue", "commune-hors-du-code"],
)
def test_agent_adresse_fausse_refusee_en_422(adresse):
    reponse, ecrit = _enregistrer_agent({"adresse_etablissement": adresse})
    assert reponse.status_code == 422
    assert ecrit is None


def test_les_deux_champs_figurent_dans_la_spec_publiee():
    """The screen is built against the published spec."""
    agent = routeur_app_spec(routeur_agent)["WorkflowConfigurationDefaults"]["properties"]
    assert "adresse_etablissement" in agent
    organisation = routeur_app_spec(route_organisation.router)["OrganizationPreferences"]["properties"]
    assert "adresse_etablissement" in organisation


def routeur_app_spec(routeur):
    app = FastAPI()
    app.include_router(routeur)
    return app.openapi()["components"]["schemas"]


# --------------------------------------------------------------------------- #
# 3. The town list of a postal code (T9)
# --------------------------------------------------------------------------- #


def test_route_des_communes_dun_code_postal():
    client = TestClient(_application_organisation())
    reponse = client.get("/organizations/communes", params={"code_postal": "60740"})
    assert reponse.status_code == 200, reponse.text
    assert reponse.json() == [{"code_insee": "60589", "nom": "Saint-Maximin"}]

    inconnu = client.get("/organizations/communes", params={"code_postal": "00000"})
    assert inconnu.status_code == 200
    assert inconnu.json() == []

    assert client.get("/organizations/communes", params={"code_postal": "6074"}).status_code == 422


# --------------------------------------------------------------------------- #
# 4. Resolution: agent > organization > none
# --------------------------------------------------------------------------- #


def test_resolution_agent_puis_organisation_puis_rien():
    organisation = OrganizationPreferences(adresse_etablissement=AdresseEtablissement(**SAINT_MAXIMIN))

    assert resoudre_adresse({"adresse_etablissement": SENLIS}, organisation).commune == "Senlis"
    assert resoudre_adresse({}, organisation).commune == "Saint-Maximin"
    assert resoudre_adresse({"adresse_etablissement": None}, organisation).commune == "Saint-Maximin"
    assert resoudre_adresse(None, organisation).commune == "Saint-Maximin"
    assert resoudre_adresse({}, OrganizationPreferences()) is None
    assert resoudre_adresse({}, None) is None


@pytest.mark.parametrize(
    "hors_bornes",
    [{"code_postal": "x"}, "60740 Saint-Maximin", 12, {**SENLIS, "voie": "x" * 500}],
    ids=["incomplete", "texte", "nombre", "voie-trop-longue"],
)
def test_une_adresse_dagent_ecrite_a_la_main_hors_bornes_ne_leve_pas(hors_bornes):
    """⛔ Same rule as the opening hours: a call never dies on the address.
    The organization's address is used instead."""
    organisation = OrganizationPreferences(adresse_etablissement=AdresseEtablissement(**SAINT_MAXIMIN))
    assert resoudre_adresse({"adresse_etablissement": hors_bornes}, organisation).commune == "Saint-Maximin"


@pytest.mark.asyncio
async def test_lire_ladresse_survit_a_une_base_indisponible():
    with patch(
        "api.services.organization_preferences.get_organization_preferences",
        AsyncMock(side_effect=RuntimeError("base indisponible")),
    ):
        assert (await lire_adresse_etablissement({"adresse_etablissement": SENLIS}, ORGANISATION)).commune == "Senlis"
        assert await lire_adresse_etablissement({}, ORGANISATION) is None


# --------------------------------------------------------------------------- #
# 5. Injection
# --------------------------------------------------------------------------- #


def test_injection_texte_exact_avec_et_sans_voie():
    avec = injecter_adresse_etablissement({"a": 1}, AdresseEtablissement(**SAINT_MAXIMIN))
    assert avec == {"a": 1, "adresse_etablissement": "12 rue de la Gare, 60740 Saint-Maximin"}
    sans = injecter_adresse_etablissement({}, AdresseEtablissement(**SENLIS))
    assert sans == {"adresse_etablissement": "60300 Senlis"}


def test_sans_adresse_la_cle_est_absente_et_le_contexte_inchange():
    contexte = {"direction": "inbound"}
    assert injecter_adresse_etablissement(contexte, None) is contexte
    assert "adresse_etablissement" not in contexte


def test_une_valeur_deja_fournie_est_gardee():
    adresse = AdresseEtablissement(**SENLIS)
    assert injecter_adresse_etablissement({"adresse_etablissement": "fournie"}, adresse) == {
        "adresse_etablissement": "fournie"
    }
    assert injecter_adresse_etablissement({"adresse_etablissement": "  "}, adresse) == {
        "adresse_etablissement": "60300 Senlis"
    }


def test_linjection_ne_leve_jamais():
    contexte = {"a": 1}
    with patch.object(module_adresse, "texte_adresse", side_effect=RuntimeError("panne")):
        assert injecter_adresse_etablissement(contexte, AdresseEtablissement(**SENLIS)) is contexte


def test_la_voie_vide_est_rangee_a_none():
    assert AdresseEtablissement(**{**SENLIS, "voie": "   "}).voie is None
    assert texte_adresse(AdresseEtablissement(**{**SENLIS, "voie": " "})) == "60300 Senlis"


# --------------------------------------------------------------------------- #
# 6. Branching: both paths call it, in order
# --------------------------------------------------------------------------- #


def _position(source: str, motif: str, quoi: str) -> int:
    trouve = re.search(motif, source)
    assert trouve, f"{quoi} is no longer in the source."
    return trouve.start()


def test_le_chemin_telephonique_injecte_ladresse_apres_la_date_et_avant_la_persistance():
    source = inspect.getsource(run_pipeline)
    date = _position(source, r"merged_call_context_vars = injecter_date_heure_appel\(", "date injection")
    lecture = _position(source, r"adresse_etablissement = await lire_adresse_etablissement\(\s*run_configs", "address read")
    injection = _position(
        source,
        r"merged_call_context_vars = injecter_adresse_etablissement\(\s*merged_call_context_vars, adresse_etablissement",
        "address injection",
    )
    persistance = _position(
        source, r"update_workflow_run\(\s*workflow_run_id, initial_context=merged_call_context_vars", "persistence"
    )
    fetch = _position(source, r"execute_pre_call_fetch\(", "pre-call fetch")
    assert date < lecture < injection < persistance < fetch
    assert len(re.findall(r"injecter_adresse_etablissement\(", source)) == 1


def test_le_chemin_clavier_injecte_ladresse_apres_la_date():
    source = inspect.getsource(text_chat_runner)
    date = _position(source, r"initial_context = injecter_date_heure_appel\(", "date injection")
    injection = _position(
        source,
        r"initial_context = injecter_adresse_etablissement\(\s*initial_context, adresse_etablissement",
        "address injection",
    )
    fetch = _position(source, r"execute_pre_call_fetch\(", "pre-call fetch")
    assert date < injection < fetch
    assert len(re.findall(r"injecter_adresse_etablissement\(", source)) == 1


class _Arret(Exception):
    """Raised by the mocked engine: everything asserted here is decided before."""


async def _jouer_au_clavier(configurations: dict, contexte_initial: dict, preferences, fetch=None):
    """The keyboard path, RUN up to the engine: what is persisted and handed over."""
    run = SimpleNamespace(
        workflow_id=6,
        name="essai",
        initial_context=dict(contexte_initial),
        definition=SimpleNamespace(
            workflow_json={
                "nodes": [
                    {
                        "id": "start",
                        "type": "startCall",
                        "position": {"x": 0, "y": 0},
                        "data": {"name": "Start", "prompt": "Bonjour.", "is_start": True,
                                 "allow_interrupt": False, "add_global_prompt": False,
                                 "greeting_type": "text", "greeting": "Bonjour.",
                                 "pre_call_fetch_enabled": fetch is not None,
                                 "pre_call_fetch_url": "https://exemple.invalid/fetch" if fetch else None},
                    },
                    {
                        "id": "end",
                        "type": "endCall",
                        "position": {"x": 0, "y": 200},
                        "data": {"name": "End", "prompt": "Fin.", "is_end": True,
                                 "allow_interrupt": False, "add_global_prompt": False},
                    },
                ],
                "edges": [{"id": "e", "source": "start", "target": "end",
                           "data": {"label": "Fin", "condition": "Quand c'est fini."}}],
            },
            workflow_configurations=configurations,
        ),
        workflow=SimpleNamespace(organization_id=ORGANISATION, user=SimpleNamespace(id=1)),
    )
    agent = SimpleNamespace(id=6, organization_id=ORGANISATION, workflow_configurations=configurations)
    moteur = MagicMock(side_effect=_Arret)
    with (
        patch.object(text_chat_runner, "db_client") as base,
        patch.object(text_chat_runner, "PipecatEngine", moteur),
        patch.object(text_chat_runner, "create_llm_service", MagicMock()),
        patch.object(text_chat_runner, "execute_pre_call_fetch", AsyncMock(return_value=fetch)),
        patch(
            "api.services.organization_preferences.get_organization_preferences",
            AsyncMock(return_value=preferences),
        ),
        patch(
            "api.services.configuration.ai_model_configuration.get_effective_ai_model_configuration_for_workflow",
            AsyncMock(return_value=SimpleNamespace(llm=SimpleNamespace(provider="openai", model="gpt-4.1"), embeddings=None)),
        ),
        patch("api.services.managed_model_services.ensure_mps_correlation_id", AsyncMock(return_value=None)),
        patch.object(text_chat_runner, "stamp_sampling_settings", lambda cible, _llm: cible),
    ):
        base.get_workflow_run_with_context = AsyncMock(return_value=(run, None))
        base.get_workflow = AsyncMock(return_value=agent)
        base.update_workflow_run = AsyncMock()
        base.has_active_recordings = AsyncMock(return_value=False)
        with pytest.raises(_Arret):
            await text_chat_runner.execute_text_chat_pending_turn(
                workflow_run_id=7,
                workflow_id=6,
                session_data={"turns": [{"status": "pending", "user_message": None}]},
                checkpoint=None,
            )
        persiste = base.update_workflow_run.await_args.kwargs["initial_context"]
        assert moteur.call_args.kwargs["call_context_vars"] == persiste
        return persiste


ORGANISATION_A_SAINT_MAXIMIN = OrganizationPreferences(adresse_etablissement=AdresseEtablissement(**SAINT_MAXIMIN))


@pytest.mark.asyncio
async def test_clavier_ladresse_de_lorganisation_arrive_au_moteur():
    persiste = await _jouer_au_clavier({}, {"direction": "inbound"}, ORGANISATION_A_SAINT_MAXIMIN)
    assert persiste["adresse_etablissement"] == "12 rue de la Gare, 60740 Saint-Maximin"


@pytest.mark.asyncio
async def test_clavier_ladresse_de_lagent_lemporte():
    persiste = await _jouer_au_clavier(
        {"adresse_etablissement": SENLIS}, {"direction": "inbound"}, ORGANISATION_A_SAINT_MAXIMIN
    )
    assert persiste["adresse_etablissement"] == "60300 Senlis"


@pytest.mark.asyncio
async def test_clavier_sans_adresse_cle_absente():
    persiste = await _jouer_au_clavier({}, {"direction": "inbound"}, OrganizationPreferences())
    assert "adresse_etablissement" not in persiste


@pytest.mark.asyncio
async def test_clavier_le_pre_call_fetch_lemporte():
    persiste = await _jouer_au_clavier(
        {}, {"direction": "inbound"}, ORGANISATION_A_SAINT_MAXIMIN,
        fetch={"adresse_etablissement": "fournie par le client"},
    )
    assert persiste["adresse_etablissement"] == "fournie par le client"
