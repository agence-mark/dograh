"""[.mark] Builder partie 3, SA-L3c, sous-lot 2 (05 § 12) : « Revenir avant » est propre à la branche.

| Test | Ce qu'il prouve |
|---|---|
| rangement | un instantané porte la branche où il a été pris (la principale pour tous ceux d'avant) |
| liste | la liste ne montre que les instantanés de la branche ouverte |
| restauration | restaurer dans une branche écrit le brouillon DE CETTE branche, jamais celui de la principale ni d'une autre ; l'instantané d'une autre branche est inconnu (404) |
| aperçu | l'aperçu d'une restauration d'une autre branche est refusé de même |
| protection | l'étiquette de protection de la vue et la route qui la pose ; la principale d'un client en ligne ne se déprotège pas |
"""

from __future__ import annotations

import pytest

from api.db import branche_ouverte
from api.services.builder import apercu, revue
from api.tests.mark.builder_commun import graphe_depart
from api.tests.mark.test_apres_appel import _organisation, base_v4, smtp  # noqa: F401  (fixtures)
from api.tests.mark.test_sous_dossiers_et_groupe import _oublier, autre_org, org  # noqa: F401


@pytest.fixture(autouse=True)
def _branche_fermee():
    branche_ouverte.ouvrir(None, None)
    yield
    branche_ouverte.ouvrir(None, None)


def _graphe(prompt):
    g = graphe_depart()
    g["nodes"][0]["data"]["prompt"] = prompt
    return g


async def _ranger(org, agent_id, prompt, cause="essai"):
    return await revue._ranger(  # noqa: SLF001
        org.organisation.id,
        agent_id,
        cause=cause,
        avant=_graphe(prompt),
        apres=_graphe(prompt),
        version_avant=1,
        version_apres=1,
        fil_id=None,
        operations=[],
        complement=None,
    )


async def _monde(org, db_session):
    agent = await db_session.create_workflow(
        name="Agent", workflow_definition=graphe_depart(), user_id=org.utilisateur.id, organization_id=org.organisation.id
    )
    branche, _ = await db_session.creer_une_branche(org.organisation.id, agent.id, "Essai", depuis_definition_id=None, user_id=org.utilisateur.id)
    return agent, branche


async def test_un_instantane_porte_sa_branche_et_la_liste_ne_montre_que_celle_ouverte(org, db_session):
    agent, branche = await _monde(org, db_session)
    sur_principale = await _ranger(org, agent.id, "principale")
    branche_ouverte.ouvrir(branche.id, org.utilisateur.id)
    sur_branche = await _ranger(org, agent.id, "branche")
    assert [v["numero"] for v in await revue.instantanes(org.organisation.id, agent.id)] == [sur_branche]
    branche_ouverte.ouvrir(None, org.utilisateur.id)
    assert [v["numero"] for v in await revue.instantanes(org.organisation.id, agent.id)] == [sur_principale]


async def test_restaurer_dans_une_branche_n_ecrit_que_son_brouillon(org, db_session):
    agent, branche = await _monde(org, db_session)
    moi = org.utilisateur.id
    sur_principale = await _ranger(org, agent.id, "principale")
    branche_ouverte.ouvrir(branche.id, moi)
    sur_branche = await _ranger(org, agent.id, "branche")
    relu = await db_session.get_workflow(agent.id, organization_id=org.organisation.id)

    rendu = await revue.restaurer(org.organisation.id, relu, sur_branche, familles=["schema"], user=org.utilisateur)
    assert rendu["familles"] == ["schema"]
    assert (await db_session.get_draft_version(agent.id)).workflow_json["nodes"][0]["data"]["prompt"] == "branche"
    # le brouillon de la principale n'a pas bougé (il n'existe pas), l'agent non plus
    branche_ouverte.ouvrir(None, moi)
    assert await db_session.get_draft_version(agent.id) is None
    # l'instantané de la principale est inconnu sur la branche, et celui de la branche sur la principale
    with pytest.raises(revue.ErreurRevue, match="Unknown version"):
        await revue.restaurer(org.organisation.id, relu, sur_branche, familles=["schema"], user=org.utilisateur)
    branche_ouverte.ouvrir(branche.id, moi)
    with pytest.raises(revue.ErreurRevue, match="Unknown version"):
        await revue.restaurer(org.organisation.id, relu, sur_principale, familles=["schema"], user=org.utilisateur)
    # l'aperçu de même
    with pytest.raises(revue.ErreurRevue, match="Unknown version"):
        await apercu.apercu_de_la_restauration(org.organisation.id, relu, sur_principale, org.utilisateur)


async def test_la_vue_dit_la_protection_et_la_route_la_pose(org, autre_org, db_session, async_session, test_client_factory, monkeypatch):
    agent, _ = await _monde(org, db_session)
    await _oublier(async_session)
    async with test_client_factory(org.utilisateur) as client:
        vue = (await client.get(f"/api/v1/builder/branches/{agent.id}")).json()
        assert vue["branches"][0]["protegee"] is False and vue["branches"][0]["protegee_par_defaut"] is False
        r = await client.put(f"/api/v1/builder/branches/{agent.id}/principale/protection", json={"protegee": True})
        assert r.status_code == 200 and r.json()["protegee"] is True and r.json()["protegee_par_defaut"] is False, r.text
        # clôture, lot B (D5) : chez un client en ligne la règle protège par défaut, mais l'équipe peut lever la protection de CET agent ;
        # « en ligne » = publié par une personne après la création (2bc67d71), d'où une version de la principale de plus
        from api.db.models import WorkflowDefinitionModel

        async with db_session.async_session() as s:
            s.add(WorkflowDefinitionModel(workflow_id=agent.id, workflow_json={}, status="archived", is_current=False))
            await s.commit()
        monkeypatch.setattr("api.services.builder.constantes.organisation_bibliotheque", lambda: autre_org.organisation.id)
        r = await client.put(f"/api/v1/builder/branches/{agent.id}/principale/protection", json={"protegee": False})
        assert r.json() == {"ok": True, "protegee": False, "protegee_par_defaut": False, "reglee": False}
        r = await client.put(f"/api/v1/builder/branches/{agent.id}/principale/protection", json={"protegee": None})  # retour à la règle
        assert r.json() == {"ok": True, "protegee": True, "protegee_par_defaut": True, "reglee": None}
        vue = (await client.get(f"/api/v1/builder/branches/{agent.id}")).json()
        assert vue["branches"][0]["protegee"] is True and vue["branches"][0]["protegee_par_defaut"] is True
        assert vue["branches"][0]["protection_reglee"] is None


async def test_la_protection_d_un_autre_agent_ou_organisation_est_un_404(org, autre_org, db_session, async_session, test_client_factory):
    agent, _ = await _monde(org, db_session)
    await _oublier(async_session)
    async with test_client_factory(autre_org.utilisateur) as client:
        r = await client.put(f"/api/v1/builder/branches/{agent.id}/principale/protection", json={"protegee": True})
        assert r.status_code == 404
