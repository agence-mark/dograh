"""[.mark] Builder partie 3, SA-L3c, sous-lot 2 (05 § 12) : la branche principale PROTÉGÉE.

| Test | Ce qu'il prouve |
|---|---|
| règle | protégée par défaut pour un agent CLIENT en ligne, jamais pour le Labo ni sans Labo réglé ; le drapeau force la protection ; un agent jamais publié ne l'est pas |
| couche de données | enregistrer, revenir à une version et publier la principale sont refusés (409 côté route) ; abandonner un brouillon reste permis ; une branche ouverte écrit librement |
| un test par chemin d'écriture | éditeur (enregistrer, créer un brouillon), publication, routes de réglages, restauration « Revenir avant », builder (opération en attente, enregistrement) ; les corrections et les modèles de réglages écrivent par ``update_workflow`` (même appel de données, testé à la couche de données) |
| fusion | l'écriture de la fusion n'est pas bloquée par la protection (voir ``test_branches_fusion.py``) |
"""

from __future__ import annotations

import pytest
from sqlalchemy import update

from api.db import branche_ouverte
from api.db import protection_principale as protection
from api.db.models import WorkflowModel
from api.db.models_builder import WorkflowBranchModel
from api.db.protection_principale import PrincipaleProtegee
from api.tests.mark.builder_commun import graphe_depart
from api.tests.mark.test_apres_appel import _organisation, base_v4, smtp  # noqa: F401  (fixtures)
from api.tests.mark.test_sous_dossiers_et_groupe import _oublier, autre_org, org  # noqa: F401

GRAPHE = graphe_depart()
AUTRE = graphe_depart()
AUTRE["nodes"][0]["data"]["prompt"] = "Allô"


@pytest.fixture(autouse=True)
def _branche_fermee():
    branche_ouverte.ouvrir(None, None)
    yield
    branche_ouverte.ouvrir(None, None)


@pytest.fixture
def labo_est(monkeypatch):
    """Dit quelle organisation est le Labo (``None`` : aucun)."""

    def regler(identifiant):
        monkeypatch.setattr("api.services.builder.constantes.organisation_bibliotheque", lambda: identifiant)

    return regler


async def _agent(db_session, org, nom="Agent"):
    return await db_session.create_workflow(
        name=nom, workflow_definition=GRAPHE, user_id=org.utilisateur.id, organization_id=org.organisation.id
    )


async def _protegee(db_session, agent_id):
    async with db_session.async_session() as s:
        return await protection.est_protegee(s, agent_id)


# --- la règle --------------------------------------------------------------------------------------------------------------------


async def test_protegee_par_defaut_pour_un_agent_client_en_ligne_pas_pour_le_labo(org, autre_org, db_session, labo_est):
    agent = await _agent(db_session, org)
    labo_est(None)
    assert await _protegee(db_session, agent.id) is False  # aucun Labo réglé : on ne devine pas
    labo_est(autre_org.organisation.id)
    assert await _protegee(db_session, agent.id) is True  # un client en ligne
    labo_est(org.organisation.id)
    assert await _protegee(db_session, agent.id) is False  # le Labo lui-même
    await db_session.obtenir_la_principale(org.organisation.id, agent.id)
    async with db_session.async_session() as s:
        await s.execute(update(WorkflowBranchModel).where(WorkflowBranchModel.workflow_id == agent.id).values(protegee=True))
        await s.commit()
    assert await _protegee(db_session, agent.id) is True  # le drapeau force la protection, même au Labo


async def test_un_agent_jamais_publie_n_est_pas_protege(org, autre_org, db_session, labo_est):
    agent = await _agent(db_session, org)
    async with db_session.async_session() as s:
        await s.execute(update(WorkflowModel).where(WorkflowModel.id == agent.id).values(released_definition_id=None))
        await s.commit()
    labo_est(autre_org.organisation.id)
    assert await _protegee(db_session, agent.id) is False


# --- la couche de données --------------------------------------------------------------------------------------------------------


async def test_enregistrer_revenir_et_publier_la_principale_protegee_sont_refuses(org, autre_org, db_session, labo_est):
    agent = await _agent(db_session, org)
    labo_est(autre_org.organisation.id)
    with pytest.raises(PrincipaleProtegee):
        await db_session.save_workflow_draft(agent.id, workflow_definition=AUTRE)
    with pytest.raises(PrincipaleProtegee):  # les corrections et les modèles de réglages écrivent par cet appel
        await db_session.update_workflow(
            workflow_id=agent.id,
            name=None,
            workflow_definition=AUTRE,
            template_context_variables=None,
            workflow_configurations=None,
            organization_id=org.organisation.id,
        )
    with pytest.raises(PrincipaleProtegee):
        await db_session.revert_to_version(agent.id, agent.released_definition_id)
    with pytest.raises(PrincipaleProtegee):
        await db_session.publish_workflow_draft(agent.id)
    assert await db_session.get_draft_version(agent.id) is None  # rien n'a été écrit
    relu = await db_session.get_workflow(agent.id, organization_id=org.organisation.id)
    assert relu.workflow_definition == GRAPHE and relu.released_definition_id == agent.released_definition_id


async def test_le_nom_et_les_branches_restent_libres_et_le_labo_ecrit_comme_avant(org, autre_org, db_session, labo_est):
    agent = await _agent(db_session, org)
    labo_est(autre_org.organisation.id)
    await db_session.update_workflow(
        workflow_id=agent.id,
        name="Nouveau nom",
        workflow_definition=None,
        template_context_variables=None,
        workflow_configurations=None,
        organization_id=org.organisation.id,
    )  # le nom est un réglage de l'agent entier, pas du brouillon
    assert (await db_session.get_workflow(agent.id, organization_id=org.organisation.id)).name == "Nouveau nom"
    branche, _ = await db_session.creer_une_branche(org.organisation.id, agent.id, "Essai", depuis_definition_id=None, user_id=org.utilisateur.id)
    branche_ouverte.ouvrir(branche.id, org.utilisateur.id)
    ecrit = await db_session.save_workflow_draft(agent.id, workflow_definition=AUTRE)  # une branche écrit librement
    assert ecrit.branch_id == branche.id
    branche_ouverte.ouvrir(None, None)
    labo_est(org.organisation.id)  # le Labo n'est pas protégé
    assert (await db_session.save_workflow_draft(agent.id, workflow_definition=AUTRE)).workflow_json == AUTRE


async def test_abandonner_un_brouillon_reste_permis(org, autre_org, db_session, labo_est):
    agent = await _agent(db_session, org)
    labo_est(None)
    await db_session.save_workflow_draft(agent.id, workflow_definition=AUTRE)  # un brouillon d'avant la protection
    labo_est(autre_org.organisation.id)
    await db_session.discard_workflow_draft(agent.id)
    assert await db_session.get_draft_version(agent.id) is None


# --- un test par chemin d'écriture -----------------------------------------------------------------------------------------------


async def test_chemin_editeur_enregistrer_et_creer_un_brouillon(org, autre_org, db_session, async_session, test_client_factory, labo_est):
    agent = await _agent(db_session, org)
    labo_est(autre_org.organisation.id)
    await _oublier(async_session)
    async with test_client_factory(org.utilisateur) as client:
        r = await client.put(f"/api/v1/workflow/{agent.id}", json={"workflow_definition": AUTRE})
        assert r.status_code == 409 and r.json()["code"] == "principale_protegee", r.text
        r = await client.post(f"/api/v1/workflow/{agent.id}/create-draft")
        assert r.status_code == 409 and r.json()["code"] == "principale_protegee", r.text
        assert (await client.get(f"/api/v1/workflow/fetch/{agent.id}")).status_code == 200  # lire reste libre
    assert await db_session.get_draft_version(agent.id) is None


async def test_chemin_publication(org, autre_org, db_session, async_session, test_client_factory, labo_est):
    agent = await _agent(db_session, org)
    labo_est(None)
    await db_session.save_workflow_draft(agent.id, workflow_definition=AUTRE)  # un brouillon d'avant la protection
    labo_est(autre_org.organisation.id)
    await _oublier(async_session)
    async with test_client_factory(org.utilisateur) as client:
        r = await client.post(f"/api/v1/workflow/{agent.id}/publish")
        assert r.status_code == 409 and r.json()["code"] == "principale_protegee", r.text
    relu = await db_session.get_workflow(agent.id, organization_id=org.organisation.id)
    assert relu.released_definition_id == agent.released_definition_id


async def test_chemin_routes_de_reglages(org, autre_org, db_session, async_session, test_client_factory, labo_est):
    agent = await _agent(db_session, org)
    labo_est(autre_org.organisation.id)
    await _oublier(async_session)
    async with test_client_factory(org.utilisateur) as client:
        r = await client.put(f"/api/v1/builder/publication/{agent.id}/reglages", json={})
        assert r.status_code == 409 and r.json()["code"] == "principale_protegee", r.text
    assert await db_session.get_draft_version(agent.id) is None


async def test_chemin_restauration_revenir_avant(org, autre_org, db_session, async_session, test_client_factory, labo_est):
    from api.services.builder import revue

    agent = await _agent(db_session, org)
    numero = await revue._ranger(  # noqa: SLF001 -- un instantané à restaurer
        org.organisation.id,
        agent.id,
        cause="essai",
        avant=AUTRE,
        apres=AUTRE,
        version_avant=1,
        version_apres=1,
        fil_id=None,
        operations=[],
        complement=None,
    )
    labo_est(autre_org.organisation.id)
    await _oublier(async_session)
    async with test_client_factory(org.utilisateur) as client:
        r = await client.post(f"/api/v1/builder/agents/{agent.id}/versions/{numero}/restaurer", json={"familles": ["schema"]})
        assert r.status_code == 409 and r.json()["code"] == "principale_protegee", r.text
    assert await db_session.get_draft_version(agent.id) is None


@pytest.fixture
def conception_approuvee(monkeypatch):
    from api.services.builder import conception

    async def approuvee(*_a, **_k):
        return None

    monkeypatch.setattr(conception, "exiger_approuvee", approuvee)


async def test_chemin_builder_operation_en_attente_et_enregistrement(org, autre_org, db_session, labo_est, conception_approuvee):
    from api.services.builder import brouillon
    from api.services.builder.actions import registre
    from api.services.builder.actions.registre import Contexte

    agent = await _agent(db_session, org)
    contexte = Contexte(user=org.utilisateur, workflow_id=agent.id)
    operation = {"op": "modifier_prompt", "id": "1", "prompt": "Allô"}
    labo_est(autre_org.organisation.id)
    r = await registre.executer("brouillon_operation", {"operations": [operation]}, contexte)
    assert r["ok"] is False and r["code"] == "principale_protegee", r
    assert (await brouillon.lire_en_attente(org.organisation.id, agent.id))["operations"] == []  # rien n'a été mis en attente
    # des opérations mises en attente avant la protection : l'enregistrement est refusé aussi
    labo_est(None)
    assert (await registre.executer("brouillon_operation", {"operations": [operation]}, contexte))["ok"] is True
    labo_est(autre_org.organisation.id)
    r = await registre.executer("brouillon_enregistrer", {}, contexte)
    assert r["ok"] is False and r["code"] == "principale_protegee", r
    assert await db_session.get_draft_version(agent.id) is None


async def test_une_branche_ouverte_laisse_le_builder_ecrire(org, autre_org, db_session, labo_est, conception_approuvee):
    from api.services.builder.actions import registre
    from api.services.builder.actions.registre import Contexte

    agent = await _agent(db_session, org)
    branche, _ = await db_session.creer_une_branche(org.organisation.id, agent.id, "Essai", depuis_definition_id=None, user_id=org.utilisateur.id)
    labo_est(autre_org.organisation.id)
    branche_ouverte.ouvrir(branche.id, org.utilisateur.id)
    operation = {"op": "modifier_prompt", "id": "1", "prompt": "Allô"}
    r = await registre.executer("brouillon_operation", {"operations": [operation]}, Contexte(user=org.utilisateur, workflow_id=agent.id))
    assert r["ok"] is True, r
