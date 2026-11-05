"""[.mark] Builder partie 3, SA-L3c, sous-lot 1 (05 § 12) : fusionner une branche et la mettre à jour depuis la principale.

| Test | Ce qu'il prouve |
|---|---|
| aperçu | champ par champ, statuts repris / gardé / conflit, sans rien écrire ; branche sans version refusée |
| conflit | sans choix la fusion est refusée et RIEN n'est écrit ; avec un choix par conflit elle passe |
| fusion | une version publiée sur la principale, la part de trafic reprise, la branche archivée, la version en ligne de l'agent à jour |
| protégée | une principale protégée exige « fusion relue » ; la fusion écrit malgré la protection |
| validé avant d'écrire | une fusion qui laisserait une liaison orpheline est refusée sans rien écrire ; un brouillon sur la principale aussi |
| périmé | si la principale a bougé depuis l'aperçu, la fusion est refusée |
| défaire | la fusion se défait (version en ligne, parts, branche) tant que rien n'a été publié depuis |
| mise à jour | les nouveautés de la principale entrent dans le brouillon de LA PERSONNE, ses changements restent, la base avance, une autre personne garde son brouillon, « Revenir avant » la défait |
| cloisonnement | une autre organisation n'a accès à rien (404) ; permissions déclarées |
"""

from __future__ import annotations

import pytest

from api.db import branche_ouverte
from api.services.builder import revue
from api.tests.mark.builder_commun import graphe_depart
from api.tests.mark.test_apres_appel import _organisation, base_v4, smtp  # noqa: F401  (fixtures)
from api.tests.mark.test_sous_dossiers_et_groupe import _oublier, autre_org, org  # noqa: F401


@pytest.fixture(autouse=True)
def _branche_fermee():
    branche_ouverte.ouvrir(None, None)
    yield
    branche_ouverte.ouvrir(None, None)


def _graphe(prompt1="p1", prompt2="p2", label="Fini"):
    g = graphe_depart()
    g["nodes"][0]["data"]["prompt"] = prompt1
    g["nodes"][1]["data"]["prompt"] = prompt2
    g["edges"][0]["data"]["label"] = label
    return g


async def _agent(db_session, org):
    return await db_session.create_workflow(
        name="Agent", workflow_definition=_graphe(), user_id=org.utilisateur.id, organization_id=org.organisation.id
    )


async def _publier_la_principale(db_session, agent, graphe, **reglages):
    await db_session.save_workflow_draft(agent.id, workflow_definition=graphe, **reglages)
    return await db_session.publish_workflow_draft(agent.id)


async def _branche_publiee(db_session, org, agent, nom, graphe):
    """Une branche prise sur la version en ligne, retouchée par la personne, publiée (version immuable de la branche)."""
    moi = org.utilisateur.id
    branche, _ = await db_session.creer_une_branche(org.organisation.id, agent.id, nom, depuis_definition_id=None, user_id=moi)
    branche_ouverte.ouvrir(branche.id, moi)
    await db_session.save_workflow_draft(agent.id, workflow_definition=graphe)
    branche_ouverte.ouvrir(None, moi)
    version = await db_session.publier_le_brouillon_de_branche(org.organisation.id, agent.id, branche.id, moi)
    return branche, version


def _url(agent, branche, suite):
    return f"/api/v1/builder/branches/{agent.id}/{branche.id}/{suite}"


def _corps(apercu, **plus):
    return {"version_branche": apercu["branche"]["id_version"], "version_cible": apercu["cible"]["id_version"], **plus}


async def _nombre_de_versions(db_session, agent, org):
    return len(await db_session.get_workflow_version_summaries(agent.id, org.organisation.id))


# --- aperçu ----------------------------------------------------------------------------------------------------------------------


async def test_l_apercu_dit_chaque_champ_et_n_ecrit_rien(org, db_session, async_session, test_client_factory):
    agent = await _agent(db_session, org)
    branche, _ = await _branche_publiee(db_session, org, agent, "Essai", _graphe(prompt1="Allô, cabinet"))
    await _publier_la_principale(db_session, agent, _graphe(prompt2="À bientôt", label="Terminé"))
    avant = await _nombre_de_versions(db_session, agent, org)
    await _oublier(async_session)
    async with test_client_factory(org.utilisateur) as client:
        r = await client.get(_url(agent, branche, "fusion"))
        assert r.status_code == 200, r.text
        apercu = r.json()
        statuts = {c["cle"]: c["statut"] for c in apercu["champs"]}
        assert statuts == {"prompt:1": "reprise", "prompt:2": "gardee", "liaison:1-2": "gardee"}
        assert apercu["resume"] == {"reprise": 1, "gardee": 2, "conflit": 0} and apercu["problemes"] == []
        assert apercu["protegee"] is False and apercu["trafic"] == {"part_branche": 0, "part_principale": 100, "part_principale_apres": 100}
        assert apercu["branche"]["nom"] == "Essai" and apercu["cible"]["nom"] == "Principale"
    assert await _nombre_de_versions(db_session, agent, org) == avant  # lire n'écrit rien


async def test_une_branche_sans_version_ne_se_fusionne_pas(org, db_session, async_session, test_client_factory):
    agent = await _agent(db_session, org)
    branche, _ = await db_session.creer_une_branche(org.organisation.id, agent.id, "Vide", depuis_definition_id=None, user_id=org.utilisateur.id)
    # créée sur la version en ligne : elle a déjà une version de départ ; on la retire pour éprouver le cas
    from sqlalchemy import update

    from api.db.models_builder import WorkflowBranchModel

    async with db_session.async_session() as s:
        await s.execute(update(WorkflowBranchModel).where(WorkflowBranchModel.id == branche.id).values(head_definition_id=None))
        await s.commit()
    await _oublier(async_session)
    async with test_client_factory(org.utilisateur) as client:
        assert (await client.get(_url(agent, branche, "fusion"))).status_code == 409


# --- fusion ----------------------------------------------------------------------------------------------------------------------


async def test_un_conflit_sans_choix_est_refuse_sans_rien_ecrire_puis_passe_avec_le_choix(org, db_session, async_session, test_client_factory):
    agent = await _agent(db_session, org)
    branche, _ = await _branche_publiee(db_session, org, agent, "Essai", _graphe(prompt1="Version de la branche"))
    en_ligne = await _publier_la_principale(db_session, agent, _graphe(prompt1="Version de la principale"))
    avant = await _nombre_de_versions(db_session, agent, org)
    await _oublier(async_session)
    async with test_client_factory(org.utilisateur) as client:
        apercu = (await client.get(_url(agent, branche, "fusion"))).json()
        assert apercu["resume"]["conflit"] == 1
        refus = await client.post(_url(agent, branche, "fusion"), json=_corps(apercu))
        assert refus.status_code == 422 and "Every conflict needs a choice" in refus.json()["detail"], refus.text
        assert await _nombre_de_versions(db_session, agent, org) == avant
        assert (await db_session.get_workflow(agent.id, organization_id=org.organisation.id)).released_definition_id == en_ligne.id
        mauvais = await client.post(_url(agent, branche, "fusion"), json=_corps(apercu, choix={"prompt:1": "le_plus_recent"}))
        assert mauvais.status_code == 422
        ok = await client.post(_url(agent, branche, "fusion"), json=_corps(apercu, choix={"prompt:1": "source"}))
        assert ok.status_code == 200, ok.text
    relu = await db_session.get_workflow(agent.id, organization_id=org.organisation.id)
    assert relu.released_definition_id != en_ligne.id
    assert relu.workflow_definition["nodes"][0]["data"]["prompt"] == "Version de la branche"


async def test_la_fusion_cree_une_version_reprend_la_part_et_archive_la_branche(org, db_session, async_session, test_client_factory):
    agent = await _agent(db_session, org)
    branche, version_de_branche = await _branche_publiee(db_session, org, agent, "Essai", _graphe(prompt1="Allô, cabinet"))
    principale = await db_session.obtenir_la_principale(org.organisation.id, agent.id)
    await db_session.regler_la_repartition(org.organisation.id, agent.id, {principale.id: 75, branche.id: 25})
    ancienne = agent.released_definition_id
    await _oublier(async_session)
    async with test_client_factory(org.utilisateur) as client:
        apercu = (await client.get(_url(agent, branche, "fusion"))).json()
        assert apercu["trafic"] == {"part_branche": 25, "part_principale": 75, "part_principale_apres": 100}
        r = await client.post(_url(agent, branche, "fusion"), json=_corps(apercu))
        assert r.status_code == 200, r.text
        assert r.json()["part_reprise"] == 25
        vue = (await client.get(f"/api/v1/builder/branches/{agent.id}")).json()
    assert [b["nom"] for b in vue["branches"]] == ["Principale"]  # la branche est archivée
    assert vue["branches"][0]["part"] == 100
    relu = await db_session.get_workflow(agent.id, organization_id=org.organisation.id)
    assert relu.released_definition_id not in (ancienne, version_de_branche.id)
    assert relu.workflow_definition["nodes"][0]["data"]["prompt"] == "Allô, cabinet"
    versions = await db_session.get_workflow_version_summaries(agent.id, org.organisation.id)
    assert sorted(v["status"] for v in versions) == ["archived", "published"]  # une seule version en ligne
    tout = await db_session.lister_les_branches(org.organisation.id, agent.id, avec_archivees=True)
    assert [(b.nom, b.statut, b.part_trafic) for b in tout] == [("Principale", "active", 100), ("Essai", "archived", 0)]


async def test_une_principale_protegee_exige_la_fusion_relue_et_la_fusion_ecrit_malgre_la_protection(
    org, autre_org, db_session, async_session, test_client_factory, monkeypatch
):
    agent = await _agent(db_session, org)
    branche, _ = await _branche_publiee(db_session, org, agent, "Essai", _graphe(prompt1="Allô"))
    monkeypatch.setattr("api.services.builder.constantes.organisation_bibliotheque", lambda: autre_org.organisation.id)
    await _oublier(async_session)
    async with test_client_factory(org.utilisateur) as client:
        apercu = (await client.get(_url(agent, branche, "fusion"))).json()
        assert apercu["protegee"] is True and apercu["relue_obligatoire"] is True
        sans = await client.post(_url(agent, branche, "fusion"), json=_corps(apercu))
        assert sans.status_code == 422 and "reviewed" in sans.json()["detail"], sans.text
        directe = await client.put(f"/api/v1/workflow/{agent.id}", json={"workflow_definition": _graphe(prompt1="Direct")})
        assert directe.status_code == 409  # la porte directe reste fermée
        relue = await client.post(_url(agent, branche, "fusion"), json=_corps(apercu, relue=True))
        assert relue.status_code == 200, relue.text
    relu = await db_session.get_workflow(agent.id, organization_id=org.organisation.id)
    assert relu.workflow_definition["nodes"][0]["data"]["prompt"] == "Allô"


async def test_une_fusion_qui_laisserait_une_liaison_orpheline_est_refusee_sans_rien_ecrire(org, db_session, async_session, test_client_factory):
    agent = await _agent(db_session, org)
    sans_fin = _graphe()
    sans_fin["nodes"] = sans_fin["nodes"][:1]
    sans_fin["edges"] = []
    branche, _ = await _branche_publiee(db_session, org, agent, "Essai", sans_fin)  # la branche retire l'étape 2 et sa liaison
    await _publier_la_principale(db_session, agent, _graphe(label="Terminé"))  # la principale retouche la liaison
    avant = await _nombre_de_versions(db_session, agent, org)
    await _oublier(async_session)
    async with test_client_factory(org.utilisateur) as client:
        apercu = (await client.get(_url(agent, branche, "fusion"))).json()
        assert {c["cle"]: c["statut"] for c in apercu["champs"]}["liaison:1-2"] == "conflit"
        garder = await client.post(_url(agent, branche, "fusion"), json=_corps(apercu, choix={"liaison:1-2": "cible"}))
        assert garder.status_code == 422 and "invalid" in garder.json()["detail"], garder.text
        assert await _nombre_de_versions(db_session, agent, org) == avant
        retirer = await client.post(_url(agent, branche, "fusion"), json=_corps(apercu, choix={"liaison:1-2": "source"}))
        assert retirer.status_code == 200, retirer.text  # la branche l'emporte : l'étape et sa liaison partent ensemble
    relu = await db_session.get_workflow(agent.id, organization_id=org.organisation.id)
    assert [n["id"] for n in relu.workflow_definition["nodes"]] == ["1"] and relu.workflow_definition["edges"] == []


async def test_un_brouillon_sur_la_principale_bloque_la_fusion(org, db_session, async_session, test_client_factory):
    agent = await _agent(db_session, org)
    branche, _ = await _branche_publiee(db_session, org, agent, "Essai", _graphe(prompt1="Allô"))
    await db_session.save_workflow_draft(agent.id, workflow_definition=_graphe(prompt2="Brouillon non publié"))
    await _oublier(async_session)
    async with test_client_factory(org.utilisateur) as client:
        apercu = (await client.get(_url(agent, branche, "fusion"))).json()
        assert [p["code"] for p in apercu["problemes"]] == ["brouillon_en_attente"]
        r = await client.post(_url(agent, branche, "fusion"), json=_corps(apercu))
        assert r.status_code == 409, r.text


async def test_si_la_principale_a_bouge_depuis_l_apercu_la_fusion_est_refusee(org, db_session, async_session, test_client_factory):
    agent = await _agent(db_session, org)
    branche, _ = await _branche_publiee(db_session, org, agent, "Essai", _graphe(prompt1="Allô"))
    await _oublier(async_session)
    async with test_client_factory(org.utilisateur) as client:
        apercu = (await client.get(_url(agent, branche, "fusion"))).json()
        await _publier_la_principale(db_session, agent, _graphe(prompt2="Publié entre-temps"))
        r = await client.post(_url(agent, branche, "fusion"), json=_corps(apercu))
        assert r.status_code == 409 and "changed since the preview" in r.json()["detail"], r.text


# --- défaire ---------------------------------------------------------------------------------------------------------------------


async def test_la_fusion_se_defait_tant_que_rien_n_a_ete_publie_depuis(org, db_session, async_session, test_client_factory):
    agent = await _agent(db_session, org)
    branche, _ = await _branche_publiee(db_session, org, agent, "Essai", _graphe(prompt1="Allô"))
    principale = await db_session.obtenir_la_principale(org.organisation.id, agent.id)
    await db_session.regler_la_repartition(org.organisation.id, agent.id, {principale.id: 60, branche.id: 40})
    ancienne = agent.released_definition_id
    await _oublier(async_session)
    async with test_client_factory(org.utilisateur) as client:
        apercu = (await client.get(_url(agent, branche, "fusion"))).json()
        assert (await client.post(_url(agent, branche, "fusion"), json=_corps(apercu))).status_code == 200
        assert (await client.get(_url(agent, branche, "fusion"))).status_code == 404  # archivée : plus de fusion à prévoir
        defait = await client.post(_url(agent, branche, "fusion/defaire"))
        assert defait.status_code == 200, defait.text
        assert (await client.post(_url(agent, branche, "fusion/defaire"))).status_code == 404  # déjà défaite
        vue = (await client.get(f"/api/v1/builder/branches/{agent.id}")).json()
    assert [(b["nom"], b["part"]) for b in vue["branches"]] == [("Principale", 60), ("Essai", 40)]
    relu = await db_session.get_workflow(agent.id, organization_id=org.organisation.id)
    assert relu.released_definition_id == ancienne
    assert relu.workflow_definition["nodes"][0]["data"]["prompt"] == "p1"
    versions = await db_session.get_workflow_version_summaries(agent.id, org.organisation.id)
    assert [v["status"] for v in versions if v["id"] == ancienne] == ["published"]


async def test_une_fusion_ne_se_defait_plus_apres_une_autre_publication(org, db_session, async_session, test_client_factory):
    agent = await _agent(db_session, org)
    branche, _ = await _branche_publiee(db_session, org, agent, "Essai", _graphe(prompt1="Allô"))
    await _oublier(async_session)
    async with test_client_factory(org.utilisateur) as client:
        apercu = (await client.get(_url(agent, branche, "fusion"))).json()
        assert (await client.post(_url(agent, branche, "fusion"), json=_corps(apercu))).status_code == 200
        await _publier_la_principale(db_session, agent, _graphe(prompt1="Allô", prompt2="Plus tard"))
        r = await client.post(_url(agent, branche, "fusion/defaire"))
        assert r.status_code == 409, r.text


# --- mise à jour depuis la principale --------------------------------------------------------------------------------------------


async def test_la_mise_a_jour_ramene_les_nouveautes_de_la_principale_et_garde_celles_de_la_branche(org, db_session, async_session, test_client_factory):
    agent = await _agent(db_session, org)
    moi = org.utilisateur.id
    branche, _ = await _branche_publiee(db_session, org, agent, "Essai", _graphe(prompt1="Allô, cabinet"))
    en_ligne = await _publier_la_principale(db_session, agent, _graphe(prompt2="À bientôt", label="Terminé"))
    await _oublier(async_session)
    async with test_client_factory(org.utilisateur) as client:
        apercu = (await client.get(_url(agent, branche, "mise-a-jour"))).json()
        assert apercu["a_jour"] is False
        assert {c["cle"]: c["statut"] for c in apercu["champs"]} == {"prompt:1": "gardee", "prompt:2": "reprise", "liaison:1-2": "reprise"}
        corps = {"version_principale": apercu["principale"]["id_version"], "base_attendue": apercu["branche"]["id_base"]}
        r = await client.post(_url(agent, branche, "mise-a-jour"), json=corps)
        assert r.status_code == 200, r.text
        # la base avance : il n'y a plus rien à ramener
        encore = await client.get(_url(agent, branche, "mise-a-jour"))
        assert encore.json()["a_jour"] is True
        assert (await client.post(_url(agent, branche, "mise-a-jour"), json=corps)).status_code == 409
    branche_ouverte.ouvrir(branche.id, moi)
    brouillon = await db_session.get_draft_version(agent.id)
    prompts = [n["data"]["prompt"] for n in brouillon.workflow_json["nodes"]]
    assert prompts == ["Allô, cabinet", "À bientôt"]  # la branche garde le sien, reçoit celui de la principale
    assert brouillon.workflow_json["edges"][0]["data"]["label"] == "Terminé"
    branche_ouverte.ouvrir(None, moi)
    assert (await db_session.get_workflow(agent.id, organization_id=org.organisation.id)).released_definition_id == en_ligne.id  # la principale n'a pas bougé
    assert await db_session.get_draft_version(agent.id) is None


async def test_la_mise_a_jour_ecrit_dans_le_brouillon_de_la_personne_et_se_defait_par_revenir_avant(org, db_session, async_session, test_client_factory):
    agent = await _agent(db_session, org)
    moi, autre = org.utilisateur.id, org.utilisateur.id + 100000
    branche, _ = await _branche_publiee(db_session, org, agent, "Essai", _graphe(prompt1="Allô"))
    await _publier_la_principale(db_session, agent, _graphe(prompt2="À bientôt"))
    branche_ouverte.ouvrir(branche.id, moi)
    await db_session.save_workflow_draft(agent.id, workflow_definition=_graphe(prompt1="Allô, retouché"))  # mon brouillon en cours
    branche_ouverte.ouvrir(None, moi)
    await _oublier(async_session)
    async with test_client_factory(org.utilisateur) as client:
        apercu = (await client.get(_url(agent, branche, "mise-a-jour"))).json()
        assert apercu["branche"]["brouillon"] is True
        corps = {"version_principale": apercu["principale"]["id_version"], "base_attendue": apercu["branche"]["id_base"]}
        assert (await client.post(_url(agent, branche, "mise-a-jour"), json=corps)).status_code == 200
    branche_ouverte.ouvrir(branche.id, moi)
    mon = await db_session.get_draft_version(agent.id)
    assert [n["data"]["prompt"] for n in mon.workflow_json["nodes"]] == ["Allô, retouché", "À bientôt"]
    branche_ouverte.ouvrir(branche.id, autre)
    assert await db_session.get_draft_version(agent.id) is None  # une autre personne n'a rien reçu
    branche_ouverte.ouvrir(branche.id, moi)
    # « Revenir avant » (propre à la branche) retrouve l'état d'avant la mise à jour
    liste = await revue.instantanes(org.organisation.id, agent.id)
    assert liste[0]["cause"] == "mise à jour depuis la principale"
    relu = await db_session.get_workflow(agent.id, organization_id=org.organisation.id)
    await revue.restaurer(org.organisation.id, relu, liste[0]["numero"], familles=["schema"], user=org.utilisateur)
    avant = await db_session.get_draft_version(agent.id)
    assert [n["data"]["prompt"] for n in avant.workflow_json["nodes"]] == ["Allô, retouché", "p2"]


async def test_une_mise_a_jour_avec_un_conflit_exige_un_choix(org, db_session, async_session, test_client_factory):
    agent = await _agent(db_session, org)
    branche, _ = await _branche_publiee(db_session, org, agent, "Essai", _graphe(prompt1="Branche"))
    await _publier_la_principale(db_session, agent, _graphe(prompt1="Principale"))
    await _oublier(async_session)
    async with test_client_factory(org.utilisateur) as client:
        apercu = (await client.get(_url(agent, branche, "mise-a-jour"))).json()
        assert apercu["resume"]["conflit"] == 1
        corps = {"version_principale": apercu["principale"]["id_version"], "base_attendue": apercu["branche"]["id_base"]}
        assert (await client.post(_url(agent, branche, "mise-a-jour"), json=corps)).status_code == 422
        assert (await client.post(_url(agent, branche, "mise-a-jour"), json={**corps, "choix": {"prompt:1": "cible"}})).status_code == 200


# --- cloisonnement et permissions ------------------------------------------------------------------------------------------------


async def test_une_autre_organisation_n_a_acces_a_rien(org, autre_org, db_session, async_session, test_client_factory):
    agent = await _agent(db_session, org)
    branche, _ = await _branche_publiee(db_session, org, agent, "Essai", _graphe(prompt1="Allô"))
    await _oublier(async_session)
    async with test_client_factory(autre_org.utilisateur) as client:
        for methode, suite in (("get", "fusion"), ("get", "mise-a-jour")):
            assert (await getattr(client, methode)(_url(agent, branche, suite))).status_code == 404
        corps = {"version_branche": 1, "version_cible": 1}
        assert (await client.post(_url(agent, branche, "fusion"), json=corps)).status_code == 404
        assert (await client.post(_url(agent, branche, "fusion/defaire"))).status_code == 404
        assert (await client.post(_url(agent, branche, "mise-a-jour"), json={"version_principale": 1})).status_code == 404


def test_les_routes_de_fusion_ont_leur_permission():
    from api.services.equipe_mark.registre_routes import decision_de

    def cle(methode, chemin):
        decision, _ = decision_de(methode, chemin)
        return getattr(decision, "cle", None)

    assert cle("POST", "/builder/branches/{workflow_id}/{branch_id}/fusion") == "agents.publier"
    assert cle("POST", "/builder/branches/{workflow_id}/{branch_id}/fusion/defaire") == "agents.publier"
    assert cle("POST", "/builder/branches/{workflow_id}/{branch_id}/mise-a-jour") == "agents.modifier"
    assert cle("PUT", "/builder/branches/{workflow_id}/principale/protection") == "agents.publier"
