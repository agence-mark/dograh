"""[.mark] builder partie 2, U2, sous-lot 2 : les espaces.

| Test | Ce qu'il prouve |
|---|---|
| C8, marquage prioritaire | l'organisation marquée Labo en base est LA source ; la variable n'est que le repli |
| un seul Labo | marquer une organisation retire le marquage de l'autre |
| nom d'affichage | le nom posé s'affiche, sinon ``provider_id`` ; l'écrire exige ``atelier.regler`` |
| sélecteur d'espace | le rôle fait la liste : un client créé après est là, un client non ouvert est absent |
| deux onglets | deux organisations dans deux adresses, des écritures entremêlées : aucune écriture croisée, l'organisation choisie du compte ne bouge pas |
| conversations de l'équipe | la vue toutes organisations ne montre que ce que le rôle ouvre ; un compte sans rôle ne voit que les siennes |
"""

import pytest

from api.services.builder.constantes import VARIABLE_ORG_BIBLIOTHEQUE, organisation_bibliotheque
from api.services.equipe_mark import espaces
from api.tests.mark.equipe_commun import (
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


async def test_le_marquage_en_base_prime_sur_la_variable(db_session, monkeypatch):
    monkeypatch.setenv(VARIABLE_ORG_BIBLIOTHEQUE, "987654")
    espaces.reinitialiser_cache()
    assert organisation_bibliotheque() == 987654  # repli : rien n'est marqué
    labo = await creer_organisation(db_session, "esp-labo-1")
    await espaces.definir_labo(labo, True)
    assert organisation_bibliotheque() == labo  # le marquage prime
    await espaces.definir_labo(labo, False)
    assert organisation_bibliotheque() == 987654  # démarqué : le repli sert de nouveau


async def test_un_seul_labo(db_session):
    a = await creer_organisation(db_session, "esp-labo-2a")
    b = await creer_organisation(db_session, "esp-labo-2b")
    await espaces.definir_labo(a, True)
    await espaces.definir_labo(b, True)
    assert organisation_bibliotheque() == b
    assert await db_session.organisation_marquee_labo("MARK_ESPACE") == b
    assert await db_session.get_configuration(a, "MARK_ESPACE") is None


async def test_le_nom_d_affichage_et_son_droit(db_session):
    org = await creer_organisation(db_session, "esp-nom-1")
    _, jeton_admin = await creer_compte(db_session, "adm-nom@example.com", role="Administrateur", organisations=[org])
    _, jeton_membre = await creer_compte(db_session, "mb-nom@example.com", role="Membre", organisations=[org])
    async with client_http() as c:
        refuse = await c.put(f"/api/v1/espaces/{org}", headers=entetes(jeton_membre, org), json={"nom_affichage": "X"})
        ok = await c.put(
            f"/api/v1/espaces/{org}", headers=entetes(jeton_admin, org), json={"nom_affichage": "  Nuances   de Feu "}
        )
        liste = await c.get("/api/v1/espaces", headers=entetes(jeton_admin, org))
        retire = await c.put(f"/api/v1/espaces/{org}", headers=entetes(jeton_admin, org), json={"nom_affichage": ""})
        apres = await c.get("/api/v1/espaces", headers=entetes(jeton_admin, org))
    assert refuse.status_code == 403
    assert ok.status_code == 200 and ok.json()["nom"] == "Nuances de Feu"
    assert next(e for e in liste.json()["espaces"] if e["id"] == org)["nom"] == "Nuances de Feu"
    assert retire.status_code == 200
    assert next(e for e in apres.json()["espaces"] if e["id"] == org)["nom"] == "esp-nom-1"  # provider_id


async def test_le_selecteur_suit_le_role(db_session):
    ouvert = await creer_organisation(db_session, "esp-sel-ouvert")
    ferme = await creer_organisation(db_session, "esp-sel-ferme")
    role = await db_session.creer_role(
        nom="Un-seul-client-test",
        labo_ouvert=False,
        tous_les_clients=False,
        permissions=["conversations.voir"],
        organisations=[ouvert],
    )
    user, jeton = await creer_compte(db_session, "sel@example.com", organisations=[ferme])
    await db_session.poser_membre(user.id, role)
    async with client_http() as c:
        liste = await c.get("/api/v1/espaces", headers=entetes(jeton))
    ids = {e["id"] for e in liste.json()["espaces"]}
    assert ouvert in ids and ferme not in ids

    tous = await db_session.creer_role(
        nom="Tous-clients-test", labo_ouvert=True, tous_les_clients=True, permissions=[], organisations=[]
    )
    apres_coup = await creer_organisation(db_session, "esp-sel-apres-coup")
    await db_session.poser_membre(user.id, tous)
    async with client_http() as c:
        liste = await c.get("/api/v1/espaces", headers=entetes(jeton))
    assert apres_coup in {e["id"] for e in liste.json()["espaces"]}


async def test_deux_onglets_deux_organisations_aucune_ecriture_croisee(db_session):
    a = await creer_organisation(db_session, "esp-onglet-a")
    b = await creer_organisation(db_session, "esp-onglet-b")
    user, jeton = await creer_compte(db_session, "onglets@example.com", role="Administrateur", organisations=[a, b])
    async with client_http() as c:
        # Les deux onglets s'entremêlent ; l'organisation choisie du compte (a) ne doit jamais bouger.
        for nom_a, nom_b in (("a1", "b1"), ("a2", "b2")):
            assert (await c.post("/api/v1/folder/", headers=entetes(jeton, a), json={"name": nom_a})).status_code == 200
            assert (await c.post("/api/v1/folder/", headers=entetes(jeton, b), json={"name": nom_b})).status_code == 200
        dans_a = await c.get("/api/v1/folder/", headers=entetes(jeton, a))
        dans_b = await c.get("/api/v1/folder/", headers=entetes(jeton, b))
    noms = lambda r: sorted(d["name"] for d in r.json())  # noqa: E731
    assert noms(dans_a) == ["a1", "a2"]
    assert noms(dans_b) == ["b1", "b2"]
    relu = await db_session.get_user_by_id(user.id)
    assert relu.selected_organization_id == a


async def test_la_vue_conversations_de_l_equipe_suit_le_role(db_session):
    ouvert = await creer_organisation(db_session, "esp-conv-ouvert")
    ferme = await creer_organisation(db_session, "esp-conv-ferme")
    role = await db_session.creer_role(
        nom="Voit-un-client-test",
        labo_ouvert=False,
        tous_les_clients=False,
        permissions=["conversations.voir"],
        organisations=[ouvert],
    )
    user, jeton = await creer_compte(db_session, "conv@example.com", organisations=[ouvert, ferme])
    await db_session.poser_membre(user.id, role)
    definition = {"nodes": [], "edges": []}
    for org, nom in ((ouvert, "agent ouvert"), (ferme, "agent ferme")):
        wf = await db_session.create_workflow(nom, definition, user.id, org)
        await db_session.create_workflow_run("run " + nom, wf.id, "chat", user.id, organization_id=org)
    async with client_http() as c:
        vue = await c.get("/api/v1/espaces/conversations", headers=entetes(jeton))
        interdit = await c.get(
            f"/api/v1/espaces/conversations?organization_id={ferme}", headers=entetes(jeton)
        )
    assert vue.status_code == 200
    corps = vue.json()
    assert corps["total"] == 1
    assert [x["organization_id"] for x in corps["conversations"]] == [ouvert]
    assert interdit.status_code == 404

    _, jeton_sans_role = await creer_compte(db_session, "sans-role-conv@example.com", organisations=[ferme])
    async with client_http() as c:
        refuse = await c.get("/api/v1/espaces/conversations", headers=entetes(jeton_sans_role))
    assert refuse.status_code == 403  # un compte sans rôle d'équipe n'a pas cette vue


async def test_l_organisation_du_labo_s_affiche_labo(db_session):
    org = await creer_organisation(db_session, "esp-labo-nom")
    _, jeton = await creer_compte(db_session, "adm-labo-nom@example.com", role="Administrateur", organisations=[org])
    await espaces.definir_labo(org, True)
    conf = await db_session.get_configuration(org, "MARK_NOM_AFFICHAGE")
    assert conf is not None and conf.value == {"nom": "Labo"}
    async with client_http() as c:
        liste = await c.get("/api/v1/espaces", headers=entetes(jeton, org))
    assert next(e for e in liste.json()["espaces"] if e["id"] == org)["nom"] == "Labo"


async def test_un_nom_choisi_n_est_pas_ecrase_par_labo(db_session):
    org = await creer_organisation(db_session, "esp-labo-nom-2")
    await espaces.definir_nom_affichage(org, "Atelier")
    await espaces.definir_labo(org, True)
    conf = await db_session.get_configuration(org, "MARK_NOM_AFFICHAGE")
    assert conf.value == {"nom": "Atelier"}
