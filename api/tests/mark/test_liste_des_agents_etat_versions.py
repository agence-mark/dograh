"""[.mark] Builder partie 2, K2 : la liste des agents dit la version, son état, la dernière modification et les appels
des 7 derniers jours (colonnes de la maquette), lus en deux requêtes pour toute la liste.

| Test | Ce qu'il prouve |
|---|---|
| publiée | un agent seulement publié est « publiée », avec son numéro de version |
| brouillon modifié | un brouillon posé au-dessus d'une version publiée donne « brouillon modifié » et garde le numéro publié |
| appels | seuls les appels des 7 derniers jours comptent |
| liste vide | aucune requête, un dictionnaire vide |
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta

from api.db.models import OrganizationModel, UserModel, WorkflowRunModel
from api.enums import WorkflowRunMode


async def _agent(async_session, db_session):
    suffixe = uuid.uuid4().hex[:10]
    organisation = OrganizationModel(provider_id=f"liste-org-{suffixe}")
    async_session.add(organisation)
    await async_session.flush()
    utilisateur = UserModel(provider_id=f"liste-user-{suffixe}", selected_organization_id=organisation.id)
    async_session.add(utilisateur)
    await async_session.flush()
    agent = await db_session.create_workflow(
        name="Agent de la liste",
        workflow_definition={"nodes": [], "edges": []},
        user_id=utilisateur.id,
        organization_id=organisation.id,
    )
    return agent, utilisateur


async def test_un_agent_publie_est_lu_publiee_avec_son_numero(db_session, async_session):
    agent, _ = await _agent(async_session, db_session)
    etats = await db_session.get_etat_des_versions_pour_liste([agent.id])
    assert etats[agent.id]["version_etat"] == "publiee"
    assert etats[agent.id]["version_numero"] == 1
    assert etats[agent.id]["modifie_le"] is not None
    assert etats[agent.id]["appels_7j"] == 0


async def test_un_brouillon_au_dessus_du_publie_donne_brouillon_modifie(db_session, async_session):
    agent, _ = await _agent(async_session, db_session)
    await db_session.save_workflow_draft(
        agent.id, workflow_definition={"nodes": [{"id": "1"}], "edges": []}
    )
    etats = await db_session.get_etat_des_versions_pour_liste([agent.id])
    assert etats[agent.id]["version_etat"] == "brouillon_modifie"
    assert etats[agent.id]["version_numero"] == 1


async def test_seuls_les_appels_des_sept_derniers_jours_comptent(db_session, async_session):
    agent, utilisateur = await _agent(async_session, db_session)
    for jours in (1, 3, 20):
        appel = WorkflowRunModel(
            name=f"appel-{jours}",
            workflow_id=agent.id,
            mode=WorkflowRunMode.SMALLWEBRTC.value,
            created_at=datetime.now(UTC) - timedelta(days=jours),
        )
        async_session.add(appel)
    await async_session.flush()
    etats = await db_session.get_etat_des_versions_pour_liste([agent.id])
    assert etats[agent.id]["appels_7j"] == 2


async def test_une_liste_vide_ne_demande_rien(db_session):
    assert await db_session.get_etat_des_versions_pour_liste([]) == {}
