"""[.mark] Non-regression test for the budget of the vocabulary shown on screen (Q2).

The questions this file answers:

    For an organization whose transcription is Deepgram, does the API say
    « N / ceiling tokens (Deepgram) » and name the ticked terms that would not
    be sent -- with the very computation a call uses? For a provider with no
    declared ceiling, does it say that nothing is sent? And is the route
    published for the screen?

Why it exists
-------------
Plan « le lexique » (2026-09-26), Q2: the ceiling is shown next to the
vocabulary, computed by the API for the organization's provider (one source of
truth), never counted by the screen.

⚠️ What the screen does with it is proven in
``ui/src/components/mark/__tests__/SectionLexiqueMetier.test.tsx``.
"""

import copy
import uuid
from types import SimpleNamespace

import pytest
from fastapi import FastAPI

from api.db.models import OrganizationModel
from api.enums import OrganizationConfigurationKey
from api.routes import organization as route_organisation
from api.schemas.ai_model_configuration import EffectiveAIModelConfiguration
from api.schemas.lexique_metier import LexiqueMetier
from api.services.configuration.ai_model_configuration import (
    convert_legacy_ai_model_configuration_to_v2,
)
from api.services.configuration.plafond_lexique import jetons_du_terme, plafond_du_lexique
from api.tests.integrations._run_pipeline_helpers import USER_CONFIGURATION


async def _organisation(db_session, async_session, stt: dict | None) -> int:
    org = OrganizationModel(provider_id=f"test-org-budget-{uuid.uuid4().hex[:10]}")
    async_session.add(org)
    await async_session.flush()
    if stt is not None:
        modeles = copy.deepcopy(USER_CONFIGURATION)
        modeles["stt"].update(stt)
        await db_session.upsert_configuration(
            org.id,
            OrganizationConfigurationKey.MODEL_CONFIGURATION_V2.value,
            convert_legacy_ai_model_configuration_to_v2(
                EffectiveAIModelConfiguration.model_validate(modeles)
            ).model_dump(mode="json", exclude_none=True),
        )
    return org.id


def _lexique(n: int) -> LexiqueMetier:
    return LexiqueMetier.model_validate(
        {
            "termes": [
                *({"terme": f"Marque{i:03d}", "a_ecouter": True} for i in range(n)),
                {"terme": "Pas cochée", "a_ecouter": False},
            ]
        }
    )


@pytest.mark.asyncio
async def test_le_budget_est_celui_du_fournisseur_de_lorganisation(db_session, async_session):
    organisation = await _organisation(db_session, async_session, {"provider": "deepgram", "model": "nova-3"})
    budget = await route_organisation.budget_lexique(
        request=_lexique(400), user=SimpleNamespace(selected_organization_id=organisation)
    )
    deepgram = plafond_du_lexique("deepgram", "nova-3")
    assert budget.fournisseur == "deepgram"
    assert budget.nom_du_plafond == "Deepgram"
    assert budget.plafond_jetons == deepgram.jetons
    assert 0 < budget.jetons <= deepgram.jetons
    assert budget.jetons == sum(jetons_du_terme(t, deepgram) for t in budget.envoyes)
    assert budget.envoyes[0] == "Marque000"
    assert budget.non_envoyes and budget.non_envoyes[-1] == "Marque399"
    assert "Pas cochée" not in budget.envoyes + budget.non_envoyes


@pytest.mark.asyncio
async def test_un_petit_lexique_tient_entier(db_session, async_session):
    organisation = await _organisation(db_session, async_session, {"provider": "deepgram", "model": "nova-3"})
    budget = await route_organisation.budget_lexique(
        request=_lexique(3), user=SimpleNamespace(selected_organization_id=organisation)
    )
    assert budget.envoyes == ["Marque000", "Marque001", "Marque002"]
    assert budget.non_envoyes == []


@pytest.mark.asyncio
async def test_sans_fournisseur_configure_rien_nest_envoye_et_cest_dit(db_session, async_session):
    organisation = await _organisation(db_session, async_session, None)
    budget = await route_organisation.budget_lexique(
        request=_lexique(2), user=SimpleNamespace(selected_organization_id=organisation)
    )
    assert budget.plafond_jetons is None and budget.nom_du_plafond is None
    assert budget.envoyes == []
    assert budget.non_envoyes == ["Marque000", "Marque001"]


def test_la_route_figure_dans_la_spec_publiee():
    app = FastAPI()
    app.include_router(route_organisation.router)
    chemins = app.openapi()["paths"]
    assert "post" in chemins["/organizations/lexique/budget"]
