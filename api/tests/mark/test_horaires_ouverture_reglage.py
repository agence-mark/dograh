"""[.mark] Non-regression test for the opening-hours setting of an agent.

The question this file answers, and only this one:

    Does the route that SAVES an agent's settings store the opening hours as
    typed, refuse a bad entry with its line number, and publish the field?

Why it exists
-------------
⛔ The lesson of 2026-09-10: a test that stops at the function is not a test of
the feature. The validator is exercised here through ``PUT /workflow/{id}``,
with the database mocked out, and the assertion is on what would be WRITTEN.

A bad entry refused at the door is decision D9: the alternative is an agent
that silently gets no opening state on every call, and nobody hears about it
until a caller is told the shop is open on a Sunday.

⚠️ What this file does NOT prove: that the screen shows the refusal. That is
``ui/src/components/mark/section-horaires-ouverture.test.tsx``.
"""

import re
from datetime import UTC, datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from loguru import logger

from api.routes.workflow import router
from api.schemas.workflow_configurations import WorkflowConfigurationDefaults
from api.services.auth.depends import get_user
from api.services.pipecat.etat_ouverture import PARIS, injecter_etat_ouverture

ORGANISATION = 11

EXEMPLE_D2 = """lundi : 10:00-18:30 sur rendez-vous
mardi : 10:00-12:30 et 14:00-18:30
mercredi : 10h-12h30, 14h-18h30
jeudi : 10:00-12:30 et 14:00-18:30
vendredi : 10:00-12:30 et 14:00-19:00
samedi : 10:00-19:00
dimanche : fermé
jours fériés : fermé
exceptions :
du 17/08/2026 au 22/08/2026 : fermé (congés d'été)
24/12/2026 : 10:00-16:00 (horaires réduits)
25/12 : fermé
"""


def _application() -> FastAPI:
    app = FastAPI()
    app.include_router(router)
    app.dependency_overrides[get_user] = lambda: SimpleNamespace(
        id=1,
        provider_id="provider-1",
        selected_organization_id=ORGANISATION,
    )
    return app


def _enregistrer(configurations: dict):
    """PUT the settings through the route; return (response, written configuration)."""
    client = TestClient(_application())
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

        reponse = client.put(
            "/workflow/1",
            json={"name": "Agent de test", "workflow_configurations": configurations},
        )
        ecrit = (
            base.update_workflow.await_args.kwargs["workflow_configurations"]
            if base.update_workflow.await_count
            else None
        )
        return reponse, ecrit


def test_la_route_accepte_lexemple_du_plan_et_lecrit_tel_quel():
    reponse, ecrit = _enregistrer({"horaires_ouverture": EXEMPLE_D2})
    assert reponse.status_code == 200, reponse.text
    assert ecrit["horaires_ouverture"] == EXEMPLE_D2


def test_la_route_refuse_une_saisie_fautive_avec_son_numero_de_ligne():
    reponse, ecrit = _enregistrer(
        {"horaires_ouverture": "lundi : fermé\nmardi : 10:00-25:00\n"}
    )
    assert reponse.status_code == 422
    assert "ligne 2" in reponse.text
    # And nothing reached the database.
    assert ecrit is None


@pytest.mark.parametrize("vide", [None, "", "   \n  "])
def test_vide_est_accepte_et_ecrit_vide(vide):
    reponse, ecrit = _enregistrer({"horaires_ouverture": vide})
    assert reponse.status_code == 200, reponse.text
    assert ecrit.get("horaires_ouverture") is None


def test_le_champ_figure_dans_la_spec_publiee():
    """The screen is built against the published spec: a field missing from it
    is a field the generated client knows nothing about."""
    proprietes = _application().openapi()["components"]["schemas"][
        "WorkflowConfigurationDefaults"
    ]["properties"]
    assert "horaires_ouverture" in proprietes
    assert proprietes["horaires_ouverture"]["anyOf"][0]["maxLength"] == 4000


def test_le_defaut_est_vide():
    assert WorkflowConfigurationDefaults().horaires_ouverture is None


HORAIRES_INVALIDES = {"horaires_ouverture": "lundi 10:00-18:30", "conversion_nombres_transcription": False}


def test_lire_une_configuration_aux_horaires_invalides_ne_leve_pas():
    """⛔ D9 on the READ side. Review of 2026-09-15: the grammar was checked by
    the schema itself, and the schema is also read on the WHOLE configuration
    when a call is set up. Invalid hours stored by hand made that read raise,
    and the call died -- while the injection test, which stops at its own
    function, stayed green."""
    lue = WorkflowConfigurationDefaults.model_validate(HORAIRES_INVALIDES)
    assert lue.horaires_ouverture == "lundi 10:00-18:30"


def test_le_montage_de_lappel_survit_a_des_horaires_invalides():
    """The two call set-up paths that read the whole configuration, called."""
    from api.services.pipecat.conversion_nombres import creer_conversion_nombres
    from api.services.pipecat.service_factory import stamp_pipeline_settings

    assert creer_conversion_nombres(HORAIRES_INVALIDES, None) is None
    estampille = stamp_pipeline_settings({}, HORAIRES_INVALIDES)
    assert "pipeline_settings" in estampille
    assert injecter_etat_ouverture(
        {"direction": "inbound"}, HORAIRES_INVALIDES, maintenant=datetime(2026, 9, 15, 11, tzinfo=PARIS)
    ) == {"direction": "inbound"}


def test_la_grammaire_est_verifiee_par_la_route_et_pas_par_le_schema():
    """The refusal lives on the save route; the schema only turns blank into None."""
    import inspect

    from api.routes import workflow as route

    assert re.search(r"vers_expression_osm\(", inspect.getsource(route))
    assert WorkflowConfigurationDefaults.model_validate({"horaires_ouverture": "   "}).horaires_ouverture is None


@pytest.mark.parametrize("configs", [{}, {"horaires_ouverture": None}, {"horaires_ouverture": "  "}])
def test_un_agent_sans_horaires_ne_journalise_aucune_erreur(configs):
    """D6, the silent side. Before the field was declared, an agent without
    hours returned an unchanged context -- after logging an error on EVERY
    call. Green for the wrong reason: the context was right, the log was
    noise that would have buried a real failure."""
    messages: list[str] = []
    puits = logger.add(lambda message: messages.append(str(message)), level="ERROR")
    try:
        contexte = {"direction": "inbound"}
        assert injecter_etat_ouverture(
            contexte, configs, maintenant=datetime(2026, 9, 15, 11, tzinfo=PARIS)
        ) == {"direction": "inbound"}
    finally:
        logger.remove(puits)
    assert messages == []
