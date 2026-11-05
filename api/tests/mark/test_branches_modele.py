"""[.mark] Builder partie 3, SA-L3b, sous-lot 1 (05 § 12) : le modèle des branches et des versions.

| Test | Ce qu'il prouve |
|---|---|
| principale | « Principale » existe toujours, une seule par agent, posée à la demande pour un agent plus récent que la migration |
| création | une branche part à 0 % du trafic, avec le brouillon de son auteur (copie de la version en ligne) ; nom pris ou invalide refusé |
| brouillon par personne | le brouillon d'une branche est à la personne ; l'autre n'en voit pas ; la principale garde son brouillon unique et sa copie héritée |
| version immuable | « Publier » une branche crée une version immuable, sans toucher la version en ligne de la principale ni son historique |
| principale | publier la principale par la branche est refusé ; un brouillon de branche ne se publie pas comme la version de l'agent |
| cloisonnement | une autre organisation n'a accès ni à l'agent, ni à la branche, ni aux versions (404) |
| en-tête | l'en-tête de branche mène le builder dans le brouillon de la personne sur cette branche (vraie route) |
| script | les agents existants : principale manquante posée ; un déploiement en cours devient une branche avec sa part, sauvegarde d'abord, rejouable |
"""

from __future__ import annotations

import json

import pytest
from starlette.requests import HTTPConnection

from api.db import branche_ouverte
from api.db.branches_client import ErreurDeBranche
from api.tests.mark.test_apres_appel import _organisation, base_v4, smtp  # noqa: F401  (fixtures)
from api.tests.mark.test_sous_dossiers_et_groupe import _oublier, autre_org, org  # noqa: F401

GRAPHE = {"nodes": [{"id": "1", "type": "agentNode", "position": {"x": 0, "y": 0}, "data": {"name": "Accueil", "prompt": "Bonjour"}}], "edges": []}


@pytest.fixture(autouse=True)
def _branche_fermee():
    branche_ouverte.ouvrir(None, None)
    yield
    branche_ouverte.ouvrir(None, None)


async def _agent(db_session, org, nom="Agent"):
    return await db_session.create_workflow(
        name=nom, workflow_definition=GRAPHE, user_id=org.utilisateur.id, organization_id=org.organisation.id
    )


# --- la principale ---------------------------------------------------------------------------------------------------------------


async def test_la_principale_existe_toujours_et_il_n_y_en_a_qu_une(org, db_session):
    agent = await _agent(db_session, org)
    premiere = await db_session.obtenir_la_principale(org.organisation.id, agent.id)
    seconde = await db_session.obtenir_la_principale(org.organisation.id, agent.id)
    assert premiere.id == seconde.id and premiere.est_principale and premiere.nom == "Principale" and premiere.part_trafic == 100
    branche, _ = await db_session.creer_une_branche(org.organisation.id, agent.id, "Essai", depuis_definition_id=None, user_id=org.utilisateur.id)
    toutes = await db_session.lister_les_branches(org.organisation.id, agent.id)
    assert [b.est_principale for b in toutes] == [True, False] and toutes[0].id == premiere.id
    assert branche.est_principale is False


# --- création --------------------------------------------------------------------------------------------------------------------


async def test_une_branche_part_a_zero_pour_cent_avec_le_brouillon_de_son_auteur(org, db_session):
    agent = await _agent(db_session, org)
    branche, brouillon = await db_session.creer_une_branche(
        org.organisation.id, agent.id, "Nouveau prompt", depuis_definition_id=None, user_id=org.utilisateur.id
    )
    assert branche.part_trafic == 0 and branche.head_definition_id == agent.released_definition_id
    assert brouillon.status == "draft" and brouillon.branch_id == branche.id and brouillon.draft_owner_id == org.utilisateur.id
    assert brouillon.workflow_json == GRAPHE
    principale = await db_session.obtenir_la_principale(org.organisation.id, agent.id)
    assert principale.part_trafic == 100  # les appels en cours ne bougent pas


async def test_nom_pris_ou_invalide_est_refuse(org, db_session):
    from api.services.branches import service

    agent = await _agent(db_session, org)
    await service.creer(org.organisation.id, agent, "Essai", depuis_version=None, user_id=org.utilisateur.id, protegee=False)
    for nom, code in (("essai", "nom_pris"), ("  ESSAI ", "nom_pris"), ("", "nom"), ("x" * 61, "nom"), ("a\x00b", "nom")):
        with pytest.raises(ErreurDeBranche) as e:
            await service.creer(org.organisation.id, agent, nom, depuis_version=None, user_id=org.utilisateur.id, protegee=False)
        assert e.value.code == code
    with pytest.raises(ErreurDeBranche) as e:  # une version qui n'existe pas
        await service.creer(org.organisation.id, agent, "Autre", depuis_version=99, user_id=org.utilisateur.id, protegee=False)
    assert e.value.code == "introuvable"


# --- un brouillon par personne et par branche -----------------------------------------------------------------------------------


async def test_le_brouillon_d_une_branche_est_a_la_personne_et_la_principale_garde_le_sien(org, db_session):
    agent = await _agent(db_session, org)
    moi, autre = org.utilisateur.id, org.utilisateur.id + 100000
    branche, _ = await db_session.creer_une_branche(org.organisation.id, agent.id, "Essai", depuis_definition_id=None, user_id=moi)

    branche_ouverte.ouvrir(branche.id, moi)
    mon_brouillon = await db_session.save_workflow_draft(agent.id, workflow_definition={"nodes": [], "edges": [], "x": "branche"})
    assert mon_brouillon.branch_id == branche.id and mon_brouillon.draft_owner_id == moi
    assert (await db_session.get_draft_version(agent.id)).workflow_json["x"] == "branche"

    branche_ouverte.ouvrir(branche.id, autre)  # une autre personne : pas mon brouillon
    assert await db_session.get_draft_version(agent.id) is None

    branche_ouverte.ouvrir(None, moi)  # la principale : son brouillon unique, jamais celui de la branche
    assert await db_session.get_draft_version(agent.id) is None
    principal = await db_session.save_workflow_draft(agent.id, workflow_definition={"nodes": [], "edges": [], "x": "principale"})
    assert principal.branch_id is None and principal.draft_owner_id is None
    assert (await db_session.get_draft_version(agent.id)).workflow_json["x"] == "principale"
    # la copie héritée de la table des agents reflète la principale, jamais la branche
    relu = await db_session.get_workflow(agent.id, organization_id=org.organisation.id)
    assert relu.workflow_definition["x"] == "principale"
    branche_ouverte.ouvrir(branche.id, moi)
    assert (await db_session.get_draft_version(agent.id)).workflow_json["x"] == "branche"


async def test_une_branche_d_un_autre_agent_ne_donne_aucun_brouillon_et_ne_casse_rien(org, db_session):
    un, deux = await _agent(db_session, org, "Un"), await _agent(db_session, org, "Deux")
    branche, brouillon = await db_session.creer_une_branche(org.organisation.id, un.id, "Essai", depuis_definition_id=None, user_id=org.utilisateur.id)
    branche_ouverte.ouvrir(branche.id, org.utilisateur.id)  # l'en-tête reste posé quand on lit un AUTRE agent
    assert await db_session.get_draft_version(deux.id) is None
    ecrit = await db_session.save_workflow_draft(deux.id, workflow_definition=GRAPHE)  # écrit sur la principale de « Deux »
    assert ecrit.branch_id is None and ecrit.draft_owner_id is None
    assert (await db_session.branche_ouverte_de(deux.id)).branch_id is None
    assert (await db_session.branche_ouverte_de(un.id)).branch_id == branche.id
    assert (await db_session.get_draft_version(un.id)).id == brouillon.id  # le brouillon de la branche n'a pas bougé


# --- version immuable ------------------------------------------------------------------------------------------------------------


async def test_publier_une_branche_cree_une_version_immuable_sans_toucher_la_principale(org, db_session):
    agent = await _agent(db_session, org)
    moi = org.utilisateur.id
    en_ligne = agent.released_definition_id
    branche, brouillon = await db_session.creer_une_branche(org.organisation.id, agent.id, "Essai", depuis_definition_id=None, user_id=moi)
    branche_ouverte.ouvrir(branche.id, moi)
    await db_session.save_workflow_draft(agent.id, workflow_definition={"nodes": [], "edges": [], "x": 2})
    branche_ouverte.ouvrir(None, moi)

    version = await db_session.publier_le_brouillon_de_branche(org.organisation.id, agent.id, branche.id, moi)
    assert version.id == brouillon.id and version.status == "archived" and version.branch_id == branche.id and version.published_at
    relue = await db_session.obtenir_une_branche(org.organisation.id, agent.id, branche.id)
    assert relue.head_definition_id == version.id
    # la version en ligne de l'agent et l'historique de la principale n'ont pas bougé
    agent_relu = await db_session.get_workflow(agent.id, organization_id=org.organisation.id)
    assert agent_relu.released_definition_id == en_ligne
    historique = await db_session.get_workflow_version_summaries(agent.id, org.organisation.id)
    assert [v["id"] for v in historique] == [en_ligne]
    assert [v.id for v in await db_session.get_workflow_versions(agent.id)] == [en_ligne]
    # la version est rangée sous sa branche, avec son numéro
    rangees = await db_session.versions_des_branches(org.organisation.id, agent.id)
    assert [(v["branch_id"], v["id"]) for v in rangees] == [(branche.id, version.id)]
    # sans nouveau brouillon, rien à publier ; la liste des agents ne montre pas le brouillon d'une branche
    with pytest.raises(ErreurDeBranche) as e:
        await db_session.publier_le_brouillon_de_branche(org.organisation.id, agent.id, branche.id, moi)
    assert e.value.code == "sans_brouillon"


async def test_la_principale_ne_se_publie_pas_par_une_branche_ni_un_brouillon_de_branche_comme_la_version_de_l_agent(org, db_session):
    agent = await _agent(db_session, org)
    moi = org.utilisateur.id
    principale = await db_session.obtenir_la_principale(org.organisation.id, agent.id)
    with pytest.raises(ErreurDeBranche) as e:
        await db_session.publier_le_brouillon_de_branche(org.organisation.id, agent.id, principale.id, moi)
    assert e.value.code == "principale"
    branche, _ = await db_session.creer_une_branche(org.organisation.id, agent.id, "Essai", depuis_definition_id=None, user_id=moi)
    branche_ouverte.ouvrir(branche.id, moi)
    with pytest.raises(ValueError):  # la publication « normale » de l'agent n'accepte pas le brouillon d'une branche
        await db_session.publish_workflow_draft(agent.id)
    etat = await db_session.get_etat_des_versions_pour_liste([agent.id])
    assert etat[agent.id]["version_etat"] == "publiee"  # le brouillon de la branche n'est pas « brouillon modifié »


# --- cloisonnement ---------------------------------------------------------------------------------------------------------------


async def test_une_autre_organisation_n_a_acces_a_rien(org, autre_org, db_session, test_client_factory, async_session):
    agent = await _agent(db_session, org)
    branche, _ = await db_session.creer_une_branche(org.organisation.id, agent.id, "Essai", depuis_definition_id=None, user_id=org.utilisateur.id)
    assert await db_session.obtenir_une_branche(autre_org.organisation.id, agent.id, branche.id) is None
    assert await db_session.versions_des_branches(autre_org.organisation.id, agent.id) == []
    assert await db_session.brouillons_de_l_agent(autre_org.organisation.id, agent.id) == []
    with pytest.raises(ErreurDeBranche):
        await db_session.lister_les_branches(autre_org.organisation.id, agent.id)
    with pytest.raises(ErreurDeBranche):
        await db_session.regler_la_repartition(autre_org.organisation.id, agent.id, {branche.id: 10})
    await _oublier(async_session)
    async with test_client_factory(autre_org.utilisateur) as client:
        assert (await client.get(f"/api/v1/builder/branches/{agent.id}")).status_code == 404
        assert (await client.post(f"/api/v1/builder/branches/{agent.id}", json={"nom": "Pirate"})).status_code == 404
        assert (await client.post(f"/api/v1/builder/branches/{agent.id}/{branche.id}/publier")).status_code == 404
        assert (await client.put(f"/api/v1/builder/branches/{agent.id}/repartition", json={"parts": {}})).status_code == 404


# --- les routes et l'en-tête de branche ------------------------------------------------------------------------------------------


@pytest.fixture
def lire_l_entete_de_branche(org):
    """Le client de test remplace ``get_user`` : on le remplace par une version qui lit l'en-tête comme la vraie (même fonction)."""
    from api.app import app
    from api.services.auth.depends import get_user

    async def faux_get_user(connexion: HTTPConnection = None):
        branche_ouverte.depuis_l_entete(connexion, org.utilisateur)
        return org.utilisateur

    return faux_get_user, app, get_user


def test_get_user_lit_vraiment_l_en_tete_de_branche():
    import inspect

    from api.services.auth.depends import get_user

    assert "branche_ouverte.depuis_l_entete(connexion, user)" in inspect.getsource(get_user)


async def test_les_routes_creent_listent_et_publient_et_l_en_tete_mene_le_builder_dans_la_branche(
    org, db_session, async_session, test_client_factory, lire_l_entete_de_branche
):
    agent = await _agent(db_session, org)
    await _oublier(async_session)
    faux_get_user, app, get_user = lire_l_entete_de_branche
    async with test_client_factory(org.utilisateur) as client:
        app.dependency_overrides[get_user] = faux_get_user
        cree = await client.post(f"/api/v1/builder/branches/{agent.id}", json={"nom": "Essai", "depuis_version": 1})
        assert cree.status_code == 200, cree.text
        identifiant = cree.json()["id"]
        assert (await client.post(f"/api/v1/builder/branches/{agent.id}", json={"nom": "essai"})).status_code == 409
        assert (await client.post(f"/api/v1/builder/branches/{agent.id}", json={"nom": ""})).status_code == 422
        vue = (await client.get(f"/api/v1/builder/branches/{agent.id}")).json()
        assert [b["nom"] for b in vue["branches"]] == ["Principale", "Essai"]
        assert vue["branches"][1]["part"] == 0 and vue["branches"][1]["version_en_ligne"] == 1
        assert [d["a_moi"] for d in vue["branches"][1]["brouillons"]] == [True]
        # le brouillon lu avec l'en-tête est celui de la branche
        d = await client.get(f"/api/v1/workflow/fetch/{agent.id}", headers={"X-Mark-Branche": str(identifiant)})
        assert d.status_code == 200, d.text
        assert d.json()["version_status"] == "draft"  # le brouillon de la personne sur la branche
        # sans en-tête, ou illisible : la principale, comme avant (pas de brouillon, donc la version en ligne)
        for entetes in ({}, {"X-Mark-Branche": "abc"}):
            p = await client.get(f"/api/v1/workflow/fetch/{agent.id}", headers=entetes)
            assert p.status_code == 200 and p.json()["version_status"] == "published"
        publiee = await client.post(f"/api/v1/builder/branches/{agent.id}/{identifiant}/publier")
        assert publiee.status_code == 200, publiee.text
        assert publiee.json()["status"] == "archived"
        assert (await client.post(f"/api/v1/builder/branches/{agent.id}/{identifiant}/publier")).status_code == 409
        vue = (await client.get(f"/api/v1/builder/branches/{agent.id}")).json()
        assert [v["numero"] for v in vue["branches"][1]["versions"]] == [publiee.json()["version_number"]]
        # branche ouverte sans brouillon : l'écran montre SA version en ligne (pas celle de la principale)
        sur_branche = (await client.get(f"/api/v1/workflow/fetch/{agent.id}", headers={"X-Mark-Branche": str(identifiant)})).json()
        assert sur_branche["version_number"] == publiee.json()["version_number"] and sur_branche["version_status"] == "archived"
        principale = (await client.get(f"/api/v1/workflow/fetch/{agent.id}")).json()
        assert principale["version_number"] == 1 and principale["version_status"] == "published"
        # publier la principale par l'en-tête d'une branche est refusé net (400), pas publié par erreur
        refuse = await client.post(f"/api/v1/workflow/{agent.id}/publish", headers={"X-Mark-Branche": str(identifiant)})
        assert refuse.status_code in (400, 409, 422), refuse.text


# --- le script des agents existants ----------------------------------------------------------------------------------------------


async def test_le_script_pose_les_principales_manquantes_et_reprend_un_deploiement_en_cours(org, db_session, async_session, tmp_path):
    from scripts.mark import migrer_branches as script
    from sqlalchemy import text

    agent = await _agent(db_session, org)
    ancienne = agent.released_definition_id
    await db_session.save_workflow_draft(agent.id, workflow_definition={"nodes": [], "edges": [], "n": 2})
    nouvelle = (await db_session.publish_workflow_draft(agent.id)).id
    await db_session.upsert_configuration(
        org.organisation.id, f"MARK_DEPLOIEMENT:{agent.id}", {"nouvelle": nouvelle, "precedente": ancienne, "pourcentage": 25, "par": "1"}
    )
    await db_session.upsert_configuration(org.organisation.id, f"MARK_DEPLOIEMENT:{agent.id + 999999}", {"nouvelle": 1, "precedente": 2, "pourcentage": 10})
    await _oublier(async_session)
    sauvegarde = tmp_path / "copie.json"

    a_blanc = await script.executer(async_session, appliquer=False, sauvegarde=None)
    mes = [f for f in a_blanc if f["agent"] == agent.id]
    assert {f["genre"] for f in mes} == {"principale", "deploiement"}
    assert (await async_session.execute(text("SELECT count(*) FROM workflow_branches WHERE workflow_id = :a"), {"a": agent.id})).scalar() == 0
    with pytest.raises(ValueError):  # rien n'est réécrit sans sauvegarde
        await script.executer(async_session, appliquer=True, sauvegarde=None)

    await script.executer(async_session, appliquer=True, sauvegarde=sauvegarde)
    sauve = json.loads(sauvegarde.read_text(encoding="utf-8"))
    assert any(f.get("cle") == f"MARK_DEPLOIEMENT:{agent.id}" and f["valeur"]["pourcentage"] == 25 for f in sauve["faits"])
    branches = (await async_session.execute(
        text("SELECT nom, est_principale, part_trafic, head_definition_id FROM workflow_branches WHERE workflow_id = :a ORDER BY est_principale DESC"),
        {"a": agent.id},
    )).all()
    assert [(b[0], b[1], b[2], b[3]) for b in branches] == [("Principale", True, 75, ancienne), ("Déploiement v2", False, 25, nouvelle)]
    assert await db_session.get_configuration(org.organisation.id, f"MARK_DEPLOIEMENT:{agent.id}") is None
    # une ligne qui ne vise aucun agent de l'organisation n'est pas touchée
    assert await db_session.get_configuration(org.organisation.id, f"MARK_DEPLOIEMENT:{agent.id + 999999}") is not None
    # rejouable sans effet double
    deuxieme = await script.executer(async_session, appliquer=True, sauvegarde=tmp_path / "deux.json")
    assert [f for f in deuxieme if f["agent"] == agent.id] == []
    assert (await async_session.execute(text("SELECT count(*) FROM workflow_branches WHERE workflow_id = :a"), {"a": agent.id})).scalar() == 2
    # et la lecture des appels voit la même chose : la nouvelle version sur sa part, l'ancienne sur le reste
    from api.services.publication import deploiement

    parts = await deploiement.lire(org.organisation.id, agent.id)
    vues = {deploiement.version_attribuee(parts, agent.id, f"0611{n:06d}") for n in range(60)}
    assert vues == {ancienne, nouvelle}


async def test_publier_avec_une_branche_ouverte_publie_la_branche_apres_les_memes_controles(
    org, db_session, async_session, test_client_factory, lire_l_entete_de_branche, monkeypatch
):
    """Le bouton Publier d'une branche ouverte joue la route de publication de l'agent : mêmes contrôles, mais la version est celle de
    la branche, et la version en ligne de l'agent ne bouge pas."""
    from api.services.groupe import groupe as groupe_service

    monkeypatch.setenv("MARK_PUBLICATION_SANS_GARDE", "1")
    agent = await db_session.create_workflow(
        name="Agent", workflow_definition=groupe_service.graphe_minimal_du_principal(), user_id=org.utilisateur.id, organization_id=org.organisation.id
    )
    en_ligne = agent.released_definition_id
    branche, brouillon = await db_session.creer_une_branche(org.organisation.id, agent.id, "Essai", depuis_definition_id=None, user_id=org.utilisateur.id)
    await _oublier(async_session)
    faux_get_user, app, get_user = lire_l_entete_de_branche
    async with test_client_factory(org.utilisateur) as client:
        app.dependency_overrides[get_user] = faux_get_user
        r = await client.post(f"/api/v1/workflow/{agent.id}/publish", headers={"X-Mark-Branche": str(branche.id)})
        assert r.status_code == 200, r.text
        assert r.json()["id"] == brouillon.id and r.json()["status"] == "archived"
    await _oublier(async_session)
    relu = await db_session.get_workflow(agent.id, organization_id=org.organisation.id)
    assert relu.released_definition_id == en_ligne
    assert (await db_session.obtenir_une_branche(org.organisation.id, agent.id, branche.id)).head_definition_id == brouillon.id


async def test_une_branche_dont_le_brouillon_est_invalide_n_est_pas_publiee(org, db_session, async_session, test_client_factory, lire_l_entete_de_branche):
    """Les contrôles de la publication jouent aussi sur une branche : un brouillon sans point de départ est refusé, rien n'est publié."""
    agent = await _agent(db_session, org)  # graphe sans « Start Call »
    branche, _ = await db_session.creer_une_branche(org.organisation.id, agent.id, "Essai", depuis_definition_id=None, user_id=org.utilisateur.id)
    await _oublier(async_session)
    faux_get_user, app, get_user = lire_l_entete_de_branche
    async with test_client_factory(org.utilisateur) as client:
        app.dependency_overrides[get_user] = faux_get_user
        r = await client.post(f"/api/v1/workflow/{agent.id}/publish", headers={"X-Mark-Branche": str(branche.id)})
        assert r.status_code == 422
    assert (await db_session.obtenir_une_branche(org.organisation.id, agent.id, branche.id)).head_definition_id == agent.released_definition_id


async def test_les_objets_rendus_restent_lisibles_comme_en_production(org, db_session, async_session):
    """La session des tests ne fait pas expirer les objets au commit (``expire_on_commit=False``) ; celle de la production, si : lire un
    objet rendu après un commit sans relecture y levait ``DetachedInstanceError`` (constaté sur l'écran, l'API répondait 500).
    Ici la session expire au commit, comme en production, le temps de ces appels."""
    agent = await _agent(db_session, org)
    o, moi, agent_id = org.organisation.id, org.utilisateur.id, agent.id
    async_session.sync_session.expire_on_commit = True
    try:
        principale = await db_session.obtenir_la_principale(o, agent_id)
        assert principale.nom == "Principale" and principale.part_trafic == 100
        branche, brouillon = await db_session.creer_une_branche(o, agent_id, "Essai", depuis_definition_id=None, user_id=moi)
        assert branche.nom == "Essai" and brouillon.branch_id == branche.id
        branches = await db_session.lister_les_branches(o, agent_id)
        assert [(b.nom, b.part_trafic, b.est_principale) for b in branches] == [("Principale", 100, True), ("Essai", 0, False)]
        ecrites = await db_session.regler_la_repartition(o, agent_id, {principale.id: 80, branche.id: 20})
        assert sorted(b.part_trafic for b in ecrites) == [20, 80]
        version = await db_session.publier_le_brouillon_de_branche(o, agent_id, branche.id, moi)
        assert version.status == "archived" and version.version_number
        from types import SimpleNamespace

        from api.services.branches import service

        faux_agent = SimpleNamespace(id=agent_id, released_definition_id=None, released_definition=None, workflow_configurations=None)
        vue = await service.vue(o, faux_agent, moi)
        assert [b["nom"] for b in vue["branches"]] == ["Principale", "Essai"]
    finally:
        async_session.sync_session.expire_on_commit = False
