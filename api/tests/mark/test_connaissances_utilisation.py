"""[.mark] Partie 3, lot 14 (SE-21, K-2) : l'usage d'un document de « Connaissances » par les agents.

| Test | Ce qu'il prouve |
|---|---|
| comptage | le nombre d'agents qui lisent le document est compté dans la dernière version de chaque agent, jamais inventé |
| cloisonnement | le document d'une autre organisation répond 404 ; les agents d'une autre organisation ne comptent jamais |
"""

from __future__ import annotations

import pytest

from api.tests.mark.equipe_commun import (
    client_http,
    creer_compte,
    creer_organisation,
    entetes,
    sans_preparation_des_organisations,  # noqa: F401
)

pytestmark = pytest.mark.usefixtures("sans_preparation_des_organisations")


def _agent_qui_lit(*documents: str) -> dict:
    return {"nodes": [{"id": "1", "type": "agentNode", "data": {"name": "Accueil", "document_uuids": list(documents)}}], "edges": []}


async def _document(db, org: int, user_id: int, nom: str):
    return await db.create_document(organization_id=org, created_by=user_id, filename=nom, file_size_bytes=10, file_hash=f"h-{nom}", mime_type="text/plain")


async def test_le_nombre_d_agents_qui_lisent_un_document_est_compte_et_cloisonne(db_session):
    org = await creer_organisation(db_session, "doc-a")
    autre = await creer_organisation(db_session, "doc-b")
    user, jeton = await creer_compte(db_session, "doc-a@example.com", role="Administrateur", organisations=[org])
    user_b, _ = await creer_compte(db_session, "doc-b@example.com", role="Administrateur", organisations=[autre])
    doc = await _document(db_session, org, user.id, "tarifs.md")
    doc_b = await _document(db_session, autre, user_b.id, "autre.md")
    await db_session.create_workflow(name="Zoé", workflow_definition=_agent_qui_lit(doc.document_uuid), user_id=user.id, organization_id=org)
    await db_session.create_workflow(name="Alice", workflow_definition=_agent_qui_lit(doc.document_uuid, "x"), user_id=user.id, organization_id=org)
    await db_session.create_workflow(name="Sans", workflow_definition=_agent_qui_lit("x"), user_id=user.id, organization_id=org)
    # un agent d'une autre organisation qui cite le même identifiant ne compte pas
    await db_session.create_workflow(name="Etranger", workflow_definition=_agent_qui_lit(doc.document_uuid), user_id=user_b.id, organization_id=autre)
    async with client_http() as c:
        r = await c.get(f"/api/v1/knowledge-base/documents/{doc.document_uuid}/utilisation", headers=entetes(jeton, org))
        aucun = await c.get(f"/api/v1/knowledge-base/documents/{doc.document_uuid}/utilisation", headers=entetes(jeton, org))
        refuse = await c.get(f"/api/v1/knowledge-base/documents/{doc_b.document_uuid}/utilisation", headers=entetes(jeton, org))
    assert r.status_code == 200
    assert r.json()["nombre"] == 2 and [a["nom"] for a in r.json()["agents"]] == ["Alice", "Zoé"]
    assert aucun.status_code == 200
    assert refuse.status_code == 404
