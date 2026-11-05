"""[.mark] Builder partie 3, SA-L3c, sous-lot 3 (05 § 12, 18) : « Comparer en duel ».

Aucun appel réel : les appels de la fenêtre sont des lignes fabriquées au format de la page Qualité ; les branches et les versions sont
en vraie base.

| Test | Ce qu'il prouve |
|---|---|
| chiffres | part, appels, résolution, transferts, note, coût par appel, latence : les définitions de la page Qualité, par branche ou par version |
| meilleur | la meilleure valeur de chaque ligne qui a un sens (résolution et note plus haut, coût et latence plus bas), aucune pour les appels et les transferts |
| verdict | gagnant selon les lignes ; « insuffisant » sous cinq appels d'un côté ; égalité |
| configuration | la différence champ par champ, avant (gauche) et après (droite), sans clé en clair |
| côtés | deux versions, ou une version contre une branche ; un côté illisible ou inconnu est refusé |
| cloisonnement | un autre agent ou une autre organisation : 404, jamais les appels d'un autre |
"""

from __future__ import annotations

import pytest

from api.db import branche_ouverte
from api.tests.mark.builder_commun import graphe_depart
from api.tests.mark.test_apres_appel import _organisation, base_v4, smtp  # noqa: F401  (fixtures)
from api.tests.mark.test_sous_dossiers_et_groupe import _oublier, autre_org, org  # noqa: F401


@pytest.fixture(autouse=True)
def _branche_fermee():
    branche_ouverte.ouvrir(None, None)
    yield
    branche_ouverte.ouvrir(None, None)


def _graphe(prompt1="p1"):
    g = graphe_depart()
    g["nodes"][0]["data"]["prompt"] = prompt1
    return g


def _appels(agent_id, version, nombre, *, issues, transferts=0, note=None, cout=None, latence=None):
    """``nombre`` appels de cette version : ``issues`` avec issue, ``transferts`` transférés ; une note sur 5 (via les verdicts du juge)."""
    lignes = []
    for i in range(nombre):
        indicateurs = {"issue_obtenue": i < issues, "transfert": i < transferts}
        if latence is not None:
            indicateurs["latence_mediane"] = latence
        if cout is not None:
            indicateurs["cout"] = cout
        annotations = {"boucle": {"indicateurs": indicateurs}}
        if note is not None:
            reussis = round(note)
            annotations["juge"] = {"etat": "juge", "verdicts": [{"verdict": "reussi"}] * reussis + [{"verdict": "rate"}] * (5 - reussis)}
        lignes.append({"run_id": i, "workflow_id": agent_id, "workflow_nom": "Agent", "cree_le": None, "version": version, "annotations": annotations})
    return lignes


async def _monde(org, db_session):
    """Une principale (v1, puis v2 publiée) et une branche « Essai » (v3 publiée, 30 % du trafic)."""
    moi = org.utilisateur.id
    agent = await db_session.create_workflow(
        name="Agent", workflow_definition=_graphe(), user_id=moi, organization_id=org.organisation.id
    )
    branche, _ = await db_session.creer_une_branche(org.organisation.id, agent.id, "Essai", depuis_definition_id=None, user_id=moi)
    branche_ouverte.ouvrir(branche.id, moi)
    await db_session.save_workflow_draft(agent.id, workflow_definition=_graphe(prompt1="Allô, cabinet"), workflow_configurations={"voix": "b"})
    branche_ouverte.ouvrir(None, moi)
    version_branche = await db_session.publier_le_brouillon_de_branche(org.organisation.id, agent.id, branche.id, moi)
    principale = await db_session.obtenir_la_principale(org.organisation.id, agent.id)
    await db_session.regler_la_repartition(org.organisation.id, agent.id, {principale.id: 70, branche.id: 30})
    return agent, branche, principale, version_branche


@pytest.fixture
def appels(monkeypatch, db_session):
    """Remplace la lecture des appels de la fenêtre par des lignes fabriquées."""
    lignes: list = []

    async def lire(organization_id, *, jours, workflow_id=None):
        assert workflow_id is not None  # toujours bornée à l'agent
        return [x for x in lignes if x["workflow_id"] == workflow_id]

    monkeypatch.setattr(db_session, "runs_pour_la_qualite", lire)
    return lignes


async def _comparer(client, agent, gauche, droite, **plus):
    return await client.get(f"/api/v1/builder/branches/{agent.id}/comparer", params={"gauche": gauche, "droite": droite, **plus})


async def test_les_chiffres_le_meilleur_et_le_verdict(org, db_session, async_session, test_client_factory, appels):
    agent, branche, principale, version_branche = await _monde(org, db_session)
    appels += _appels(agent.id, 1, 20, issues=10, transferts=4, note=3, cout=0.20, latence=1.8)  # la principale
    appels += _appels(agent.id, version_branche.version_number, 10, issues=8, transferts=1, note=4, cout=0.30, latence=1.2)  # la branche
    await _oublier(async_session)
    async with test_client_factory(org.utilisateur) as client:
        r = await _comparer(client, agent, f"branche:{principale.id}", f"branche:{branche.id}")
        assert r.status_code == 200, r.text
        vue = r.json()
    assert vue["gauche"]["nom"] == "Principale" and vue["droite"]["nom"] == "Essai"
    assert (vue["gauche"]["part"], vue["droite"]["part"]) == (70, 30)
    lignes = {m["cle"]: m for m in vue["mesures"]}
    assert (lignes["appels"]["gauche"], lignes["appels"]["droite"], lignes["appels"]["meilleur"]) == (20, 10, None)
    assert (lignes["resolution"]["gauche"], lignes["resolution"]["droite"]) == (0.5, 0.8)
    assert lignes["resolution"]["meilleur"] == "droite" and lignes["resolution"]["ecart"] == 0.3
    assert lignes["transferts"]["meilleur"] is None  # un transfert n'est ni bon ni mauvais en soi
    assert lignes["note"]["meilleur"] == "droite"
    assert lignes["cout"]["gauche"] == 0.2 and lignes["cout"]["droite"] == 0.3 and lignes["cout"]["meilleur"] == "gauche"  # plus bas = mieux
    assert lignes["latence"]["meilleur"] == "droite"
    assert vue["verdict"] == {"gagnant": "droite", "pour_gauche": ["cout"], "pour_droite": ["resolution", "note", "latence"]}


async def test_sous_cinq_appels_le_verdict_est_insuffisant_et_une_donnee_absente_reste_vide(org, db_session, async_session, test_client_factory, appels):
    agent, branche, principale, version_branche = await _monde(org, db_session)
    appels += _appels(agent.id, 1, 20, issues=10)
    appels += _appels(agent.id, version_branche.version_number, 3, issues=3)
    await _oublier(async_session)
    async with test_client_factory(org.utilisateur) as client:
        vue = (await _comparer(client, agent, f"branche:{principale.id}", f"branche:{branche.id}")).json()
    assert vue["verdict"]["gagnant"] == "insuffisant" and vue["appels_min"] == 5
    lignes = {m["cle"]: m for m in vue["mesures"]}
    assert lignes["latence"]["gauche"] is None and lignes["latence"]["droite"] is None and lignes["latence"]["meilleur"] is None


async def test_egalite_quand_chacun_gagne_autant_de_lignes(org, db_session, async_session, test_client_factory, appels):
    agent, branche, principale, version_branche = await _monde(org, db_session)
    appels += _appels(agent.id, 1, 10, issues=9, note=3)  # la principale résout mieux
    appels += _appels(agent.id, version_branche.version_number, 10, issues=5, note=4)  # la branche est mieux notée
    await _oublier(async_session)
    async with test_client_factory(org.utilisateur) as client:
        vue = (await _comparer(client, agent, f"branche:{principale.id}", f"branche:{branche.id}")).json()
    assert vue["verdict"] == {"gagnant": "egalite", "pour_gauche": ["resolution"], "pour_droite": ["note"]}


async def test_deux_versions_ou_une_version_contre_une_branche(org, db_session, async_session, test_client_factory, appels):
    agent, branche, principale, version_branche = await _monde(org, db_session)
    appels += _appels(agent.id, 1, 6, issues=2)
    appels += _appels(agent.id, version_branche.version_number, 6, issues=6)
    await _oublier(async_session)
    async with test_client_factory(org.utilisateur) as client:
        vue = (await _comparer(client, agent, "version:1", f"version:{version_branche.version_number}")).json()
        assert (vue["gauche"]["type"], vue["gauche"]["nom"], vue["droite"]["nom"]) == ("version", "Principale", "Essai")
        assert vue["gauche"]["part"] is None and "part" not in {m["cle"] for m in vue["mesures"]}
        mixte = (await _comparer(client, agent, "version:1", f"branche:{branche.id}")).json()
        assert mixte["droite"]["version"] == version_branche.version_number
        for mauvais in ("version:99", "branche:999999", "n'importe quoi", "version:", "branche:-1"):
            assert (await _comparer(client, agent, "version:1", mauvais)).status_code in (404, 422), mauvais


async def test_la_difference_de_configuration_est_champ_par_champ_et_sans_cle_en_clair(org, db_session, async_session, test_client_factory, appels):
    agent, branche, principale, version_branche = await _monde(org, db_session)
    await _oublier(async_session)
    async with test_client_factory(org.utilisateur) as client:
        vue = (await _comparer(client, agent, f"branche:{principale.id}", f"branche:{branche.id}")).json()
    lignes = {c["cle"]: c for c in vue["configuration"]}
    assert lignes["prompt:1"]["famille"] == "prompts" and lignes["prompt:1"]["avant"] == "p1" and lignes["prompt:1"]["apres"] == "Allô, cabinet"
    assert lignes["reglage:voix"]["famille"] == "reglages" and lignes["reglage:voix"]["avant"] is None and lignes["reglage:voix"]["apres"] == "b"
    assert lignes["prompt:1"]["libelle"] == "Départ"


async def test_les_appels_d_un_autre_agent_ne_sont_jamais_comptes_et_une_autre_organisation_a_un_404(
    org, autre_org, db_session, async_session, test_client_factory, appels
):
    agent, branche, principale, version_branche = await _monde(org, db_session)
    autre = await db_session.create_workflow(
        name="Autre", workflow_definition=_graphe(), user_id=org.utilisateur.id, organization_id=org.organisation.id
    )
    appels += _appels(agent.id, 1, 6, issues=6)
    appels += _appels(autre.id, 1, 50, issues=0)  # mêmes numéros de version, un autre agent
    await _oublier(async_session)
    async with test_client_factory(org.utilisateur) as client:
        vue = (await _comparer(client, agent, f"branche:{principale.id}", f"branche:{branche.id}")).json()
        assert {m["cle"]: m for m in vue["mesures"]}["appels"]["gauche"] == 6
        # une branche d'un AUTRE agent n'est pas lisible par cet agent
        autre_branche, _ = await db_session.creer_une_branche(org.organisation.id, autre.id, "Autre", depuis_definition_id=None, user_id=org.utilisateur.id)
        assert (await _comparer(client, agent, f"branche:{principale.id}", f"branche:{autre_branche.id}")).status_code == 404
    async with test_client_factory(autre_org.utilisateur) as client:
        assert (await _comparer(client, agent, f"branche:{principale.id}", f"branche:{branche.id}")).status_code == 404
