"""[.mark] Builder partie 3, SA-L3b, sous-lot 2 (05 § 9 et § 12) : la répartition du trafic entre branches.

| Test | Ce qu'il prouve |
|---|---|
| règle pure | les branches occupent les places basses dans l'ordre, la principale garde le reste ; clé absente ou masquée : la principale ; une branche sans version ne reçoit rien |
| un appelant reste sur sa branche | en augmentant la part d'une branche, un appelant ne passe que de la principale vers la branche, jamais l'inverse ; trois branches comprises |
| total et curseur | le total est exigé à 100 ; une branche prend 0 ou 1 à 99 ; la principale garde au moins 1 ; toutes les branches actives, et seulement elles |
| atomique | un refus laisse les parts d'avant, intactes |
| réglage | éteint (réglage de l'agent) : refusé ; une branche sans version publiée : refusée ; une branche d'une autre organisation : refusée |
| vrai chemin d'appel (R1) | de VRAIES branches en base, la vraie création de l'appel : l'appelant de la branche reçoit sa version, les autres la principale ; éteint, rien n'est lu |
| route | PUT avec ses refus (un seul format d'erreur), et le journal |
"""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest

from api.db.branches_client import ErreurDeBranche
from api.services.publication import deploiement
from api.tests.mark.test_apres_appel import _organisation, base_v4, smtp  # noqa: F401  (fixtures)
from api.tests.mark.test_sous_dossiers_et_groupe import _oublier, autre_org, org  # noqa: F401

ACTIF = {"publication": {"deploiement": {"actif": True}}}
GRAPHE = {"nodes": [{"id": "1", "type": "agentNode", "position": {"x": 0, "y": 0}, "data": {"name": "Accueil", "prompt": "Bonjour"}}], "edges": []}


def _parts(*branches, principale=(100, 11)):
    """(part, version) de chaque branche non principale, puis la principale."""
    lignes = [{"branche": i + 2, "principale": False, "part": p, "definition": v} for i, (p, v) in enumerate(branches)]
    return lignes + [{"branche": 1, "principale": True, "part": principale[0], "definition": principale[1]}]


# --- la règle pure ---------------------------------------------------------------------------------------------------------------


def test_les_branches_occupent_les_places_basses_et_la_principale_garde_le_reste():
    parts = _parts((20, 12), (30, 13), principale=(50, 11))
    vues = [deploiement.version_attribuee(parts, 5, None, f"appel:{n}") for n in range(2000)]
    assert set(vues) == {11, 12, 13}
    assert 0.14 < vues.count(12) / 2000 < 0.26 and 0.24 < vues.count(13) / 2000 < 0.36 and 0.44 < vues.count(11) / 2000 < 0.56


def test_cle_masquee_ou_vide_reste_sur_la_principale_et_une_branche_sans_version_ne_recoit_rien():
    parts = _parts((99, 12), principale=(1, 11))
    assert deploiement.version_attribuee(parts, 5, "") == 11 and deploiement.version_attribuee(parts, 5, None, "") == 11
    sans_version = _parts((99, None), principale=(1, 11))
    assert {deploiement.version_attribuee(sans_version, 5, None, f"appel:{n}") for n in range(200)} == {11}
    libre = _parts((50, 12), principale=(50, None))  # principale libre : la version publiée (None)
    assert None in {deploiement.version_attribuee(libre, 5, None, f"appel:{n}") for n in range(200)}


def test_un_appelant_ne_quitte_jamais_sa_branche_quand_la_part_de_sa_branche_monte():
    cles = [f"appel:{n}" for n in range(1500)]
    avant = {c: deploiement.version_attribuee(_parts((10, 12), (10, 13), principale=(80, 11)), 5, None, c) for c in cles}
    apres = {c: deploiement.version_attribuee(_parts((25, 12), (10, 13), principale=(65, 11)), 5, None, c) for c in cles}
    for c in cles:
        if avant[c] == 12:
            assert apres[c] == 12, "un appelant de la branche 12 ne doit pas la quitter quand sa part monte"
        if avant[c] == 13:
            assert apres[c] in (12, 13)  # la branche 13 est décalée par la montée de la 12, mais ne retourne pas à la principale
    assert sum(1 for c in cles if avant[c] != apres[c]) > 0


# --- total, curseur, atomicité --------------------------------------------------------------------------------------------------


async def _agent_avec_deux_branches(db_session, org):
    agent = await db_session.create_workflow(
        name="Agent", workflow_definition=GRAPHE, user_id=org.utilisateur.id, organization_id=org.organisation.id,
        workflow_configurations=ACTIF,
    )
    o = org.organisation.id
    a, _ = await db_session.creer_une_branche(o, agent.id, "A", depuis_definition_id=None, user_id=org.utilisateur.id)
    b, _ = await db_session.creer_une_branche(o, agent.id, "B", depuis_definition_id=None, user_id=org.utilisateur.id)
    principale = await db_session.obtenir_la_principale(o, agent.id)
    return agent, principale, a, b


async def _parts_en_base(db_session, org, agent):
    return {b.id: b.part_trafic for b in await db_session.lister_les_branches(org.organisation.id, agent.id)}


async def test_le_total_fait_cent_et_le_curseur_va_de_un_a_quatre_vingt_dix_neuf(org, db_session):
    agent, principale, a, b = await _agent_avec_deux_branches(db_session, org)
    o = org.organisation.id
    ecrites = await db_session.regler_la_repartition(o, agent.id, {principale.id: 70, a.id: 20, b.id: 10})
    assert {x.id: x.part_trafic for x in ecrites} == {principale.id: 70, a.id: 20, b.id: 10}
    refus = {
        "total 99": ({principale.id: 69, a.id: 20, b.id: 10}, "total"),
        "total 101": ({principale.id: 71, a.id: 20, b.id: 10}, "total"),
        "une branche à 100": ({principale.id: 0, a.id: 100, b.id: 0}, "part"),
        "principale à 0": ({principale.id: 0, a.id: 60, b.id: 40}, "part"),
        "part négative": ({principale.id: 110, a.id: -10, b.id: 0}, "part"),
        "branche manquante": ({principale.id: 80, a.id: 20}, "branches"),
        "branche inconnue": ({principale.id: 80, a.id: 10, b.id: 10, 999999: 0}, "branches"),
        "part décimale": ({principale.id: 70, a.id: 20.5, b.id: 9.5}, "part"),
        "part booléenne": ({principale.id: 98, a.id: True, b.id: True}, "part"),
    }
    for nom, (parts, code) in refus.items():
        with pytest.raises(ErreurDeBranche) as e:
            await db_session.regler_la_repartition(o, agent.id, parts)
        assert e.value.code == code, nom
        assert await _parts_en_base(db_session, org, agent) == {principale.id: 70, a.id: 20, b.id: 10}, f"{nom} : rien n'a changé"
    # les bornes du curseur sont permises : 1 et 99
    await db_session.regler_la_repartition(o, agent.id, {principale.id: 1, a.id: 99, b.id: 0})
    await db_session.regler_la_repartition(o, agent.id, {principale.id: 98, a.id: 1, b.id: 1})


# --- le réglage (service) ------------------------------------------------------------------------------------------------------


async def test_eteint_une_part_est_refusee_et_une_branche_sans_version_ne_recoit_rien(org, autre_org, db_session):
    from api.services.branches import service

    agent, principale, a, b = await _agent_avec_deux_branches(db_session, org)
    o = org.organisation.id
    # éteint (réglage de l'agent) : refusé, mais 0 % partout reste permis
    eteint = await db_session.get_workflow(agent.id, organization_id=o)
    eteint.released_definition.workflow_configurations = {}
    eteint.workflow_configurations = {}
    with pytest.raises(ErreurDeBranche) as e:
        await service.regler_la_repartition(o, eteint, {principale.id: 80, a.id: 20, b.id: 0})
    assert e.value.code == "eteint"
    assert (await service.regler_la_repartition(o, eteint, {principale.id: 100, a.id: 0, b.id: 0}))["parts"][principale.id] == 100
    # allumé : une branche SANS version publiée ne reçoit rien
    allume = await db_session.get_workflow(agent.id, organization_id=o)
    allume.released_definition.workflow_configurations = ACTIF
    from sqlalchemy import update

    from api.db.models_builder import WorkflowBranchModel

    async with db_session.async_session() as session:
        await session.execute(update(WorkflowBranchModel).where(WorkflowBranchModel.id == b.id).values(head_definition_id=None))
        await session.commit()
    with pytest.raises(ErreurDeBranche) as e:
        await service.regler_la_repartition(o, allume, {principale.id: 90, a.id: 0, b.id: 10})
    assert e.value.code == "sans_version"
    assert (await service.regler_la_repartition(o, allume, {principale.id: 90, a.id: 10, b.id: 0}))["parts"][a.id] == 10
    # une autre organisation ne règle rien (l'agent n'existe pas pour elle)
    with pytest.raises(ErreurDeBranche) as e:
        await db_session.regler_la_repartition(autre_org.organisation.id, agent.id, {principale.id: 90, a.id: 10, b.id: 0})
    assert e.value.code == "introuvable"


# --- le vrai chemin d'appel (R1) ---------------------------------------------------------------------------------------------


async def test_vraie_creation_d_appel_l_appelant_de_la_branche_recoit_sa_version_et_eteint_rien_n_est_lu(org, db_session):
    """Aucune doublure de la lecture : de vraies branches en base, la vraie fonction de création du run."""
    from api.services.workflow.run_creation import definition_to_run

    o = org.organisation.id
    agent = await db_session.create_workflow(
        name="Agent", workflow_definition=GRAPHE, user_id=org.utilisateur.id, organization_id=o, workflow_configurations=ACTIF
    )
    ancienne = agent.released_definition_id
    await db_session.save_workflow_draft(agent.id, workflow_definition={"nodes": [], "edges": [], "n": 2}, workflow_configurations=ACTIF)
    nouvelle = (await db_session.publish_workflow_draft(agent.id)).id  # la principale suit la nouvelle publiée
    branche, _ = await db_session.creer_une_branche(o, agent.id, "Essai", depuis_definition_id=ancienne, user_id=org.utilisateur.id)
    principale = await db_session.obtenir_la_principale(o, agent.id)
    await db_session.regler_la_repartition(o, agent.id, {principale.id: 60, branche.id: 40})
    workflow = await db_session.get_workflow(agent.id, organization_id=o)

    cles = [f"0611{n:06d}" for n in range(200)]
    obtenues = {}
    for c in cles:
        definition = await definition_to_run(db_session, workflow, appelant=c)
        obtenues[c] = definition.id
    assert set(obtenues.values()) == {ancienne, nouvelle}, "40 % sur la branche (v1), le reste sur la version en ligne (v2)"
    sur_branche = sum(1 for v in obtenues.values() if v == ancienne)
    assert 50 < sur_branche < 110
    # le même appelant retombe toujours du même côté
    for c in cles[:20]:
        assert (await definition_to_run(db_session, workflow, appelant=c)).id == obtenues[c]
    # la branche monte : ceux qui y étaient y restent
    await db_session.regler_la_repartition(o, agent.id, {principale.id: 30, branche.id: 70})
    for c in cles:
        if obtenues[c] == ancienne:
            assert (await definition_to_run(db_session, workflow, appelant=c)).id == ancienne
    # éteint : rien n'est lu, la version publiée pour tous
    workflow.released_definition.workflow_configurations = {}
    workflow.workflow_configurations = {}
    with patch.object(deploiement, "lire", new=AsyncMock()) as lire:
        assert {(await definition_to_run(db_session, workflow, appelant=c)).id for c in cles[:30]} == {nouvelle}
    lire.assert_not_awaited()


# --- la route ----------------------------------------------------------------------------------------------------------------------


async def test_la_route_regle_les_parts_refuse_avec_un_seul_format_d_erreur_et_journalise(org, autre_org, db_session, async_session, test_client_factory):
    agent, principale, a, b = await _agent_avec_deux_branches(db_session, org)
    await _oublier(async_session)
    journal = []

    async def journaliser(user, action, organization_id, detail=None):
        journal.append((action, organization_id, detail))

    with patch("api.services.equipe_mark.acces.journaliser", journaliser):
        async with test_client_factory(org.utilisateur) as client:
            ok = await client.put(f"/api/v1/builder/branches/{agent.id}/repartition", json={"parts": {str(principale.id): 75, str(a.id): 25, str(b.id): 0}})
            assert ok.status_code == 200, ok.text
            for corps in (
                {"parts": {str(principale.id): 70, str(a.id): 20, str(b.id): 5}},
                {"parts": {str(principale.id): 0, str(a.id): 100, str(b.id): 0}},
                {"parts": {"x": 1}},
                {"parts": {}},
                {"autre": 1},
            ):
                r = await client.put(f"/api/v1/builder/branches/{agent.id}/repartition", json=corps)
                assert r.status_code == 422 and "detail" in r.json(), corps
            vue = (await client.get(f"/api/v1/builder/branches/{agent.id}")).json()
            assert {br["nom"]: br["part"] for br in vue["branches"]} == {"Principale": 75, "A": 25, "B": 0}
        async with test_client_factory(autre_org.utilisateur) as client:
            r = await client.put(f"/api/v1/builder/branches/{agent.id}/repartition", json={"parts": {str(principale.id): 100}})
            assert r.status_code == 404
    assert [j[0] for j in journal] == ["agents.repartition_du_trafic"] and journal[0][2]["parts"] == {principale.id: 75, a.id: 25, b.id: 0}
