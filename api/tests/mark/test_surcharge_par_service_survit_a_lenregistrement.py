"""[.mark] Non-regression test for the route that SAVES a per-service override.

The question this file answers, and it answers only this one:

    When the agent screen saves a deliberate per-service override, does the
    override survive the trip through ``PUT /workflow/{id}`` — or does the
    route turn it into a frozen copy on the way in?

Why it exists, and why it exists SEPARATELY
-------------------------------------------
``test_surcharge_par_service_sur_client_v2.py`` proves two other things: that
the field-by-field merge inherits correctly at runtime, and that the migration
run on every save of the ORGANISATION configuration spares a marked override.
Both were green while the feature did not work at all, because neither goes
through the route where an override is actually written.

The route carries its OWN conversion, separate from that migration: when the
client is on the v2 format — which is every real .mark client — it compiles the
merged configuration into a complete copy, stores that, and drops
``model_overrides``. So an override saved from the agent screen became a frozen
copy immediately, and the agent stopped inheriting anything from its client.

⛔ The lesson this file records, and it is the expensive one: a test that stops
at the function is not a test of the feature. This one drives the HTTP route,
with the database mocked out, and asserts on what would be WRITTEN.
"""

from datetime import UTC, datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from api.routes.workflow import router
from api.schemas.ai_model_configuration import (
    BYOKAIModelConfiguration,
    BYOKPipelineAIModelConfiguration,
    OrganizationAIModelConfigurationV2,
    compile_ai_model_configuration_v2,
)
from api.services.auth.depends import get_user
from api.services.configuration.ai_model_configuration import (
    DELIBERATE_PER_SERVICE_OVERRIDE_KEY,
    WORKFLOW_MODEL_CONFIGURATION_V2_OVERRIDE_KEY,
)
from api.services.configuration.registry import (
    DeepgramSTTConfiguration,
    MistralLLMConfiguration,
    MistralTTSConfiguration,
)

ORGANISATION = 11

SURCHARGE_VOIX_SEULE = {
    "tts": {
        "provider": "mistral",
        "api_key": "cle-client",
        "voice": "fr_marie_curious",
    }
}


def _client_au_nouveau_format() -> OrganizationAIModelConfigurationV2:
    return OrganizationAIModelConfigurationV2(
        mode="byok",
        byok=BYOKAIModelConfiguration(
            mode="pipeline",
            pipeline=BYOKPipelineAIModelConfiguration(
                llm=MistralLLMConfiguration(
                    api_key="cle-client", model="mistral-large-2512", temperature=0.2
                ),
                tts=MistralTTSConfiguration(api_key="cle-client", voice="fr_marie_neutral"),
                stt=DeepgramSTTConfiguration(api_key="cle-client", model="nova-3-general"),
            ),
        ),
    )


def _application() -> FastAPI:
    app = FastAPI()
    app.include_router(router)
    app.dependency_overrides[get_user] = lambda: SimpleNamespace(
        id=1,
        provider_id="provider-1",
        selected_organization_id=ORGANISATION,
    )
    return app


def _enregistrer(configurations: dict) -> dict:
    """Save workflow configurations through the route, return what was written.

    The database is mocked: the assertion is on the argument handed to
    ``update_workflow``, which is exactly what would have been persisted.
    """
    client = TestClient(_application())
    configuration_client = _client_au_nouveau_format()
    resolu = SimpleNamespace(
        effective=compile_ai_model_configuration_v2(configuration_client),
        source="organization_v2",
        organization_configuration=configuration_client,
    )
    workflow = SimpleNamespace(
        id=1,
        workflow_uuid="uuid-1",
        name="Agent Nuances de Feu",
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
        # Reads the organisation's preferences from a client of its own, so it
        # needs a database. Nothing here is about the PBX policy: it passes the
        # configurations through untouched.
        patch(
            "api.routes.workflow.apply_external_pbx_mapping_policy",
            AsyncMock(side_effect=lambda configurations, **_: configurations),
        ),
        patch(
            "api.routes.workflow.get_resolved_ai_model_configuration",
            AsyncMock(return_value=resolu),
        ),
        patch(
            "api.routes.workflow.UserConfigurationValidator"
        ) as validateur,
    ):
        validateur.return_value.validate = AsyncMock(return_value=None)
        base.get_workflow = AsyncMock(return_value=workflow)
        base.get_draft_version = AsyncMock(return_value=None)
        base.update_workflow = AsyncMock(return_value=workflow)
        base.sync_triggers_for_workflow = AsyncMock(return_value=None)

        reponse = client.put(
            "/workflow/1",
            json={"name": "Agent Nuances de Feu", "workflow_configurations": configurations},
        )

        assert reponse.status_code == 200, reponse.text
        assert base.update_workflow.await_count == 1
        return base.update_workflow.await_args.kwargs["workflow_configurations"]


# --------------------------------------------------------------------------- #
# 1. The failure this file was written for
# --------------------------------------------------------------------------- #


def test_une_surcharge_deliberee_est_ECRITE_telle_quelle():
    """⛔ Before the fix: the route stored a complete copy and dropped this.

    The agent then inherited nothing — the exact opposite of what the screen
    that saved it announces.
    """
    ecrit = _enregistrer(
        {
            "model_overrides": SURCHARGE_VOIX_SEULE,
            DELIBERATE_PER_SERVICE_OVERRIDE_KEY: True,
        }
    )

    assert ecrit["model_overrides"]["tts"]["voice"] == "fr_marie_curious"
    assert WORKFLOW_MODEL_CONFIGURATION_V2_OVERRIDE_KEY not in ecrit
    assert ecrit[DELIBERATE_PER_SERVICE_OVERRIDE_KEY] is True


def test_la_cle_du_client_est_toujours_recopiee_dans_la_surcharge():
    """Upstream stamps the client's key into the override so it stays valid if
    the client later changes provider. That enrichment must not be lost with
    the conversion it used to travel with."""
    ecrit = _enregistrer(
        {
            "model_overrides": {"tts": {"provider": "mistral", "voice": "fr_marie_curious"}},
            DELIBERATE_PER_SERVICE_OVERRIDE_KEY: True,
        }
    )

    assert ecrit["model_overrides"]["tts"]["api_key"] == "cle-client"


# --------------------------------------------------------------------------- #
# 2. Their behaviour, untouched
# --------------------------------------------------------------------------- #


@pytest.mark.parametrize("marqueur", [{}, {DELIBERATE_PER_SERVICE_OVERRIDE_KEY: False}])
def test_sans_marqueur_la_route_convertit_comme_avant(marqueur):
    """An override with no marker is one of theirs, and keeps their behaviour:
    compiled into a complete configuration, and `model_overrides` dropped."""
    ecrit = _enregistrer({"model_overrides": SURCHARGE_VOIX_SEULE, **marqueur})

    assert "model_overrides" not in ecrit
    assert WORKFLOW_MODEL_CONFIGURATION_V2_OVERRIDE_KEY in ecrit


def test_enregistrer_une_configuration_complete_retire_le_marqueur():
    """Switching an agent to a complete configuration must not leave a marker
    behind: it would freeze the migration for an agent that no longer
    overrides a single service."""
    complete = _client_au_nouveau_format().model_dump(mode="json", exclude_none=True)

    ecrit = _enregistrer(
        {
            WORKFLOW_MODEL_CONFIGURATION_V2_OVERRIDE_KEY: complete,
            DELIBERATE_PER_SERVICE_OVERRIDE_KEY: True,
        }
    )

    assert WORKFLOW_MODEL_CONFIGURATION_V2_OVERRIDE_KEY in ecrit
    assert DELIBERATE_PER_SERVICE_OVERRIDE_KEY not in ecrit
    assert "model_overrides" not in ecrit
