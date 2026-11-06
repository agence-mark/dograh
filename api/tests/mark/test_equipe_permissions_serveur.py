"""[.mark] builder partie 2, U2 ter, sous-lot 1 : les permissions vérifiées côté serveur, sur la vraie application.

| Test | Ce qu'il prouve |
|---|---|
| sans permission | un membre de l'équipe sans la permission reçoit 403, avec elle la route s'ouvre |
| sans rôle | un compte sans rôle d'équipe lit (MEMBRE) mais n'écrit rien qui exige une permission |
| organisation de l'adresse | une organisation où le compte n'est pas membre est refusée (403) |
| rôle qui n'ouvre pas | un compte de l'équipe n'entre pas dans un client que son rôle n'ouvre pas, même s'il en était membre |
| client créé après | un rôle « tous les clients » ouvre une organisation créée après le compte |
| journal | un geste d'écriture à permission écrit une ligne : qui, quoi, quel espace |
| fermé par défaut | une route sans décision au registre est refusée |
| clé d'API | une clé reste dans son organisation, l'adresse ne la déplace pas |
"""

import pytest

from api.services.equipe_mark import registre_routes as registre
from api.tests.mark.equipe_commun import (
    client_http,
    creer_compte,
    creer_organisation,
    entetes,
    sans_preparation_des_organisations,  # noqa: F401
)

pytestmark = pytest.mark.usefixtures("sans_preparation_des_organisations")


async def _role_avec(db, nom: str, permissions, **kw) -> int:
    return await db.creer_role(
        nom=nom,
        labo_ouvert=kw.get("labo_ouvert", True),
        tous_les_clients=kw.get("tous_les_clients", True),
        permissions=list(permissions),
        organisations=kw.get("organisations", []),
    )


async def test_sans_la_permission_403_avec_la_permission_la_route_s_ouvre(db_session):
    org = await creer_organisation(db_session, "perm-org-1")
    role = await _role_avec(db_session, "Lecteur-test", ["conversations.voir"])
    editeur = await _role_avec(db_session, "Editeur-test", ["agents.publier"])
    lecteur, jeton_l = await creer_compte(db_session, "lecteur@example.com", organisations=[org])
    await db_session.poser_membre(lecteur.id, role)
    ecrivain, jeton_e = await creer_compte(db_session, "ecrivain@example.com", organisations=[org])
    await db_session.poser_membre(ecrivain.id, editeur)

    async with client_http() as c:
        refuse = await c.post("/api/v1/workflow/999999/publish", headers=entetes(jeton_l, org), json={})
        ouvert = await c.post("/api/v1/workflow/999999/publish", headers=entetes(jeton_e, org), json={})
    assert refuse.status_code == 403
    assert "agents.publier" in refuse.json()["detail"]
    assert ouvert.status_code != 403  # la porte s'ouvre ; la route répond ensuite pour son compte


async def test_un_compte_sans_role_lit_mais_n_ecrit_pas(db_session):
    org = await creer_organisation(db_session, "perm-org-2")
    _, jeton = await creer_compte(db_session, "sansrole@example.com", organisations=[org])
    async with client_http() as c:
        lecture = await c.get("/api/v1/workflow/count", headers=entetes(jeton, org))
        ecriture = await c.post("/api/v1/workflow/999999/publish", headers=entetes(jeton, org), json={})
    assert lecture.status_code == 200
    assert ecriture.status_code == 403


async def test_une_organisation_dont_on_n_est_pas_membre_est_refusee(db_session):
    mienne = await creer_organisation(db_session, "perm-org-3a")
    autre = await creer_organisation(db_session, "perm-org-3b")
    _, jeton = await creer_compte(db_session, "isole@example.com", organisations=[mienne])
    async with client_http() as c:
        ok = await c.get("/api/v1/workflow/count", headers=entetes(jeton, mienne))
        ko = await c.get("/api/v1/workflow/count", headers=entetes(jeton, autre))
        illisible = await c.get("/api/v1/workflow/count", headers=entetes(jeton, "abc"))
    assert ok.status_code == 200
    assert ko.status_code == 403
    assert illisible.status_code == 400


async def test_un_role_qui_n_ouvre_pas_un_client_le_ferme_meme_pour_un_membre(db_session):
    ouvert = await creer_organisation(db_session, "perm-org-4a")
    ferme = await creer_organisation(db_session, "perm-org-4b")
    role = await _role_avec(
        db_session,
        "Freelance-test",
        ["conversations.voir"],
        labo_ouvert=False,
        tous_les_clients=False,
        organisations=[ouvert],
    )
    user, jeton = await creer_compte(db_session, "free@example.com", organisations=[ouvert, ferme])
    await db_session.poser_membre(user.id, role)
    async with client_http() as c:
        ok = await c.get("/api/v1/workflow/count", headers=entetes(jeton, ouvert))
        ko = await c.get("/api/v1/workflow/count", headers=entetes(jeton, ferme))
    assert ok.status_code == 200
    assert ko.status_code == 403


async def test_un_role_tous_les_clients_ouvre_une_organisation_creee_apres(db_session):
    role = await _role_avec(db_session, "Tous-test", ["conversations.voir"])
    user, jeton = await creer_compte(db_session, "tous@example.com")
    await db_session.poser_membre(user.id, role)
    apres = await creer_organisation(db_session, "perm-org-5-apres")
    assert not await db_session.is_user_member_of_organization(user.id, apres)
    async with client_http() as c:
        r = await c.get("/api/v1/workflow/count", headers=entetes(jeton, apres))
    assert r.status_code == 200
    assert await db_session.is_user_member_of_organization(user.id, apres)


async def test_un_geste_d_ecriture_a_permission_est_ecrit_au_journal(db_session):
    org = await creer_organisation(db_session, "perm-org-6")
    role = await _role_avec(db_session, "Pub-test", ["agents.publier"])
    user, jeton = await creer_compte(db_session, "pub@example.com", organisations=[org])
    await db_session.poser_membre(user.id, role)
    async with client_http() as c:
        await c.post("/api/v1/workflow/999999/publish", headers=entetes(jeton, org), json={})
    lignes, _ = await db_session.lister_journal(limit=25, offset=0, organization_id=org)
    assert [ligne["action"] for ligne in lignes] == ["agents.publier"]
    assert lignes[0]["user_id"] == user.id
    assert lignes[0]["auteur"] == user.provider_id  # l'identifiant du compte, jamais l'adresse
    assert "pub@example.com" not in str(lignes[0])


async def test_une_route_sans_decision_est_refusee_meme_pour_un_administrateur(db_session, monkeypatch):
    org = await creer_organisation(db_session, "perm-org-7")
    _, jeton = await creer_compte(db_session, "adm@example.com", role="Administrateur", organisations=[org])
    monkeypatch.setattr(registre, "REGLES", ())
    async with client_http() as c:
        r = await c.get("/api/v1/workflow/count", headers=entetes(jeton, org))
    assert r.status_code == 403
    assert "decision" in r.json()["detail"]


async def test_une_cle_d_api_reste_dans_son_organisation(db_session):
    org_cle = await creer_organisation(db_session, "perm-org-8a")
    autre = await creer_organisation(db_session, "perm-org-8b")
    user, _ = await creer_compte(
        db_session, "cle@example.com", role="Administrateur", organisations=[org_cle, autre]
    )
    _, cle_en_clair = await db_session.create_api_key(org_cle, "test", user.id)
    async with client_http() as c:
        ok = await c.get("/api/v1/workflow/count", headers={"X-API-Key": cle_en_clair})
        deplacee = await c.get(
            "/api/v1/workflow/count",
            headers={"X-API-Key": cle_en_clair, "X-Mark-Organisation": str(autre)},
        )
    assert ok.status_code == 200
    assert deplacee.status_code == 403


async def test_une_cle_d_api_ecrit_sans_role_mais_jamais_les_gestes_de_l_equipe(db_session):
    org = await creer_organisation(db_session, "perm-org-9")
    createur, _ = await creer_compte(db_session, "createur-cle@example.com", organisations=[org])  # aucun rôle d'équipe
    _, cle = await db_session.create_api_key(org, "portail", createur.id)
    en_tete = {"X-API-Key": cle, "X-Mark-Auteur": "Lea"}
    async with client_http() as c:
        ecrit = await c.put("/api/v1/organizations/lexique", headers=en_tete, json={})  # RV : une écriture du portail (``portail.ecrire``)
        invite = await c.post(
            "/api/v1/equipe-mark/invitations", headers=en_tete, json={"email": "x@example.com", "role_id": 1}
        )
        espace = await c.put(f"/api/v1/espaces/{org}", headers=en_tete, json={"nom_affichage": "X"})
        nouveau = await c.post("/api/v1/organizations", headers=en_tete, json={"provider_id": "pirate"})
    assert ecrit.status_code == 200
    assert invite.status_code == 403 and espace.status_code == 403 and nouveau.status_code == 403
    lignes, _ = await db_session.lister_journal(limit=25, offset=0, organization_id=org)
    assert [ligne["action"] for ligne in lignes] == ["portail.ecrire"]  # RV2 (M-3) : la permission réellement requise de la clé
    assert lignes[0]["auteur"] == "portail : Lea"
