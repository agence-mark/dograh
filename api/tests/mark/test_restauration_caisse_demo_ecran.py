"""[.mark] Module Restauration, lot 20, étape 5 : les routes de l'écran Outils › Simulateurs › Caisse / POS et les scénarios.

Vraie authentification (compte d'équipe), vraies bases de clients, vrai Redis. Aucun réseau.

| Test | Ce qu'il prouve |
|---|---|
| garde | éteinte ou hors Labo : 404 partout (état « inactive » pour l'écran), rien n'est créé ; sans compte : 401 |
| restaurants | création, réglage (liste fermée refusée en 422), copie, suppression ; un restaurant d'une autre organisation : 404 ; le jeton n'est jamais rendu |
| scénarios | les neuf livrés (six du plan, trois de la maquette) sont versés une fois, sans rien écraser ; mettre en place change état et comportement ; enregistrer les réglages en cours ; supprimer ; un nom livré n'est pas écrasé |
| carte | un fichier au format commun remplace la carte ; un fichier invalide est refusé sans rien écrire |
| gestes | rupture, prix, état, statut par la caisse : message signé écrit ; un code inconnu : 422 |
| réservation | la réservation que CET essai a faite (même appel, même établissement) est rendue à la fenêtre : heure, couverts, état, tables, jamais le prénom ni le numéro ; un autre appel, un autre établissement, une autre organisation : 404 |
| branchement | brancher relie le restaurant à l'établissement du Labo (liaison « ok » et carte importée), débrancher libère ; supprimer le restaurant libère le point de vente |
| permissions | chaque route est au registre : lire = voir les conversations, écrire = modifier un agent |
"""

from __future__ import annotations

import uuid

import pytest

from api.db import db_client
from api.db.bases_clients import connexion as schema
from api.db.bases_clients import restauration_liaison as lia
from api.services.equipe_mark import registre_routes as registre
from api.services.restauration.caisse.caisse_demo import garde, scenarios
from api.tests.mark.equipe_commun import client_http, creer_compte, entetes, sans_preparation_des_organisations  # noqa: F401
from api.tests.mark.test_base_client import base_essai  # noqa: F401
from api.tests.mark.test_contacts_portail import seconde_base  # noqa: F401
from api.tests.mark.test_restauration_caisse_routes import _corps
from api.tests.mark.test_restauration_flux import _deux_organisations_avec_des_etablissements
from api.services.restauration.caisse.prises import hubrise_traduction as ht

RACINE = "/api/v1/restauration/caisse-demo"
SECRET = "secret-de-notre-application"


@pytest.fixture
def demo_allumee(monkeypatch):
    monkeypatch.setenv("CAISSE_DEMO_ACTIVE", "1")
    monkeypatch.setenv("HUBRISE_CLIENT_ID", "id-de-notre-application")
    monkeypatch.setenv("HUBRISE_CLIENT_SECRET", SECRET)


async def _cas(db_session, seconde_base, monkeypatch, *, labo: str = "a"):  # noqa: F811
    cas = await _deux_organisations_avec_des_etablissements(db_session, seconde_base)
    voulu = {"a": cas.a, "b": cas.b, None: -1}[labo]

    async def est_labo(o):
        return o == voulu

    monkeypatch.setattr(garde, "organisation_est_labo", est_labo)
    _, jeton = await creer_compte(db_session, f"demo-{uuid.uuid4().hex[:8]}@example.com", role="Administrateur", organisations=[cas.a])
    cas.session = entetes(jeton)
    return cas


async def test_eteinte_ou_hors_labo_la_caisse_de_demo_n_existe_pas(db_session, seconde_base, sans_preparation_des_organisations, monkeypatch):  # noqa: F811
    cas = await _cas(db_session, seconde_base, monkeypatch, labo="b")  # le compte est dans A, le Labo est B
    monkeypatch.setenv("CAISSE_DEMO_ACTIVE", "1")
    async with client_http() as c:
        assert (await c.get(f"{RACINE}/etat")).status_code == 401
        assert (await c.get(f"{RACINE}/etat", headers=cas.session)).json()["active"] is False
        assert (await c.get(f"{RACINE}/restaurants", headers=cas.session)).status_code == 404
        assert (await c.post(f"{RACINE}/restaurants", json={"nom": "X"}, headers=cas.session)).status_code == 404
        monkeypatch.delenv("CAISSE_DEMO_ACTIVE")
        _labo_a = cas.a

        async def est_labo(o):
            return o == _labo_a

        monkeypatch.setattr(garde, "organisation_est_labo", est_labo)
        assert (await c.get(f"{RACINE}/etat", headers=cas.session)).json()["active"] is False  # Labo, mais interrupteur éteint
        assert (await c.get(f"{RACINE}/restaurants", headers=cas.session)).status_code == 404
    assert await db_client.lister_restaurants_de_demo(cas.a) == [] and await db_client.lister_restaurants_de_demo(cas.b) == []


async def test_creer_regler_dupliquer_supprimer_un_restaurant_de_test(db_session, seconde_base, sans_preparation_des_organisations, demo_allumee, monkeypatch):  # noqa: F811
    cas = await _cas(db_session, seconde_base, monkeypatch)
    async with client_http() as c:
        assert (await c.get(f"{RACINE}/etat", headers=cas.session)).json()["active"] is True
        cree = await c.post(f"{RACINE}/restaurants", json={"nom": "Pizzeria test", "scenario": "restaurant-deborde"}, headers=cas.session)
        assert cree.status_code == 200, cree.text
        r = cree.json()
        assert (r["etat"], r["minutes_en_plus"], r["scenario"], r["branche"]) == ("deborde", 20, "restaurant-deborde", False)
        assert "jeton" not in str(r).lower() and "empreinte" not in str(r).lower()
        rid = r["id"]
        for mauvais in ({"etat": "explose"}, {"minutes_en_plus": 999}, {"comportement": {"reponse": "piege"}}, {"inconnu": 1}):
            assert (await c.put(f"{RACINE}/restaurants/{rid}", json=mauvais, headers=cas.session)).status_code == 422, mauvais
        assert (await c.put(f"{RACINE}/restaurants/{rid}", json={"reglages": {"inconnu": 1}}, headers=cas.session)).status_code == 422
        ok = await c.put(f"{RACINE}/restaurants/{rid}", json={"nom": "Renommé", "etat": "ferme", "comportement": {"reponse": "controle", "controles": ["ferme"]}}, headers=cas.session)
        assert ok.status_code == 200 and (ok.json()["nom"], ok.json()["etat"], ok.json()["comportement"]["reponse"]) == ("Renommé", "ferme", "controle")
        copie = (await c.post(f"{RACINE}/restaurants/{rid}/dupliquer", headers=cas.session)).json()
        assert copie["id"] != rid and copie["nom"] == "Renommé (copie)" and copie["etat"] == "ferme"
        liste = (await c.get(f"{RACINE}/restaurants", headers=cas.session)).json()
        assert {x["id"] for x in liste["restaurants"]} == {rid, copie["id"]} and len(liste["scenarios"]) == 9
        assert (await c.delete(f"{RACINE}/restaurants/{copie['id']}", headers=cas.session)).status_code == 200
        assert (await c.get(f"{RACINE}/restaurants/{copie['id']}", headers=cas.session)).status_code == 404
        # le restaurant d'une autre organisation : introuvable
        chez_b = await db_client.creer_restaurant_de_demo(cas.b, "Chez B", "pdv-chez-b-0", __import__("datetime").datetime(2026, 11, 15, tzinfo=__import__("datetime").UTC))
        base_b = f"{RACINE}/restaurants/{chez_b['id']}"
        assert (await c.get(base_b, headers=cas.session)).status_code == 404
        assert (await c.put(base_b, json={"nom": "x"}, headers=cas.session)).status_code == 404
        assert (await c.delete(base_b, headers=cas.session)).status_code == 404
        assert (await c.post(base_b + "/dupliquer", headers=cas.session)).status_code == 404
        assert (await c.post(base_b + "/gestes", json={"geste": "etat", "etat": "ferme"}, headers=cas.session)).status_code == 404
        assert (await c.post(base_b + "/brancher", json={"etablissement_id": cas.sites_a[0]}, headers=cas.session)).status_code == 404
        assert (await c.get(f"{RACINE}/restaurants/{chez_b['id']}", headers=cas.session)).status_code == 404
    assert (await db_client.lire_restaurant_de_demo(cas.b, chez_b["id"]))["nom"] == "Chez B"


async def test_les_neuf_scenarios_livres_sont_verses_une_fois_et_se_mettent_en_place(db_session, seconde_base, sans_preparation_des_organisations, demo_allumee, monkeypatch):  # noqa: F811
    cas = await _cas(db_session, seconde_base, monkeypatch)
    async with client_http() as c:
        liste = (await c.get(f"{RACINE}/restaurants", headers=cas.session)).json()
        assert sorted(s["cle"] for s in liste["scenarios"]) == sorted(scenarios.LIVRES) and len(scenarios.LIVRES) == 9
        r = (await c.post(f"{RACINE}/restaurants", json={"nom": "Scénarios"}, headers=cas.session)).json()
        # une modification d'un scénario livré n'est jamais écrasée par une nouvelle livraison
        await scenarios.enregistrer(cas.a, r["id"], "Mon scénario")
        await scenarios.livrer(cas.a)
        await scenarios.livrer(cas.a)
        cles = sorted((await scenarios.lire(cas.a)))
        assert len(cles) == 10 and "mon-scenario" in cles
        muette = (await c.post(f"{RACINE}/restaurants/{r['id']}/scenario", json={"scenario": "caisse-muette"}, headers=cas.session)).json()
        assert (muette["comportement"]["reponse"], muette["scenario"]) == ("silence", "caisse-muette")
        stricte = (await c.post(f"{RACINE}/restaurants/{r['id']}/scenario", json={"scenario": "caisse-stricte"}, headers=cas.session)).json()
        assert stricte["comportement"]["reponse"] == "controle" and len(stricte["comportement"]["controles"]) == 4
        assert (await c.post(f"{RACINE}/restaurants/{r['id']}/scenario", json={"scenario": "n-existe-pas"}, headers=cas.session)).status_code == 404
        # enregistrer les réglages en cours, puis les remettre
        await c.put(f"{RACINE}/restaurants/{r['id']}", json={"etat": "deborde", "minutes_en_plus": 35, "comportement": {"acceptation": "refus"}}, headers=cas.session)
        cle = (await c.post(f"{RACINE}/restaurants/{r['id']}/scenarios", json={"nom": "Soir de rush"}, headers=cas.session)).json()["cle"]
        assert cle == "soir-de-rush"
        assert (await c.post(f"{RACINE}/restaurants/{r['id']}/scenarios", json={"nom": "Caisse stricte"}, headers=cas.session)).status_code == 422  # un nom livré n'est pas écrasé
        await c.post(f"{RACINE}/restaurants/{r['id']}/scenario", json={"scenario": "tout-va-bien"}, headers=cas.session)
        remis = (await c.post(f"{RACINE}/restaurants/{r['id']}/scenario", json={"scenario": cle}, headers=cas.session)).json()
        assert (remis["etat"], remis["minutes_en_plus"], remis["comportement"]) == ("deborde", 35, {"acceptation": "refus"})
        assert (await c.delete(f"{RACINE}/scenarios/{cle}", headers=cas.session)).status_code == 200
        assert (await c.delete(f"{RACINE}/scenarios/{cle}", headers=cas.session)).status_code == 404


async def test_la_carte_d_un_fichier_remplace_celle_du_restaurant_un_fichier_invalide_n_ecrit_rien(db_session, seconde_base, sans_preparation_des_organisations, demo_allumee, monkeypatch):  # noqa: F811
    cas = await _cas(db_session, seconde_base, monkeypatch)
    carte = ht.carte_de_hubrise(_corps("04-carte-relue.json")).carte
    async with client_http() as c:
        r = (await c.post(f"{RACINE}/restaurants", json={"nom": "Carte"}, headers=cas.session)).json()
        ok = await c.post(f"{RACINE}/restaurants/{r['id']}/carte/import", json={"carte": carte}, headers=cas.session)
        assert ok.status_code == 200 and ok.json()["produits"] == len(carte["produits"]) > 0
        for mauvaise in ({"format": "autre"}, {"format": ht.FORMAT_CARTE, "produits": [{"declinaisons": "pas une liste"}]}):
            assert (await c.post(f"{RACINE}/restaurants/{r['id']}/carte/import", json={"carte": mauvaise}, headers=cas.session)).status_code == 422
        detail = (await c.get(f"{RACINE}/restaurants/{r['id']}", headers=cas.session)).json()
        assert len(detail["carte"]["produits"]) == len(carte["produits"])  # rien n'a été écrasé par les refus


async def test_les_gestes_de_la_caisse_ecrivent_un_message_signe_un_code_inconnu_est_refuse(db_session, seconde_base, sans_preparation_des_organisations, demo_allumee, monkeypatch):  # noqa: F811
    cas = await _cas(db_session, seconde_base, monkeypatch)
    carte = ht.carte_de_hubrise(_corps("04-carte-relue.json")).carte
    async with client_http() as c:
        r = (await c.post(f"{RACINE}/restaurants", json={"nom": "Gestes"}, headers=cas.session)).json()
        await c.post(f"{RACINE}/restaurants/{r['id']}/carte/import", json={"carte": carte}, headers=cas.session)
        for geste in (
            {"geste": "rupture", "code": "TIRA-1", "disponible": False}, {"geste": "prix", "code": "REINE-S", "prix": 1300},
            {"geste": "etat", "etat": "deborde", "minutes_en_plus": 10},
        ):
            assert (await c.post(f"{RACINE}/restaurants/{r['id']}/gestes", json=geste, headers=cas.session)).status_code == 200, geste
        for refus in ({"geste": "rupture", "code": "INCONNU", "disponible": False}, {"geste": "prix", "code": "REINE-S"}, {"geste": "commande", "ref": "nope", "statut": "accepted"}, {"geste": "danse"}):
            assert (await c.post(f"{RACINE}/restaurants/{r['id']}/gestes", json=refus, headers=cas.session)).status_code == 422, refus
        detail = (await c.get(f"{RACINE}/restaurants/{r['id']}", headers=cas.session)).json()
        assert [m["type"] for m in reversed(detail["messages"])] == ["inventory.patch", "catalog.update", "location.update"]


async def test_brancher_relie_le_restaurant_a_l_etablissement_et_debrancher_libere(db_session, seconde_base, sans_preparation_des_organisations, demo_allumee, monkeypatch):  # noqa: F811
    from api.services.restauration.caisse.caisse_demo import branchement
    from api.services.restauration.caisse.caisse_demo.transport import TransportDeDemo

    cas = await _cas(db_session, seconde_base, monkeypatch)
    etab = cas.sites_a[0]
    carte = ht.carte_de_hubrise(_corps("04-carte-relue.json")).carte
    transport = TransportDeDemo()
    reel = branchement.brancher

    async def brancher_en_memoire(*args, **kwargs):  # la route n'a pas de réseau en test : la prise parle à la caisse par le transport en mémoire
        return await reel(*args, transport=transport, **kwargs)

    monkeypatch.setattr(branchement, "brancher", brancher_en_memoire)
    async with client_http() as c:
        r = (await c.post(f"{RACINE}/restaurants", json={"nom": "Branché"}, headers=cas.session)).json()
        await c.post(f"{RACINE}/restaurants/{r['id']}/carte/import", json={"carte": carte}, headers=cas.session)
        assert (await c.post(f"{RACINE}/restaurants/{r['id']}/brancher", json={"etablissement_id": 99_999_999}, headers=cas.session)).status_code == 404
        ok = await c.post(f"{RACINE}/restaurants/{r['id']}/brancher", json={"etablissement_id": etab}, headers=cas.session)
        assert ok.status_code == 200 and ok.json() == {"ok": True, "passif": False}
        base = await schema.connecter(cas.base_a)
        try:
            assert (await lia.liaison(base, etab))["etat"] == "ok" and await base.fetchval("SELECT count(*) FROM mark.resto_produit WHERE site_id = $1", etab) > 0
        finally:
            await base.close()
        liste = (await c.get(f"{RACINE}/restaurants", headers=cas.session)).json()
        assert [e["id"] for e in liste["etablissements"]] == cas.sites_a and next(x for x in liste["restaurants"] if x["id"] == r["id"])["branche"] is True
        # un second restaurant sur le même point de vente n'existe pas : un restaurant de test sert UN établissement ; le débrancher libère
        assert (await c.post(f"{RACINE}/restaurants/{r['id']}/debrancher", headers=cas.session)).json() == {"ok": True}
        assert (await c.get(f"{RACINE}/restaurants/{r['id']}", headers=cas.session)).json()["branche"] is False
        base = await schema.connecter(cas.base_a)
        try:
            assert await lia.liaison(base, etab) is None
        finally:
            await base.close()
        await c.post(f"{RACINE}/restaurants/{r['id']}/brancher", json={"etablissement_id": etab}, headers=cas.session)
        assert (await c.delete(f"{RACINE}/restaurants/{r['id']}", headers=cas.session)).status_code == 200  # supprimer libère aussi le point de vente
        assert await db_client.retrouver_le_point_de_vente("hubrise", r["point_de_vente"]) is None


async def test_la_fenetre_lit_la_reservation_que_l_essai_a_faite_et_rien_d_autre(db_session, seconde_base, sans_preparation_des_organisations, demo_allumee, monkeypatch):  # noqa: F811
    cas = await _cas(db_session, seconde_base, monkeypatch)
    etab, autre_etab = cas.sites_a[0], cas.sites_a[1]
    base = await schema.connecter(cas.base_a)
    try:
        salle = await base.fetchval("INSERT INTO mark.resto_salle (site_id, nom) VALUES ($1, 'Salle') RETURNING id", etab)
        table = await base.fetchval("INSERT INTO mark.resto_table (site_id, salle_id, nom, couverts_min, couverts_max) VALUES ($1, $2, 'T3', 1, 6) RETURNING id", etab, salle)
        await base.execute(
            "INSERT INTO mark.resto_reservation (numero, site_id, debut, duree_minutes, couverts, telephone, prenom, table_ids, appel_id) "
            "VALUES (gen_random_uuid(), $1, '2026-11-21 18:30+00', 90, 4, '+33612345678', 'Sophie', $2, '7001')", etab, [table],
        )
    finally:
        await base.close()
    chemin = lambda appel, e: f"{RACINE}/appels/{appel}/reservation?etablissement_id={e}"  # noqa: E731
    async with client_http() as c:
        rendu = await c.get(chemin(7001, etab), headers=cas.session)
        assert rendu.status_code == 200, rendu.text
        corps = rendu.json()
        assert (corps["couverts"], corps["statut"], corps["tables"], corps["duree_minutes"]) == (4, "confirmee", ["T3"], 90)
        assert "Sophie" not in rendu.text and "0612345678" not in rendu.text and "prenom" not in rendu.text and "telephone" not in rendu.text
        assert (await c.get(chemin(7002, etab), headers=cas.session)).status_code == 404  # un autre appel
        assert (await c.get(chemin(7001, autre_etab), headers=cas.session)).status_code == 404  # un autre établissement de l'organisation
        assert (await c.get(chemin(7001, max(cas.sites_a + cas.sites_b) + 1000), headers=cas.session)).status_code == 404  # un établissement inconnu
        assert (await c.get(chemin(7001, 0), headers=cas.session)).status_code == 422
    # le Labo seulement : une organisation qui n'est pas le Labo n'a pas cette caisse
    async def pas_le_labo(o):
        return False

    monkeypatch.setattr(garde, "organisation_est_labo", pas_le_labo)
    async with client_http() as c:
        assert (await c.get(chemin(7001, etab), headers=cas.session)).status_code == 404


def test_chaque_route_de_la_caisse_de_demo_est_au_registre(sans_preparation_des_organisations):  # noqa: F811
    from api.app import app

    routes = [(m, r.path.removeprefix("/api/v1")) for r in app.routes if getattr(r, "path", "").startswith("/api/v1/restauration/caisse-demo") for m in getattr(r, "methods", set()) if m != "HEAD"]
    assert len(routes) >= 14
    for methode, chemin in routes:
        trouve = registre.decision_de(methode, chemin)
        assert trouve is not None, (methode, chemin)
        decision = trouve[0]
        if "/v1/" in chemin:
            assert type(decision).__name__ == "Exemption", chemin
        else:
            assert type(decision).__name__ == "Permission" and decision.cle == ("conversations.voir" if methode == "GET" else "agents.modifier"), (methode, chemin)
