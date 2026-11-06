"""[.mark] Partie 3, lot 15 (SE-25 N-1, SE-29 O-1, P-1, P-2, P-3) : équipe, relation, journal, invitation.

| Test | Ce qu'il prouve |
|---|---|
| P-1 | le journal rend le nom d'un membre ; un compte sans nom est marqué ``sans_nom`` (jamais son identifiant brut) ; un geste sans compte garde son auteur |
| P-2 | le journal se filtre par membre et par espace, DANS la requête (le total suit le filtre) |
| P-3 | l'invitation lue dit qui invite (son nom, jamais son adresse) et jusqu'à quand le lien vaut |
| N-1 | « Suivi par » ne propose que les membres dont le rôle ouvre CE client ; confier un fil à un autre est refusé |
| O-1 | la bande de chiffres d'un client : appels des 7 jours et note du juge de CE client ; un client non ouvert : 404 |
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import text

from api.tests.mark.equipe_commun import (
    client_http,
    creer_compte,
    creer_organisation,
    entetes,
    sans_preparation_des_organisations,  # noqa: F401
)

pytestmark = pytest.mark.usefixtures("sans_preparation_des_organisations")


async def _role(db, nom, *, tous=True, organisations=(), permissions=("conversations.voir",)):
    return await db.creer_role(nom=nom, labo_ouvert=True, tous_les_clients=tous, permissions=list(permissions), organisations=list(organisations))


async def test_p1_p2_le_journal_dit_le_nom_filtre_par_membre_et_par_espace(db_session):
    a = await creer_organisation(db_session, "j15-a")
    b = await creer_organisation(db_session, "j15-b")
    admin, jeton = await creer_compte(db_session, "j15-admin@example.com", role="Administrateur", organisations=[a, b])
    await db_session.poser_membre(admin.id, (await db_session.role_par_nom("Administrateur"))["id"], prenom="Léa", nom="Martin")
    sans_nom, _ = await creer_compte(db_session, "j15-sansnom@example.com", role="Membre", organisations=[a])
    await db_session.ecrire_journal(user_id=admin.id, auteur="prov-admin", action="agents.modifier", organization_id=a)
    await db_session.ecrire_journal(user_id=admin.id, auteur="prov-admin", action="agents.publier", organization_id=b)
    await db_session.ecrire_journal(user_id=sans_nom.id, auteur="prov-brut-1234", action="tests.jouer", organization_id=a)
    await db_session.ecrire_journal(user_id=None, auteur="portail:Nuances", action="relation.message", organization_id=a)
    async with client_http() as c:
        tout = (await c.get("/api/v1/equipe-mark/journal?limit=100", headers=entetes(jeton))).json()
        par_membre = (await c.get(f"/api/v1/equipe-mark/journal?membre={admin.id}", headers=entetes(jeton))).json()
        par_espace = (await c.get(f"/api/v1/equipe-mark/journal?organization_id={b}", headers=entetes(jeton))).json()
        les_deux = (await c.get(f"/api/v1/equipe-mark/journal?membre={admin.id}&organization_id={a}", headers=entetes(jeton))).json()
    lignes = {x["action"]: x for x in tout["lignes"]}
    assert lignes["agents.modifier"]["qui"] == "Léa Martin" and lignes["agents.modifier"]["sans_nom"] is False
    sans = lignes["tests.jouer"]
    assert sans["qui"] is None and sans["sans_nom"] is True
    assert "prov-brut-1234" not in str({k: v for k, v in sans.items() if k in ("qui",)})  # l'écran n'a pas l'identifiant à montrer
    assert lignes["relation.message"]["qui"] == "portail:Nuances" and lignes["relation.message"]["sans_nom"] is False
    assert par_membre["total"] == 2 and {x["action"] for x in par_membre["lignes"]} == {"agents.modifier", "agents.publier"}
    assert par_espace["total"] == 1 and par_espace["lignes"][0]["action"] == "agents.publier"
    assert les_deux["total"] == 1 and les_deux["lignes"][0]["action"] == "agents.modifier"


async def test_p3_l_invitation_dit_qui_invite_sans_son_adresse_et_jusqu_a_quand(db_session):
    org = await creer_organisation(db_session, "j15-inv")
    chef, jeton = await creer_compte(db_session, "j15-chef@example.com", role="Administrateur", organisations=[org])
    await db_session.poser_membre(chef.id, (await db_session.role_par_nom("Administrateur"))["id"], prenom="Evan", nom="L")
    membre = (await db_session.role_par_nom("Membre"))["id"]
    async with client_http() as c:
        cree = (await c.post("/api/v1/equipe-mark/invitations", headers=entetes(jeton), json={"email": "nouvelle@example.com", "role_id": membre})).json()
        lue = await c.get(f"/api/v1/auth/invitation/{cree['lien'].split('jeton=', 1)[1]}")
    corps = lue.json()
    assert corps["invite_par"] == "Evan L"
    assert "j15-chef@example.com" not in lue.text
    assert datetime.fromisoformat(corps["expire_le"]) > datetime.now(UTC)


async def test_n1_le_suivi_n_est_propose_qu_aux_membres_dont_le_role_ouvre_le_client(db_session):
    a = await creer_organisation(db_session, "n1-a")
    b = await creer_organisation(db_session, "n1-b")
    admin, jeton = await creer_compte(db_session, "n1-admin@example.com", role="Administrateur", organisations=[a, b])
    await db_session.poser_membre(admin.id, (await db_session.role_par_nom("Administrateur"))["id"], prenom="Admin", nom="Tous")
    seulement_a = await _role(db_session, "Seulement-A", tous=False, organisations=[a])
    seulement_b = await _role(db_session, "Seulement-B", tous=False, organisations=[b])
    ua, _ = await creer_compte(db_session, "n1-a@example.com", organisations=[a])
    await db_session.poser_membre(ua.id, seulement_a, prenom="Ana", nom="A")
    ub, _ = await creer_compte(db_session, "n1-b@example.com", organisations=[b])
    await db_session.poser_membre(ub.id, seulement_b, prenom="Ben", nom="B")
    fil = await db_session.creer_fil_relation(a, sorte="question", sujet="Une question", auteur="Client", texte="Bonjour")
    async with client_http() as c:
        pour_a = {m["nom"] for m in (await c.get(f"/api/v1/relation/membres?client={a}", headers=entetes(jeton))).json()}
        pour_b = {m["nom"] for m in (await c.get(f"/api/v1/relation/membres?client={b}", headers=entetes(jeton))).json()}
        tous = {m["nom"] for m in (await c.get("/api/v1/relation/membres", headers=entetes(jeton))).json()}
        autre_client = await c.get("/api/v1/relation/membres?client=999999", headers=entetes(jeton))
        # confier le fil du client A à qui n'ouvre que B : refusé ; à qui ouvre A : accepté
        refuse = await c.patch(f"/api/v1/relation/clients/{a}/fils/{fil['id']}", headers=entetes(jeton), json={"suivi_par": ub.id})
        accepte = await c.patch(f"/api/v1/relation/clients/{a}/fils/{fil['id']}", headers=entetes(jeton), json={"suivi_par": ua.id})
    assert pour_a == {"Admin Tous", "Ana A"}
    assert pour_b == {"Admin Tous", "Ben B"}
    assert {"Admin Tous", "Ana A", "Ben B"} <= tous  # sans client : la liste d'avant
    assert autre_client.status_code == 404
    assert refuse.status_code == 422 and accepte.status_code == 204


async def test_o1_la_bande_de_chiffres_d_un_client_ne_compte_que_lui(db_session):
    a = await creer_organisation(db_session, "o1-a")
    b = await creer_organisation(db_session, "o1-b")
    admin, jeton = await creer_compte(db_session, "o1-admin@example.com", role="Administrateur", organisations=[a, b])
    agent = await db_session.create_workflow(name="Standard", workflow_definition={}, user_id=admin.id, organization_id=a)
    autre = await db_session.create_workflow(name="Autre", workflow_definition={}, user_id=admin.id, organization_id=b)
    for wf, org, note, il_y_a in ((agent, a, 4.0, 1), (agent, a, 5.0, 2), (agent, a, 1.0, 20), (autre, b, 2.0, 1)):
        run = await db_session.create_workflow_run(f"appel-{org}-{il_y_a}", wf.id, "smallwebrtc", admin.id, organization_id=org)
        async with db_session.async_session() as s:
            await s.execute(text("update workflow_runs set created_at = :d, note_juge = :n where id = :i"), {"d": datetime.now(UTC) - timedelta(days=il_y_a), "n": note, "i": run.id})
            await s.commit()
    async with client_http() as c:
        ra = (await c.get(f"/api/v1/relation/clients/{a}/chiffres", headers=entetes(jeton))).json()
        rb = (await c.get(f"/api/v1/relation/clients/{b}/chiffres", headers=entetes(jeton))).json()
        inconnu = await c.get("/api/v1/relation/clients/999999/chiffres", headers=entetes(jeton))
    assert ra["appels_7j"] == 2 and ra["note_juge"] == 4.5  # l'appel de 20 jours et ceux de l'autre client ne comptent pas
    assert rb["appels_7j"] == 1 and rb["note_juge"] == 2.0
    assert inconnu.status_code == 404
