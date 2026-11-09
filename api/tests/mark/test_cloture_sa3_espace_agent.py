"""[.mark] Clôture, SA-3 : dans quel espace vit un agent (message « cet agent est dans l'espace … » au lieu de « introuvable »).

| Test | Ce qu'il prouve |
|---|---|
| espace rendu | un compte qui ouvre l'espace de l'agent apprend son nom et son type |
| espace fermé | un agent d'un espace que le rôle n'ouvre pas reste un 404, comme un agent qui n'existe pas |
"""

import pytest

from api.tests.mark.equipe_commun import (
    client_http,
    creer_compte,
    creer_organisation,
    entetes,
    sans_preparation_des_organisations,  # noqa: F401
)

pytestmark = pytest.mark.usefixtures("sans_preparation_des_organisations")


async def test_l_espace_d_un_agent_est_dit_a_qui_l_ouvre(db_session):
    ouvert = await creer_organisation(db_session, "sa3-esp-ouvert")
    autre = await creer_organisation(db_session, "sa3-esp-autre")
    user, jeton = await creer_compte(db_session, "sa3-espace@example.com", role="Administrateur", organisations=[ouvert, autre])
    agent = await db_session.create_workflow("agent de l'autre", {"nodes": [], "edges": []}, user.id, autre)
    async with client_http() as c:
        r = await c.get(f"/api/v1/espaces/agent/{agent.id}", headers=entetes(jeton, ouvert))
    assert r.status_code == 200
    corps = r.json()
    assert corps["id"] == autre and corps["espace"] == "client" and corps["workflow_id"] == agent.id


async def test_un_agent_d_un_espace_ferme_reste_un_404(db_session):
    ouvert = await creer_organisation(db_session, "sa3-esp-ouvert2")
    ferme = await creer_organisation(db_session, "sa3-esp-ferme2")
    role = await db_session.creer_role(
        nom="Un-seul-client-sa3", labo_ouvert=False, tous_les_clients=False, permissions=["conversations.voir"], organisations=[ouvert]
    )
    user, jeton = await creer_compte(db_session, "sa3-ferme@example.com", organisations=[ouvert, ferme])
    await db_session.poser_membre(user.id, role)
    agent = await db_session.create_workflow("agent ferme", {"nodes": [], "edges": []}, user.id, ferme)
    async with client_http() as c:
        r = await c.get(f"/api/v1/espaces/agent/{agent.id}", headers=entetes(jeton, ouvert))
        absent = await c.get("/api/v1/espaces/agent/99999999", headers=entetes(jeton, ouvert))
    assert r.status_code == 404
    assert absent.status_code == 404
