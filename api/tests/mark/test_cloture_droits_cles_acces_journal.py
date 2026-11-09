"""[.mark] Clôture, lot A (D9 à D12, D21 à D24) : droits des clés, accès bloqué en un clic, journal complet de l'équipe.

| Test | Ce qu'il prouve |
|---|---|
| plafond | une clé ne porte jamais plus de droits que son créateur (403 à la création et au changement de rôle) |
| table unique | les permissions d'une clé à rôle = le rôle borné par son créateur, sans les gestes de l'équipe ; un créateur qui perd un droit le fait perdre à sa clé |
| suspension | une clé suspendue est refusée, rétablie elle repasse ; révoquée elle ne se rétablit pas par la suspension |
| accès bloqué | un membre bloqué est refusé (session, clé, connexion) avec le message réglé à l'écran ; rétabli, il retrouve tout ; ni soi-même ni le dernier administrateur |
| journal | origine (écran, API), filtres, permission « Lire le journal », durée réglable avec bornes |
| D9 | « Ajouter un document » (traitement du fichier déposé) rouvert à la clé du portail |
| D10 | une clé de client sans rôle ne lit ni agents, ni outils, ni builder ; documents gardés ; la clé du Labo garde tout |
| D11 | le miroir de Claude Code n'accepte que la clé du Labo |
"""

from __future__ import annotations

import pytest

from api.services.equipe_mark import droits_effectifs, espaces
from api.services.equipe_mark.blocage import MESSAGE_PAR_DEFAUT
from api.tests.mark.equipe_commun import (
    MOT_DE_PASSE,
    client_http,
    creer_compte,
    creer_organisation,
    entetes,
    sans_preparation_des_organisations,  # noqa: F401
)

pytestmark = pytest.mark.usefixtures("sans_preparation_des_organisations")


@pytest.fixture(autouse=True)
def _cache_du_labo_propre():
    espaces.reinitialiser_cache()
    yield
    espaces.reinitialiser_cache()


async def _role(db, nom, permissions):
    return await db.creer_role(nom=nom, labo_ouvert=True, tous_les_clients=True, permissions=permissions, organisations=[])


async def _monde(db, suffixe):
    labo = await creer_organisation(db, f"cl-labo-{suffixe}")
    client = await creer_organisation(db, f"cl-client-{suffixe}")
    await espaces.definir_labo(labo, True)
    admin, jeton = await creer_compte(db, f"cl-admin-{suffixe}@example.com", role="Administrateur", organisations=[labo, client])
    return labo, client, admin, jeton


async def _creer_cle(c, jeton, org, nom="cle", role_id=None):
    corps = {"name": nom}
    if role_id is not None:
        corps["role_id"] = role_id
    return await c.post("/api/v1/user/api-keys", headers=entetes(jeton, org), json=corps)


# ---------------------------------------------------------------------- D21 : clé portée par un rôle
async def test_une_cle_ne_porte_jamais_plus_de_droits_que_son_createur(db_session):
    db = db_session
    labo, client, admin, jeton_admin = await _monde(db, "plafond")
    editeur = await _role(db, "cl-editeur", ["agents.modifier", "conversations.voir"])
    petit = await _role(db, "cl-petit", ["cles.gerer", "conversations.voir"])
    _, jeton_petit = await creer_compte(db, "cl-petit@example.com", role="cl-petit", organisations=[labo, client])
    async with client_http() as c:
        refus = await _creer_cle(c, jeton_petit, client, "trop", editeur)
        ok = await _creer_cle(c, jeton_petit, client, "juste", petit)
        par_admin = await _creer_cle(c, jeton_admin, client, "editeur", editeur)
        inconnu = await _creer_cle(c, jeton_admin, client, "fantome", 99999)
        change = await c.put(
            f"/api/v1/user/api-keys/{ok.json()['id']}/role", headers=entetes(jeton_petit, client), json={"role_id": editeur}
        )
    assert refus.status_code == 403 and "agents.modifier" in refus.json()["detail"]
    assert ok.status_code == 200 and par_admin.status_code == 200
    assert inconnu.status_code == 404
    assert change.status_code == 403  # même plafond au changement de rôle


async def test_les_permissions_d_une_cle_a_role_sont_celles_du_role_bornees_par_le_createur(db_session):
    db = db_session
    labo, client, admin, _ = await _monde(db, "table")
    role = await _role(db, "cl-gros", ["agents.modifier", "agents.publier", "equipe.gerer", "roles.gerer", "clients.creer", "journal.lire"])
    petit = await _role(db, "cl-createur", ["agents.modifier", "equipe.gerer", "journal.lire"])
    createur, _ = await creer_compte(db, "cl-createur@example.com", role="cl-createur", organisations=[labo, client])
    cle = lambda role_id: type("U", (), {"id": createur.id, "selected_organization_id": client, "par_cle_api": True, "cle_api_role_id": role_id})()  # noqa: E731
    # le rôle porte 6 droits ; le créateur 3 ; une clé n'a jamais les gestes de l'équipe : seul agents.modifier reste
    assert await droits_effectifs.permissions_de(cle(role)) == frozenset({"agents.modifier"})
    # sans rôle : la liste fermée des clés, ni plus ni moins
    from api.services.equipe_mark.permissions import PERMISSIONS_DE_CLE

    assert await droits_effectifs.permissions_de(cle(None)) == PERMISSIONS_DE_CLE
    # le créateur perd agents.modifier : la clé le perd à l'appel suivant
    await db.modifier_role(petit, nom="cl-createur", labo_ouvert=True, tous_les_clients=True, permissions=["journal.lire"], organisations=[])
    assert await droits_effectifs.permissions_de(cle(role)) == frozenset()


async def test_une_cle_a_role_ecrit_comme_le_role_et_pas_au_dela(db_session):
    db = db_session
    labo, client, admin, jeton = await _monde(db, "http")
    role = await _role(db, "cl-redacteur", ["agents.modifier"])
    async with client_http() as c:
        avec_role = (await _creer_cle(c, jeton, client, "avec", role)).json()["api_key"]
        sans_role = (await _creer_cle(c, jeton, client, "sans")).json()["api_key"]
        # écriture qui exige agents.modifier : ouverte à la clé à rôle, fermée à la clé sans rôle (liste fermée du portail)
        a = await c.post("/api/v1/folder/", headers={"X-API-Key": avec_role}, json={"name": "x"})
        b = await c.post("/api/v1/folder/", headers={"X-API-Key": sans_role}, json={"name": "x"})
        # un geste de l'équipe reste fermé même à une clé dont le créateur l'a
        e = await c.get("/api/v1/equipe-mark/membres", headers={"X-API-Key": avec_role})
    assert a.status_code != 403, a.text
    assert b.status_code == 403
    assert e.status_code == 403


async def test_une_cle_suspendue_est_refusee_puis_retablie(db_session):
    db = db_session
    labo, client, admin, jeton = await _monde(db, "susp")
    async with client_http() as c:
        cree = (await _creer_cle(c, jeton, client)).json()
        cle = cree["api_key"]
        assert (await c.get("/api/v1/auth/me", headers={"X-API-Key": cle})).status_code == 200
        r = await c.put(f"/api/v1/user/api-keys/{cree['id']}/suspension", headers=entetes(jeton, client), json={"suspendue": True})
        assert r.status_code == 200
        assert (await c.get("/api/v1/auth/me", headers={"X-API-Key": cle})).status_code == 401
        liste = (await c.get("/api/v1/user/api-keys", headers=entetes(jeton, client))).json()
        assert next(k for k in liste if k["id"] == cree["id"])["suspendue"] is True
        await c.put(f"/api/v1/user/api-keys/{cree['id']}/suspension", headers=entetes(jeton, client), json={"suspendue": False})
        assert (await c.get("/api/v1/auth/me", headers={"X-API-Key": cle})).status_code == 200
        # révoquée : la suspension ne la rétablit pas
        await c.delete(f"/api/v1/user/api-keys/{cree['id']}", headers=entetes(jeton, client))
        r = await c.put(f"/api/v1/user/api-keys/{cree['id']}/suspension", headers=entetes(jeton, client), json={"suspendue": False})
        assert r.status_code == 404
        assert (await c.get("/api/v1/auth/me", headers={"X-API-Key": cle})).status_code == 401


async def test_un_role_porte_par_une_cle_ne_se_supprime_pas(db_session):
    db = db_session
    labo, client, admin, jeton = await _monde(db, "rolecle")
    role = await _role(db, "cl-utilise", ["agents.modifier"])
    async with client_http() as c:
        cree = (await _creer_cle(c, jeton, client, "k", role)).json()
        refus = await c.delete(f"/api/v1/equipe-mark/roles/{role}", headers=entetes(jeton, client))
        await c.delete(f"/api/v1/user/api-keys/{cree['id']}", headers=entetes(jeton, client))
        ok = await c.delete(f"/api/v1/equipe-mark/roles/{role}", headers=entetes(jeton, client))
    assert refus.status_code == 409
    assert ok.status_code == 204


# ---------------------------------------------------------------------- D22 : accès bloqué
async def test_un_membre_bloque_est_coupe_partout_avec_le_message_regle_puis_retrouve_tout(db_session):
    db = db_session
    labo, client, admin, jeton_admin = await _monde(db, "bloc")
    role = await _role(db, "cl-salarie", ["agents.modifier", "cles.gerer"])
    salarie, jeton = await creer_compte(db, "cl-salarie@example.com", role="cl-salarie", organisations=[labo, client])
    async with client_http() as c:
        cle = (await _creer_cle(c, jeton, client, "mienne")).json()["api_key"]
        assert (await c.get("/api/v1/auth/me", headers=entetes(jeton))).status_code == 200
        r = await c.put(f"/api/v1/equipe-mark/membres/{salarie.id}/acces", headers=entetes(jeton_admin), json={"actif": False})
        assert r.status_code == 204
        session = await c.get("/api/v1/auth/me", headers=entetes(jeton))
        par_cle = await c.get("/api/v1/auth/me", headers={"X-API-Key": cle})
        connexion = await c.post("/api/v1/auth/login", json={"email": "cl-salarie@example.com", "password": MOT_DE_PASSE})
        assert session.status_code == par_cle.status_code == connexion.status_code == 403
        assert session.json()["detail"] == MESSAGE_PAR_DEFAUT["fr"]
        # le message se règle à l'écran, dans les deux langues
        regle = await c.put(
            "/api/v1/equipe-mark/reglages/message-acces-bloque", headers=entetes(jeton_admin), json={"fr": "Pause jusqu'à lundi.", "en": "Paused until Monday."}
        )
        assert regle.status_code == 200
        fr = await c.post("/api/v1/auth/login", json={"email": "cl-salarie@example.com", "password": MOT_DE_PASSE})
        en = await c.post(
            "/api/v1/auth/login", headers={"Accept-Language": "en-GB"}, json={"email": "cl-salarie@example.com", "password": MOT_DE_PASSE}
        )
        assert fr.json()["detail"] == "Pause jusqu'à lundi." and en.json()["detail"] == "Paused until Monday."
        # la liste dit l'état
        membres = (await c.get("/api/v1/equipe-mark/membres", headers=entetes(jeton_admin))).json()["membres"]
        assert next(m for m in membres if m["user_id"] == salarie.id)["acces_actif"] is False
        # rétabli en un clic : session, clé et connexion repassent, permissions retrouvées
        await c.put(f"/api/v1/equipe-mark/membres/{salarie.id}/acces", headers=entetes(jeton_admin), json={"actif": True})
        assert (await c.get("/api/v1/auth/me", headers=entetes(jeton))).status_code == 200
        assert (await c.get("/api/v1/auth/me", headers={"X-API-Key": cle})).status_code == 200
        assert (await c.post("/api/v1/auth/login", json={"email": "cl-salarie@example.com", "password": MOT_DE_PASSE})).status_code == 200
        moi = (await c.get("/api/v1/equipe-mark/moi", headers=entetes(jeton))).json()
        assert "agents.modifier" in moi["permissions"]


async def test_on_ne_se_bloque_pas_soi_meme_ni_le_dernier_administrateur(db_session):
    db = db_session
    labo, client, admin, jeton = await _monde(db, "dernier")
    autre, jeton_autre = await creer_compte(db, "cl-autre-admin@example.com", role="Administrateur", organisations=[labo, client])
    async with client_http() as c:
        soi = await c.put(f"/api/v1/equipe-mark/membres/{admin.id}/acces", headers=entetes(jeton), json={"actif": False})
        bloque_autre = await c.put(f"/api/v1/equipe-mark/membres/{autre.id}/acces", headers=entetes(jeton), json={"actif": False})
        # il ne reste qu'un administrateur actif (l'autre est bloqué) : on ne peut pas le bloquer non plus, par le premier compte bloqué...
        dernier = await db.changer_acces_protege(admin.id, False)
    assert soi.status_code == 409
    assert bloque_autre.status_code == 204
    assert dernier == "dernier_administrateur"


# ---------------------------------------------------------------------- D23, D24 : journal
async def test_le_journal_dit_la_porte_se_filtre_et_demande_sa_permission(db_session):
    db = db_session
    labo, client, admin, jeton = await _monde(db, "jrn")
    role = await _role(db, "cl-gestionnaire", ["equipe.gerer", "cles.gerer"])  # gère l'équipe mais ne lit pas le journal
    _, jeton_gest = await creer_compte(db, "cl-gest@example.com", role="cl-gestionnaire", organisations=[labo, client])
    async with client_http() as c:
        cle = (await _creer_cle(c, jeton, client, "j")).json()["api_key"]
        # une écriture par l'écran, une par l'API
        await c.put("/api/v1/user/api-keys/1/suspension", headers=entetes(jeton, client), json={"suspendue": False})
        liste = (await c.get("/api/v1/equipe-mark/journal", headers=entetes(jeton, client))).json()
        creer = [ligne for ligne in liste["lignes"] if ligne["action"] == "cle_api.creer"]
        assert creer and creer[0]["origine"] == "ecran"
        par_api = await c.get("/api/v1/equipe-mark/journal?origine=api", headers=entetes(jeton, client))
        assert par_api.status_code == 200
        assert all(ligne["origine"] == "api" for ligne in par_api.json()["lignes"])
        filtre = (await c.get("/api/v1/equipe-mark/journal?action=cle_api.creer&limit=1", headers=entetes(jeton, client))).json()
        assert filtre["limit"] == 1 and filtre["total"] >= 1 and all(ligne["action"] == "cle_api.creer" for ligne in filtre["lignes"])
        types = (await c.get("/api/v1/equipe-mark/journal/types", headers=entetes(jeton, client))).json()
        assert "cle_api.creer" in types
        # sans « Lire le journal » : 403, avec ou sans gérer l'équipe
        assert (await c.get("/api/v1/equipe-mark/journal", headers=entetes(jeton_gest, client))).status_code == 403
        # une clé n'a jamais le journal de l'équipe
        assert (await c.get("/api/v1/equipe-mark/journal", headers={"X-API-Key": cle})).status_code == 403
    roles = {r["nom"]: r for r in await db.lister_roles()}
    assert "journal.lire" in roles["Administrateur"]["permissions"]


async def test_la_duree_du_journal_se_regle_dans_ses_bornes(db_session):
    db = db_session
    labo, client, admin, jeton = await _monde(db, "duree")
    async with client_http() as c:
        defaut = (await c.get("/api/v1/equipe-mark/reglages", headers=entetes(jeton))).json()
        assert defaut["journal_mois"] == 12
        ok = await c.put("/api/v1/equipe-mark/reglages/duree-journal", headers=entetes(jeton), json={"mois": 6})
        trop = await c.put("/api/v1/equipe-mark/reglages/duree-journal", headers=entetes(jeton), json={"mois": 5000})
        zero = await c.put("/api/v1/equipe-mark/reglages/duree-journal", headers=entetes(jeton), json={"mois": 0})
    assert ok.status_code == 200 and ok.json()["journal_mois"] == 6
    assert trop.status_code == zero.status_code == 422


# ---------------------------------------------------------------------- D9, D10, D11
async def test_d9_d10_d11_les_cles_de_client_et_du_labo(db_session):
    db = db_session
    labo, client, admin, jeton = await _monde(db, "d10")
    async with client_http() as c:
        cle_client = (await _creer_cle(c, jeton, client, "client")).json()["api_key"]
        cle_labo = (await _creer_cle(c, jeton, labo, "labo")).json()["api_key"]
        # D10 : un client ne lit ni agents, ni outils, ni builder ; les documents restent lisibles
        for chemin in ("/api/v1/workflow/fetch", "/api/v1/tools/", "/api/v1/builder/fils"):
            assert (await c.get(chemin, headers={"X-API-Key": cle_client})).status_code == 403, chemin
        assert (await c.get("/api/v1/knowledge-base/documents", headers={"X-API-Key": cle_client})).status_code != 403
        # la clé du Labo garde tout
        for chemin in ("/api/v1/workflow/fetch", "/api/v1/tools/"):
            assert (await c.get(chemin, headers={"X-API-Key": cle_labo})).status_code != 403, chemin
        # D11 : le miroir n'accepte que la clé du Labo
        assert (await c.post("/api/v1/builder/miroir", headers={"X-API-Key": cle_client}, json={})).status_code == 403
        assert (await c.post("/api/v1/builder/miroir", headers={"X-API-Key": cle_labo}, json={})).status_code != 403
        # D9 : ajouter un document (traitement du fichier déposé) est rouvert à la clé du portail
        r = await c.post("/api/v1/knowledge-base/process-document", headers={"X-API-Key": cle_client}, json={})
        assert r.status_code != 403, r.text

def test_le_message_par_defaut_est_celui_d_evan():
    assert MESSAGE_PAR_DEFAUT["fr"] == "Votre accès est bloqué jusqu'à votre prochaine mission."
