"""[.mark] Clôture, É36 : la page Versions d'un agent dit PAR QUI, CE QUI CHANGE et les TESTS de chaque version.

| Test | Ce qu'il prouve |
|---|---|
| migration | une seule tête, les cinq colonnes de la migration sont celles du modèle, toutes nullables, sans valeur par défaut |
| identité | la session ou la clé de la requête pose l'auteur (``get_user``) ; la clé dit son nom, jamais un auteur du corps |
| chemins | écran, première version, retour en arrière, builder, fusion : aucun ne reste sans auteur |
| accepté par | un changement du builder accepté par une personne garde les deux |
| résumé | « Ce qui change » est rangé à la publication ; la première version et les anciennes restent vides |
| tests | le compte d'une version vient des dernières exécutions JOUÉES SUR ELLE, additionnées |
| route | prénom, auteur, résumé et tests en deux requêtes pour toute la page ; vides sans ``avec_details`` ; une autre organisation : 404 |
"""

from __future__ import annotations

import pytest
from sqlalchemy import select

from api.db import auteur_de_version, branche_ouverte
from api.db.models import WorkflowDefinitionModel
from api.services.builder import stock
from api.services.builder.constantes import cle_resultats
from api.services.publication import resume_version
from api.services.versions_agent import details
from api.tests.mark.builder_commun import graphe_depart, utilisateur
from api.tests.mark.test_apres_appel import _organisation, base_v4, smtp  # noqa: F401  (fixtures)
from api.tests.mark.test_sous_dossiers_et_groupe import _oublier, autre_org, org  # noqa: F401

COLONNES = {"auteur_type", "auteur_user_id", "auteur_libelle", "accepte_par_user_id", "resume_changements"}


@pytest.fixture(autouse=True)
def _auteur_efface():
    auteur_de_version.poser(None)
    branche_ouverte.ouvrir(None, None)
    yield
    auteur_de_version.poser(None)
    branche_ouverte.ouvrir(None, None)


def _graphe(prompt="p1"):
    g = graphe_depart()
    g["nodes"][0]["data"]["prompt"] = prompt
    return g


async def _lignes(async_session, agent):
    await async_session.flush()
    async_session.expunge_all()
    rows = await async_session.scalars(
        select(WorkflowDefinitionModel).where(WorkflowDefinitionModel.workflow_id == agent.id).order_by(WorkflowDefinitionModel.version_number)
    )
    return list(rows)


async def _agent(db_session, org):
    return await db_session.create_workflow(
        name="Agent", workflow_definition=_graphe(), user_id=org.utilisateur.id, organization_id=org.organisation.id
    )


# --- migration ---------------------------------------------------------------------------------------------------------------------


def test_la_migration_a_une_seule_tete_et_ses_colonnes_sont_celles_du_modele():
    import importlib.util
    from pathlib import Path

    from alembic.config import Config
    from alembic.script import ScriptDirectory

    racine = Path(__file__).resolve().parents[2]
    config = Config(str(racine / "alembic.ini"))
    config.set_main_option("script_location", str(racine / "alembic"))
    assert len(ScriptDirectory.from_config(config).get_heads()) == 1
    spec = importlib.util.spec_from_file_location("m", racine / "alembic" / "versions" / "b7d3f1a9c5e2_cloture_auteur_et_resume_des_versions.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    assert module.down_revision == "a1c5e9d3b7f2"
    assert {nom for nom, _ in module.COLONNES} == COLONNES
    colonnes = WorkflowDefinitionModel.__table__.c
    assert all(colonnes[nom].nullable and colonnes[nom].server_default is None for nom in COLONNES)


# --- identité ----------------------------------------------------------------------------------------------------------------------


def test_l_auteur_vient_de_la_session_ou_de_la_cle():
    personne = utilisateur(7)
    personne.par_cle_api = False
    assert auteur_de_version.depuis_l_utilisateur(personne) == auteur_de_version.Auteur("personne", 7, None)
    cle = utilisateur(8)
    cle.par_cle_api, cle.cle_api_nom = True, "Clé du portail\x00 de Marc"
    assert auteur_de_version.depuis_l_utilisateur(cle) == auteur_de_version.Auteur("cle_api", 8, "Clé du portail de Marc")
    cle.mark_auteur = "portail : Léa Martin"
    assert auteur_de_version.depuis_l_utilisateur(cle).libelle == "portail : Léa Martin"


async def test_get_user_pose_l_auteur_de_la_requete(monkeypatch):
    from api.services.auth import depends

    compte = utilisateur(42)
    compte.selected_organization_id = None

    async def brut(*_args):
        return compte

    async def acces(*_args, **_kw):
        return None

    monkeypatch.setattr(depends, "_get_user_brut", brut)
    monkeypatch.setattr("api.services.equipe_mark.blocage.exiger_acces_actif", acces)
    await depends.get_user(authorization="Bearer x", x_api_key=None, x_mark_auteur=None, connexion=None)
    assert auteur_de_version.courant() == auteur_de_version.Auteur("personne", 42, None)
    compte.cle_api_nom = "Ma clé"
    await depends.get_user(authorization=None, x_api_key="cle", x_mark_auteur=None, connexion=None)
    assert auteur_de_version.courant() == auteur_de_version.Auteur("cle_api", 42, "Ma clé")


def test_le_cerveau_du_builder_et_la_porte_mcp_se_declarent():
    """Les branchements qu'aucun test de route n'exerce : le moteur écrit « Builder », la porte MCP « par la clé »."""
    from pathlib import Path

    racine = Path(__file__).resolve().parents[2]
    assert "en_tant_que_builder()" in (racine / "services" / "builder" / "moteur.py").read_text(encoding="utf-8")
    assert "poser_depuis(user)" in (racine / "mcp_server" / "auth.py").read_text(encoding="utf-8")
    assert "accepte_par=user.id" in (racine / "routes" / "builder_c2.py").read_text(encoding="utf-8")


# --- chemins qui créent une version -----------------------------------------------------------------------------------------------


async def test_ecran_premiere_version_et_retour_en_arriere_ont_un_auteur(org, db_session, async_session):
    moi = org.utilisateur.id
    auteur_de_version.poser(auteur_de_version.Auteur("personne", moi))
    agent = await _agent(db_session, org)  # v1
    await db_session.save_workflow_draft(agent.id, workflow_definition=_graphe("v2"))
    await db_session.publish_workflow_draft(agent.id)
    anciennes = await _lignes(async_session, agent)
    auteur_de_version.poser(auteur_de_version.Auteur("cle_api", moi, "Clé de Marc"))
    await db_session.revert_to_version(agent.id, anciennes[0].id)
    lignes = await _lignes(async_session, agent)
    assert [(l.version_number, l.auteur_type, l.auteur_user_id, l.auteur_libelle, l.accepte_par_user_id) for l in lignes] == [
        (1, "personne", moi, None, None),
        (2, "personne", moi, None, None),
        (3, "cle_api", moi, "Clé de Marc", None),
    ]


async def test_sans_requete_la_version_n_a_pas_d_auteur_et_rien_ne_casse(org, db_session, async_session):
    agent = await _agent(db_session, org)
    (v1,) = await _lignes(async_session, agent)
    assert (v1.auteur_type, v1.auteur_user_id, v1.auteur_libelle, v1.accepte_par_user_id, v1.resume_changements) == (None,) * 5


async def test_un_changement_du_builder_est_builder_et_une_acceptation_garde_la_personne(org, db_session, async_session):
    moi = org.utilisateur.id
    auteur_de_version.poser(auteur_de_version.Auteur("personne", moi))
    agent = await _agent(db_session, org)
    with auteur_de_version.en_tant_que_builder():
        await db_session.save_workflow_draft(agent.id, workflow_definition=_graphe("par le builder"))  # crée le brouillon v2
    assert auteur_de_version.courant().type == "personne"  # la fin du geste rend la main à la requête
    with auteur_de_version.en_tant_que_builder(accepte_par=moi):
        await db_session.save_workflow_draft(agent.id, workflow_definition=_graphe("accepté"))  # le brouillon existe déjà
    v1, v2 = await _lignes(async_session, agent)
    assert (v2.auteur_type, v2.auteur_user_id, v2.accepte_par_user_id) == ("builder", None, moi)
    assert v1.accepte_par_user_id is None


async def test_la_fusion_a_pour_auteur_celui_qui_a_ouvert_la_branche_et_pour_accepte_par_celui_qui_fusionne(
    org, db_session, async_session, test_client_factory
):
    from api.db.models import UserModel

    collegue = UserModel(provider_id=f"collegue-{org.utilisateur.id}", selected_organization_id=org.organisation.id)
    async_session.add(collegue)
    await async_session.flush()
    moi, autre = org.utilisateur.id, collegue.id
    agent = await _agent(db_session, org)
    auteur_de_version.poser(auteur_de_version.Auteur("personne", autre))
    branche, _ = await db_session.creer_une_branche(org.organisation.id, agent.id, "Essai", depuis_definition_id=None, user_id=autre)
    branche_ouverte.ouvrir(branche.id, autre)
    await db_session.save_workflow_draft(agent.id, workflow_definition=_graphe("branche"))
    branche_ouverte.ouvrir(None, autre)
    await db_session.publier_le_brouillon_de_branche(org.organisation.id, agent.id, branche.id, autre)
    de_la_branche = [l for l in await _lignes(async_session, agent) if l.branch_id == branche.id]
    assert [(l.auteur_type, l.auteur_user_id) for l in de_la_branche] == [("personne", autre)]
    assert de_la_branche[0].resume_changements["etapes_modifiees"] == 1  # contre la tête que la branche servait

    auteur_de_version.poser(auteur_de_version.Auteur("personne", moi))
    url = f"/api/v1/builder/branches/{agent.id}/{branche.id}/fusion"
    await _oublier(async_session)
    async with test_client_factory(org.utilisateur) as client:
        apercu = (await client.get(url)).json()
        fait = await client.post(url, json={"version_branche": apercu["branche"]["id_version"], "version_cible": apercu["cible"]["id_version"]})
        assert fait.status_code == 200, fait.text
    version = [l for l in await _lignes(async_session, agent) if l.branch_id is None and l.status == "published"][0]
    assert (version.auteur_type, version.auteur_user_id, version.accepte_par_user_id) == ("personne", autre, moi)
    assert version.resume_changements["etapes_modifiees"] == 1 and version.resume_changements["noms_modifiees"] == ["Départ"]


# --- résumé ------------------------------------------------------------------------------------------------------------------------


def test_le_resume_compte_les_etapes_les_liaisons_et_les_reglages():
    avant = _graphe("a")
    apres = _graphe("b")
    apres["nodes"].append({"id": "3", "type": "agentNode", "position": {"x": 0, "y": 0}, "data": {"name": "Rendez-vous", "prompt": "x"}})
    apres["nodes"][1]["data"]["prompt"] = "autre"
    resume = resume_version.resumer(apres, avant, {"voix": "b"}, {"voix": "a"})
    assert resume["etapes_ajoutees"] == 1 and resume["noms_ajoutees"] == ["Rendez-vous"]
    assert resume["etapes_modifiees"] == 2 and resume["noms_modifiees"] == ["Départ", "Fin"]
    assert resume["etapes_retirees"] == 0 and resume["reglages"] == 1 and resume["total"] == 4
    assert resume_version.resumer(avant, avant)["total"] == 0


async def test_le_resume_est_range_a_la_publication_et_la_premiere_version_reste_vide(org, db_session, async_session):
    agent = await _agent(db_session, org)
    nouveau = _graphe("changé")
    nouveau["nodes"][1]["data"]["prompt"] = "Au revoir"
    await db_session.save_workflow_draft(agent.id, workflow_definition=nouveau)
    (brouillon,) = [l for l in await _lignes(async_session, agent) if l.status == "draft"]
    assert brouillon.resume_changements is None  # calculé à la publication, pas avant
    await db_session.publish_workflow_draft(agent.id)
    v1, v2 = await _lignes(async_session, agent)
    assert v1.resume_changements is None
    assert v2.resume_changements["total"] == 2 and v2.resume_changements["etapes_modifiees"] == 2


# --- tests -------------------------------------------------------------------------------------------------------------------------


def test_le_compte_des_tests_prend_la_derniere_execution_de_chaque_test_sur_cette_version():
    lignes = [
        {"executions": [{"version": 3, "reussis": 2, "total": 3}, {"version": 3, "reussis": 0, "total": 3}, {"version": 2, "reussis": 3, "total": 3}]},
        {"executions": [{"version": 2, "reussis": 1, "total": 3}, {"version": 3, "reussis": 3, "total": 3}]},
        {"executions": [{"version": 3, "reussis": "x", "total": 3}, {"version": 3, "reussis": 1, "total": 0}]},
        {"executions": []},
    ]
    assert details.compte_des_tests(lignes, {1, 2, 3}) == {3: (5, 6), 2: (4, 6)}
    assert details.compte_des_tests(lignes, {9}) == {}


# --- route -------------------------------------------------------------------------------------------------------------------------


async def _membre(async_session, user_id, prenom):
    from api.db.models_equipe import MarkMembreModel, MarkRoleModel

    role = await async_session.scalar(select(MarkRoleModel.id).limit(1))
    async_session.add(MarkMembreModel(user_id=user_id, role_id=role, prenom=prenom, nom="Dupont"))
    await async_session.flush()


async def test_la_page_donne_par_qui_ce_qui_change_et_les_tests_en_deux_requetes(org, db_session, async_session, test_client_factory, monkeypatch):
    moi = org.utilisateur.id
    await _membre(async_session, moi, "Evan")
    agent = await _agent(db_session, org)  # v1 sans auteur (version d'avant)
    for n in (2, 3, 4):
        auteur_de_version.poser(
            auteur_de_version.Auteur("cle_api", moi, "Clé du portail") if n == 3 else auteur_de_version.Auteur("personne", moi)
        )
        await db_session.save_workflow_draft(agent.id, workflow_definition=_graphe(f"v{n}"))
        await db_session.publish_workflow_draft(agent.id)
    await stock.ecrire(org.organisation.id, cle_resultats(agent.id, "accueil"), {"executions": [{"version": 4, "reussis": 21, "total": 24}]})
    appels = {"prenoms": 0, "tests": 0}
    vrai_prenoms, vrai_tests = details.db_client.prenoms_des_comptes, details.stock.lister

    async def prenoms(ids):
        appels["prenoms"] += 1
        return await vrai_prenoms(ids)

    async def tests(*a, **k):
        appels["tests"] += 1
        return await vrai_tests(*a, **k)

    monkeypatch.setattr(details.db_client, "prenoms_des_comptes", prenoms)
    monkeypatch.setattr(details.stock, "lister", tests)
    await _oublier(async_session)
    async with test_client_factory(org.utilisateur) as client:
        reponse = await client.get(f"/api/v1/workflow/{agent.id}/versions", params={"limit": 26, "avec_details": "true"})
        sans = await client.get(f"/api/v1/workflow/{agent.id}/versions", params={"limit": 26})
    assert reponse.status_code == 200, reponse.text
    assert appels == {"prenoms": 1, "tests": 1}  # une fois pour 4 versions : pas de requête par ligne
    par_numero = {v["version_number"]: v for v in reponse.json()}
    v4 = par_numero[4]
    assert (v4["auteur_type"], v4["auteur_nom"], v4["tests_reussis"], v4["tests_total"]) == ("personne", "Evan", 21, 24)
    assert v4["resume_changements"]["etapes_modifiees"] == 1
    v3 = par_numero[3]
    assert (v3["auteur_type"], v3["auteur_nom"], v3["tests_total"]) == ("cle_api", "Clé du portail", None)
    v1 = par_numero[1]
    assert (v1["auteur_type"], v1["auteur_nom"], v1["resume_changements"], v1["tests_total"], v1["accepte_par"]) == (None, None, None, None, False)
    assert all(v["auteur_type"] is None and v["resume_changements"] is None for v in sans.json())  # sans le paramètre : rien de plus


async def test_une_autre_organisation_ne_voit_ni_les_versions_ni_leurs_details(org, autre_org, db_session, async_session, test_client_factory):
    agent = await _agent(db_session, org)
    await stock.ecrire(org.organisation.id, cle_resultats(agent.id, "accueil"), {"executions": [{"version": 1, "reussis": 1, "total": 1}]})
    await _oublier(async_session)
    async with test_client_factory(autre_org.utilisateur) as client:
        reponse = await client.get(f"/api/v1/workflow/{agent.id}/versions", params={"avec_details": "true"})
    assert reponse.status_code == 404
    # les résultats de tests se lisent avec l'organisation de l'appelant : ceux d'une autre n'apparaissent pas
    assert await details.tests_par_version(autre_org.organisation.id, agent.id, {1}) == {}
