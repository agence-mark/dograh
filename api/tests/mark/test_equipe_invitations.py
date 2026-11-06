"""[.mark] builder partie 2, U2 ter, sous-lot 3 : invitations, premier compte, rôles, profil, dernier administrateur.

| Test | Ce qu'il prouve |
|---|---|
| de bout en bout | invitation, lien, page publique, compte créé avec le rôle, connexion, espaces ouverts, journal |
| jeton en empreinte | la base ne contient jamais le jeton, seulement son SHA-256 |
| lien réutilisé / périmé / inconnu | refusés (410), un mot de passe trop court ne brûle pas le lien |
| mail | part par le serveur de mail de l'installation s'il existe (simulé), sinon le lien est rendu |
| droit d'inviter | sans ``equipe.gerer``, 403 |
| inscription fermée | le premier compte d'une installation vide devient Administrateur, ensuite 403 |
| client créé après | un membre invité voit une organisation créée après lui |
| dernier administrateur | impossible à retirer ou rétrograder, possible dès qu'il y en a un autre |
| rôles | Administrateur fixe, nom unique, permission inconnue refusée, rôle utilisé non supprimable, rôle restreint retire les espaces |
| profil | rôle et permissions lus, nom modifiable, mot de passe (12 caractères, ancien exigé) |
"""

from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock, patch

import pytest
from sqlalchemy import text

from api.schemas.apres_appel import ReglagesInstallation, ReglagesSmtp
from api.services.equipe_mark import espaces
from api.services.equipe_mark.equipe import empreinte_du_jeton
from api.tests.mark.equipe_commun import (
    MOT_DE_PASSE,
    client_http,
    creer_compte,
    creer_organisation,
    entetes,
    sans_preparation_des_organisations,  # noqa: F401
)

pytestmark = pytest.mark.usefixtures("sans_preparation_des_organisations")

NOUVEAU_MDP = "un-autre-mot-de-passe-12"


@pytest.fixture(autouse=True)
def _cache_du_labo_propre():
    espaces.reinitialiser_cache()
    yield
    espaces.reinitialiser_cache()


def _jeton_du_lien(lien: str) -> str:
    return lien.split("jeton=", 1)[1]


async def _inviter(c, jeton_admin, email, role_id):
    return await c.post(
        "/api/v1/equipe-mark/invitations", headers=entetes(jeton_admin), json={"email": email, "role_id": role_id}
    )


async def _role_id(db, nom):
    return (await db.role_par_nom(nom))["id"]


async def test_invitation_de_bout_en_bout(db_session):
    org = await creer_organisation(db_session, "inv-org-1")
    _, jeton_admin = await creer_compte(db_session, "chef@example.com", role="Administrateur", organisations=[org])
    membre_id = await _role_id(db_session, "Membre")
    async with client_http() as c:
        cree = await _inviter(c, jeton_admin, "Pierre@Example.com", membre_id)
        assert cree.status_code == 201
        corps = cree.json()
        assert corps["email"] == "pierre@example.com"
        assert corps["envoye"] is False  # pas de serveur de mail réglé : le lien s'affiche à l'écran
        jeton = _jeton_du_lien(corps["lien"])

        lue = await c.get(f"/api/v1/auth/invitation/{jeton}")
        assert lue.status_code == 200
        corps_lu = lue.json()
        assert corps_lu["email"] == "pierre@example.com" and corps_lu["role_nom"] == "Membre"
        # Lot 15 (P-3) : la page dit qui invite (un compte sans nom : rien, jamais son adresse) et jusqu'à quand le lien vaut.
        assert corps_lu["invite_par"] is None and corps_lu["expire_le"]
        assert "chef@example.com" not in lue.text

        accepte = await c.post(
            f"/api/v1/auth/invitation/{jeton}/accepter",
            json={"prenom": "Pierre", "nom": "Martin", "mot_de_passe": MOT_DE_PASSE},
        )
        assert accepte.status_code == 200
        session = accepte.json()["token"]

        # Il se connecte avec son mot de passe, voit les espaces que son rôle ouvre, et son nom signe ses gestes.
        connexion = await c.post(
            "/api/v1/auth/login", json={"email": "pierre@example.com", "password": MOT_DE_PASSE}
        )
        assert connexion.status_code == 200
        espaces_ouverts = await c.get("/api/v1/espaces", headers=entetes(session))
        assert org in {e["id"] for e in espaces_ouverts.json()["espaces"]}
        moi = (await c.get("/api/v1/equipe-mark/moi", headers=entetes(session))).json()
        assert moi["role"] == "Membre" and moi["prenom"] == "Pierre" and "agents.modifier" in moi["permissions"]

        # Organisation créée APRÈS lui : visible sans geste de personne.
        apres = await creer_organisation(db_session, "inv-org-apres")
        espaces_apres = await c.get("/api/v1/espaces", headers=entetes(session))
        assert apres in {e["id"] for e in espaces_apres.json()["espaces"]}

        journal = (await c.get("/api/v1/equipe-mark/journal", headers=entetes(jeton_admin))).json()
    actions = [ligne["action"] for ligne in journal["lignes"]]
    assert "invitation.creer" in actions and "invitation.accepter" in actions
    assert "pierre@example.com" not in str(
        [ligne["detail"] for ligne in journal["lignes"] if ligne["action"] == "invitation.accepter"]
    ).replace("None", "")
    assert jeton not in str(journal)  # le jeton n'est jamais journalisé


async def test_la_base_ne_garde_que_l_empreinte_du_jeton(db_session):
    _, jeton_admin = await creer_compte(db_session, "chef2@example.com", role="Administrateur")
    async with client_http() as c:
        cree = await _inviter(c, jeton_admin, "x@example.com", await _role_id(db_session, "Membre"))
    jeton = _jeton_du_lien(cree.json()["lien"])
    async with db_session.async_session() as session:
        lignes = (await session.execute(text("SELECT empreinte_jeton FROM mark_invitations"))).scalars().all()
        tout = (await session.execute(text("SELECT row_to_json(t)::text FROM mark_invitations t"))).scalars().all()
    assert lignes == [empreinte_du_jeton(jeton)]
    assert jeton not in "".join(tout)
    assert len(lignes[0]) == 64


async def test_lien_reutilise_perime_ou_inconnu_refuse(db_session):
    _, jeton_admin = await creer_compte(db_session, "chef3@example.com", role="Administrateur")
    membre_id = await _role_id(db_session, "Membre")
    corps = {"prenom": "A", "nom": "B", "mot_de_passe": MOT_DE_PASSE}
    async with client_http() as c:
        jeton = _jeton_du_lien((await _inviter(c, jeton_admin, "a@example.com", membre_id)).json()["lien"])
        # Un mot de passe trop court est refusé SANS brûler le lien.
        court = await c.post(f"/api/v1/auth/invitation/{jeton}/accepter", json={**corps, "mot_de_passe": "court"})
        assert court.status_code == 422
        assert (await c.get(f"/api/v1/auth/invitation/{jeton}")).status_code == 200
        assert (await c.post(f"/api/v1/auth/invitation/{jeton}/accepter", json=corps)).status_code == 200
        # Réutilisé.
        assert (await c.get(f"/api/v1/auth/invitation/{jeton}")).status_code == 410
        assert (await c.post(f"/api/v1/auth/invitation/{jeton}/accepter", json=corps)).status_code == 410

        # Périmé (48 h passées).
        autre = _jeton_du_lien((await _inviter(c, jeton_admin, "b@example.com", membre_id)).json()["lien"])
        async with db_session.async_session() as session:
            await session.execute(
                text("UPDATE mark_invitations SET expire_le = :t WHERE email = 'b@example.com'"),
                {"t": datetime.now(UTC) - timedelta(seconds=1)},
            )
        assert (await c.get(f"/api/v1/auth/invitation/{autre}")).status_code == 410
        assert (await c.post(f"/api/v1/auth/invitation/{autre}/accepter", json=corps)).status_code == 410

        # Inconnu.
        assert (await c.get("/api/v1/auth/invitation/n-importe-quoi")).status_code == 410


async def test_le_mail_part_par_le_serveur_de_l_installation_sinon_le_lien_s_affiche(db_session):
    _, jeton_admin = await creer_compte(db_session, "chef4@example.com", role="Administrateur")
    membre_id = await _role_id(db_session, "Membre")
    reglages = ReglagesInstallation(
        smtp=ReglagesSmtp(hote="smtp.exemple.fr", expediteur="equipe@exemple.fr")
    )
    envoi = AsyncMock(return_value="<id>")
    with patch(
        "api.services.apres_appel.installation.lire_installation", new=AsyncMock(return_value=(1, reglages))
    ), patch("api.services.apres_appel.mail.envoyer", new=envoi):
        async with client_http() as c:
            cree = await _inviter(c, jeton_admin, "mail@example.com", membre_id)
    assert cree.json()["envoye"] is True
    envoi.assert_awaited_once()
    destinataires, _sujet, texte = envoi.await_args.args[2:5]
    assert destinataires == ["mail@example.com"]
    assert cree.json()["lien"] in texte


async def test_inviter_exige_la_permission(db_session):
    _, jeton_membre = await creer_compte(db_session, "simple@example.com", role="Membre")
    async with client_http() as c:
        r = await _inviter(c, jeton_membre, "z@example.com", await _role_id(db_session, "Membre"))
        liste = await c.get("/api/v1/equipe-mark/membres", headers=entetes(jeton_membre))
        role = await c.post(
            "/api/v1/equipe-mark/roles", headers=entetes(jeton_membre), json={"nom": "Pirate", "permissions": ["equipe.gerer"]}
        )
    assert r.status_code == 403 and liste.status_code == 403 and role.status_code == 403


async def test_inscription_fermee_apres_le_premier_compte(db_session):
    corps = {"email": "premier@example.com", "password": "un-mot-de-passe-long-12", "name": "Premier"}
    with patch("api.routes.auth.ensure_organization_bootstrapped", new=AsyncMock(return_value=True)):
        async with client_http() as c:
            premier = await c.post("/api/v1/auth/signup", json=corps)
            second = await c.post("/api/v1/auth/signup", json={**corps, "email": "second@example.com"})
    assert premier.status_code == 200
    assert second.status_code == 403
    membre = await db_session.obtenir_membre(premier.json()["user"]["id"])
    assert membre["role_nom"] == "Administrateur"
    assert await db_session.get_user_by_email("second@example.com") is None
    # L'organisation du premier compte est celle de l'installation : le Labo.
    assert await db_session.organisation_marquee_labo("MARK_ESPACE") == premier.json()["user"]["organization_id"]


async def test_le_drapeau_ferme_aussi_le_premier_compte(db_session, monkeypatch):
    import api.routes.auth as routes_auth

    monkeypatch.setattr(routes_auth, "ENABLE_SIGNUP", False)
    async with client_http() as c:
        r = await c.post("/api/v1/auth/signup", json={"email": "p@example.com", "password": MOT_DE_PASSE})
    assert r.status_code == 403


async def test_le_dernier_administrateur_ne_se_retire_pas_ni_ne_se_retrograde(db_session):
    unique, jeton = await creer_compte(db_session, "seul@example.com", role="Administrateur")
    membre_id = await _role_id(db_session, "Membre")
    async with client_http() as c:
        retrait = await c.delete(f"/api/v1/equipe-mark/membres/{unique.id}", headers=entetes(jeton))
        degrade = await c.put(
            f"/api/v1/equipe-mark/membres/{unique.id}/role", headers=entetes(jeton), json={"role_id": membre_id}
        )
        assert retrait.status_code == 409 and degrade.status_code == 409
        assert (await db_session.obtenir_membre(unique.id))["role_nom"] == "Administrateur"

        # Un autre administrateur existe : le premier peut partir.
        autre, _ = await creer_compte(db_session, "second-adm@example.com", role="Administrateur")
        ok = await c.delete(f"/api/v1/equipe-mark/membres/{unique.id}", headers=entetes(jeton))
    assert ok.status_code == 204
    assert await db_session.obtenir_membre(unique.id) is None
    assert (await db_session.obtenir_membre(autre.id))["role_nom"] == "Administrateur"


async def test_les_roles(db_session):
    org = await creer_organisation(db_session, "inv-role-org")
    autre_org = await creer_organisation(db_session, "inv-role-autre")
    _, jeton = await creer_compte(db_session, "roles@example.com", role="Administrateur", organisations=[org, autre_org])
    admin_id = await _role_id(db_session, "Administrateur")
    async with client_http() as c:
        h = entetes(jeton)
        assert (await c.put(f"/api/v1/equipe-mark/roles/{admin_id}", headers=h, json={"nom": "Autre", "permissions": []})).status_code == 403
        assert (await c.delete(f"/api/v1/equipe-mark/roles/{admin_id}", headers=h)).status_code == 403
        inconnue = await c.post("/api/v1/equipe-mark/roles", headers=h, json={"nom": "X", "permissions": ["tout.faire"]})
        assert inconnue.status_code == 422
        cree = await c.post(
            "/api/v1/equipe-mark/roles",
            headers=h,
            json={"nom": "Freelance", "permissions": ["conversations.voir"], "organisations": [org, autre_org]},
        )
        assert cree.status_code == 201
        role_id = cree.json()["id"]
        doublon = await c.post("/api/v1/equipe-mark/roles", headers=h, json={"nom": "freelance", "permissions": []})
        assert doublon.status_code == 409

        # Un membre de ce rôle voit les deux clients ; le rôle est restreint : il n'en voit plus qu'un.
        invite = _jeton_du_lien((await _inviter(c, jeton, "free@example.com", role_id)).json()["lien"])
        session = (
            await c.post(
                f"/api/v1/auth/invitation/{invite}/accepter",
                json={"prenom": "F", "nom": "R", "mot_de_passe": MOT_DE_PASSE},
            )
        ).json()["token"]
        avant = {e["id"] for e in (await c.get("/api/v1/espaces", headers=entetes(session))).json()["espaces"]}
        assert {org, autre_org} <= avant
        restreint = await c.put(
            f"/api/v1/equipe-mark/roles/{role_id}",
            headers=h,
            json={"nom": "Freelance", "permissions": ["conversations.voir"], "organisations": [org]},
        )
        assert restreint.status_code == 200
        apres = {e["id"] for e in (await c.get("/api/v1/espaces", headers=entetes(session))).json()["espaces"]}
        assert org in apres and autre_org not in apres
        assert (await c.get("/api/v1/workflow/count", headers=entetes(session, autre_org))).status_code == 403

        # Un rôle qui a des membres ne se supprime pas.
        assert (await c.delete(f"/api/v1/equipe-mark/roles/{role_id}", headers=h)).status_code == 409


async def test_le_profil(db_session):
    user, jeton = await creer_compte(db_session, "profil@example.com", role="Membre")
    async with client_http() as c:
        h = entetes(jeton)
        moi = (await c.get("/api/v1/equipe-mark/moi", headers=h)).json()
        assert moi["role"] == "Membre" and moi["langue"] == "fr" and moi["alertes_mail"] is True
        change = await c.patch(
            "/api/v1/equipe-mark/moi", headers=h, json={"prenom": "Léa", "nom": "Durand", "langue": "en", "alertes_mail": False}
        )
        assert change.status_code == 200
        assert (change.json()["prenom"], change.json()["langue"], change.json()["alertes_mail"]) == ("Léa", "en", False)
        assert (await c.patch("/api/v1/equipe-mark/moi", headers=h, json={"langue": "de"})).status_code == 422

        faux = await c.post("/api/v1/equipe-mark/moi/mot-de-passe", headers=h, json={"actuel": "faux", "nouveau": NOUVEAU_MDP})
        court = await c.post("/api/v1/equipe-mark/moi/mot-de-passe", headers=h, json={"actuel": MOT_DE_PASSE, "nouveau": "court"})
        bon = await c.post("/api/v1/equipe-mark/moi/mot-de-passe", headers=h, json={"actuel": MOT_DE_PASSE, "nouveau": NOUVEAU_MDP})
        assert (faux.status_code, court.status_code, bon.status_code) == (403, 422, 204)
        assert (await c.post("/api/v1/auth/login", json={"email": "profil@example.com", "password": NOUVEAU_MDP})).status_code == 200
        assert (await c.post("/api/v1/auth/login", json={"email": "profil@example.com", "password": MOT_DE_PASSE})).status_code == 401
    assert user.id


async def test_la_liste_des_membres_dit_depuis_quand_chacun_est_dans_l_equipe(db_session):
    # V4 : la colonne « Depuis » de la page Équipe vient de ``mark_membres.cree_le`` (jamais d'une date inventée à l'écran).
    _, jeton = await creer_compte(db_session, "ancien@example.com", role="Administrateur")
    async with client_http() as c:
        liste = await c.get("/api/v1/equipe-mark/membres", headers=entetes(jeton))
    assert liste.status_code == 200, liste.text
    [membre] = [m for m in liste.json()["membres"] if m["email"] == "ancien@example.com"]
    from datetime import datetime, timedelta, timezone

    entree = datetime.fromisoformat(membre["depuis"].replace("Z", "+00:00"))
    assert entree.tzinfo is not None and abs(datetime.now(timezone.utc) - entree) < timedelta(minutes=5)
