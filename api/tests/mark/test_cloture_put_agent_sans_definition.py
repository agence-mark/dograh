"""[.mark] Clôture, SA-2 : ``PUT /workflow/{id}`` sans ``workflow_definition`` ne rend plus 500.

Une clé d'API ou le MCP peuvent ne changer que le nom (ou les réglages) d'un agent. Le chargement paresseux de
``released_definition`` échouait (``MissingGreenlet``) ; l'écran, lui, envoie toujours la définition et ne le voyait pas.
Tests sur la VRAIE base, par la vraie route.
"""

from __future__ import annotations

from api.tests.mark.test_apres_appel import _organisation, base_v4, smtp  # noqa: F401
from api.tests.mark.test_principale_protegee import GRAPHE, _agent, labo_est  # noqa: F401
from api.tests.mark.test_sous_dossiers_et_groupe import _oublier, autre_org, org  # noqa: F401


async def test_renommer_un_agent_sans_envoyer_sa_definition_rend_200_et_garde_le_graphe(org, db_session, async_session, test_client_factory, labo_est):  # noqa: F811
    agent = await _agent(db_session, org, nom="Ancien nom")
    labo_est(org.organisation.id)
    await _oublier(async_session)
    async with test_client_factory(org.utilisateur) as client:
        r = await client.put(f"/api/v1/workflow/{agent.id}", json={"name": "Nouveau nom"})
    assert r.status_code == 200, r.text
    assert r.json()["name"] == "Nouveau nom"
    assert r.json()["workflow_definition"], "le graphe n'est pas perdu"


async def test_regler_sans_definition_rend_200_y_compris_pour_un_bloc_de_cles_propres(org, db_session, async_session, test_client_factory, labo_est):  # noqa: F811
    agent = await _agent(db_session, org)
    labo_est(org.organisation.id)
    await _oublier(async_session)
    async with test_client_factory(org.utilisateur) as client:
        r = await client.put(f"/api/v1/workflow/{agent.id}", json={"workflow_configurations": {"max_call_duration": 600}})
        assert r.status_code == 200, r.text
        # un autre agent, d'une autre organisation : 404, jamais 500
        r404 = await client.put("/api/v1/workflow/987654", json={"name": "x"})
    assert r404.status_code == 404, r404.text


# --- la méthode de la base, sur la vraie base (leçon du 09/11 : un test qui remplace ``db_client`` n'a pas vu ce bug) -------------------


async def test_la_base_rend_un_agent_renomme_avec_sa_version_en_ligne_lisible_hors_session(org, db_session):  # noqa: F811
    agent = await _agent(db_session, org)
    rendu = await db_session.update_workflow(
        workflow_id=agent.id, name="Renommé", workflow_definition=None, template_context_variables=None,
        workflow_configurations=None, organization_id=org.organisation.id,
    )
    assert rendu.name == "Renommé"
    assert rendu.released_definition.workflow_json  # ``MissingGreenlet`` avant la correction : chargement paresseux hors session


async def test_la_base_rend_un_agent_dont_le_statut_change_avec_sa_version_en_ligne_lisible_hors_session(org, db_session):  # noqa: F811
    agent = await _agent(db_session, org)
    rendu = await db_session.update_workflow_status(workflow_id=agent.id, status="archived", organization_id=org.organisation.id)
    assert rendu.released_definition.workflow_json


async def test_la_base_refuse_un_agent_d_une_autre_organisation_sans_le_renommer(org, autre_org, db_session):  # noqa: F811
    import pytest

    agent = await _agent(db_session, org)
    with pytest.raises(ValueError):
        await db_session.update_workflow(
            workflow_id=agent.id, name="Pris", workflow_definition=None, template_context_variables=None,
            workflow_configurations=None, organization_id=autre_org.organisation.id,
        )
