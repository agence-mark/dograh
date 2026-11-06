"""[.mark] V2b (E51) : « remplacé par N agents » sur les cartes de Modèles et clés.

| Test | Ce qu'il prouve |
|---|---|
| compte par brique | un agent qui remplace la voix compte pour ``tts`` seulement ; un agent sans remplacement ne compte pas |
| organisation | les agents d'une autre organisation ne sont jamais comptés |
| archivés | un agent archivé ne compte plus |
| route | la route rend les quatre comptes de l'organisation de l'appelant |
"""

from __future__ import annotations

import uuid
from types import SimpleNamespace

import pytest

from api.db.models import OrganizationModel, UserModel
from api.routes.organization import get_model_configuration_v2_remplacements


async def _organisation(async_session):
    suffixe = uuid.uuid4().hex[:10]
    organisation = OrganizationModel(provider_id=f"remplacements-org-{suffixe}")
    async_session.add(organisation)
    await async_session.flush()
    utilisateur = UserModel(
        provider_id=f"remplacements-user-{suffixe}",
        selected_organization_id=organisation.id,
    )
    async_session.add(utilisateur)
    await async_session.flush()
    return organisation, utilisateur


async def _agent(db_session, organisation, utilisateur, surcharges=None):
    return await db_session.create_workflow(
        name="Agent",
        workflow_definition={"nodes": [], "edges": []},
        user_id=utilisateur.id,
        organization_id=organisation.id,
        workflow_configurations={"model_overrides": surcharges} if surcharges else None,
    )


@pytest.mark.asyncio
async def test_compte_par_brique_et_par_organisation(async_session, db_session):
    organisation, utilisateur = await _organisation(async_session)
    autre, autre_utilisateur = await _organisation(async_session)
    await _agent(db_session, organisation, utilisateur)
    await _agent(db_session, organisation, utilisateur, {"tts": {"provider": "cartesia"}})
    await _agent(
        db_session,
        organisation,
        utilisateur,
        {"tts": {"provider": "cartesia"}, "llm": {"provider": "mistral"}},
    )
    await _agent(db_session, autre, autre_utilisateur, {"stt": {"provider": "soniox"}})

    assert await db_session.compter_remplacements_de_modeles(organisation.id) == {
        "llm": 1,
        "tts": 2,
        "stt": 0,
        "realtime": 0,
    }
    assert (await db_session.compter_remplacements_de_modeles(autre.id))["stt"] == 1


@pytest.mark.asyncio
async def test_un_agent_archive_ne_compte_plus(async_session, db_session):
    organisation, utilisateur = await _organisation(async_session)
    agent = await _agent(
        db_session, organisation, utilisateur, {"tts": {"provider": "cartesia"}}
    )
    assert (await db_session.compter_remplacements_de_modeles(organisation.id))["tts"] == 1
    agent.status = "archived"
    await async_session.flush()
    assert (await db_session.compter_remplacements_de_modeles(organisation.id))["tts"] == 0


@pytest.mark.asyncio
async def test_la_route_rend_les_comptes_de_l_organisation_de_l_appelant(
    async_session, db_session
):
    organisation, utilisateur = await _organisation(async_session)
    await _agent(db_session, organisation, utilisateur, {"realtime": {"provider": "openai_realtime"}})
    reponse = await get_model_configuration_v2_remplacements(
        user=SimpleNamespace(selected_organization_id=organisation.id)
    )
    assert reponse == {"llm": 0, "tts": 0, "stt": 0, "realtime": 1}
