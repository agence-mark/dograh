"""[.mark] V4 : « Publier » ne grossit plus avec l'historique de l'organisation.

La question : ce que la publication relit (qui lit quel objet, quel module sert à qui) charge-t-il TOUTES les versions de tous les
agents, ou seulement la version publiée ? Mesuré : 600 anciennes versions de 100 Ko ajoutaient la moitié du temps de la route.
"""

from __future__ import annotations

from api.db.models import OrganizationModel, UserModel
from api.services.groupe.agents_servis import _version_publiee, lire_agents_lus
from api.services.objets_agent.utilisation import _agents_publies

GRAPHE = {
    "nodes": [
        {"id": "1", "type": "startCall", "data": {"name": "Start", "prompt": "Bonjour {{marque}}"}},
        {"id": "2", "type": "endCall", "data": {"name": "End", "prompt": "Au revoir"}},
    ],
    "edges": [{"id": "e1", "source": "1", "target": "2", "data": {"label": "End"}}],
}


async def _agent_avec_historique(db_session, async_session, fournisseur: str, versions: int):
    org = OrganizationModel(provider_id=f"org-{fournisseur}")
    async_session.add(org)
    await async_session.flush()
    user = UserModel(provider_id=f"user-{fournisseur}", selected_organization_id=org.id)
    async_session.add(user)
    await async_session.flush()
    workflow = await db_session.create_workflow(name="Accueil", workflow_definition=GRAPHE, user_id=user.id, organization_id=org.id)
    for numero in range(versions):
        graphe = {**GRAPHE, "nodes": [{**GRAPHE["nodes"][0], "data": {"name": "Start", "prompt": f"Version {numero}"}}, GRAPHE["nodes"][1]]}
        await db_session.save_workflow_draft(workflow_id=workflow.id, workflow_definition=graphe)
        await db_session.publish_workflow_draft(workflow.id)
    await db_session.save_workflow_draft(workflow_id=workflow.id, workflow_definition=GRAPHE)  # un brouillon en cours
    return org, workflow


async def test_la_lecture_des_agents_publies_ne_charge_que_la_version_publiee(db_session, async_session):
    org, workflow = await _agent_avec_historique(db_session, async_session, "legere", 4)
    toutes = await db_session.list_workflows_for_model_configuration_migration(org.id)
    assert len(toutes[0].definitions) >= 5  # l'historique entier, brouillon compris : ce que la route ne doit plus charger
    async_session.expunge_all()  # une session neuve, comme à chaque requête : pas de collection déjà chargée
    legeres = await db_session.list_workflows_with_published_versions(org.id)
    assert [w.id for w in legeres] == [workflow.id]
    assert {d.status for d in legeres[0].definitions} == {"published"} and len(legeres[0].definitions) == 1
    # Le résultat ne change pas : la même version est désignée comme publiée.
    assert _version_publiee(legeres[0]).id == _version_publiee(toutes[0]).id
    assert _version_publiee(legeres[0]).workflow_json["nodes"][0]["data"]["prompt"] == "Version 3"


async def test_la_lecture_est_cloisonnee_par_organisation(db_session, async_session):
    org_a, _ = await _agent_avec_historique(db_session, async_session, "a", 1)
    org_b, wf_b = await _agent_avec_historique(db_session, async_session, "b", 1)
    assert [w.id for w in await db_session.list_workflows_with_published_versions(org_b.id)] == [wf_b.id]
    assert all(w.organization_id == org_a.id for w in await db_session.list_workflows_with_published_versions(org_a.id))


async def test_qui_lit_quoi_et_les_agents_lus_donnent_les_memes_reponses(db_session, async_session):
    org, workflow = await _agent_avec_historique(db_session, async_session, "memes", 3)
    [(identifiant, nom, texte)] = await _agents_publies(org.id)
    assert (identifiant, nom) == (workflow.id, "Accueil") and "Version 2" in texte and "Version 0" not in texte
    agents, _outils = await lire_agents_lus(org.id)
    assert [a.id for a in agents] == [workflow.id]


async def test_la_base_retire_les_graphes_des_instantanes_et_ne_lit_que_les_cles(db_session, async_session):
    # V4 : la liste des versions restaurables et le rangement d'un instantané ne lisent plus les graphes (50 x 2 par agent).
    org_a = OrganizationModel(provider_id="org-instantanes-a")
    org_b = OrganizationModel(provider_id="org-instantanes-b")
    async_session.add_all([org_a, org_b])
    await async_session.flush()
    lourd = {"nodes": [{"id": str(i)} for i in range(50)]}
    for numero in (1, 2, 3):
        await db_session.upsert_configuration(
            org_a.id, f"MARK_BUILDER:9:instantanes:{numero:06d}", {"numero": numero, "cause": "x", "avant": lourd, "apres": lourd}
        )
    await db_session.upsert_configuration(org_a.id, "MARK_BUILDER:9:instantanesX:000001", {"numero": 99})  # le « _ » du préfixe n'est pas un joker
    await db_session.upsert_configuration(org_a.id, "MARK_BUILDER:10:instantanes:000001", {"numero": 77})
    await db_session.upsert_configuration(org_b.id, "MARK_BUILDER:9:instantanes:000001", {"numero": 55, "avant": lourd})
    prefixe = "MARK_BUILDER:9:instantanes:"
    assert await db_session.get_configuration_keys_by_prefix(org_a.id, prefixe) == [f"{prefixe}{n:06d}" for n in (1, 2, 3)]
    lignes = await db_session.get_configurations_by_prefix_without(org_a.id, prefixe, ["avant", "apres"])
    assert [(cle, valeur) for cle, valeur in lignes] == [(f"{prefixe}{n:06d}", {"numero": n, "cause": "x"}) for n in (1, 2, 3)]
    # Une autre organisation ne voit rien de celle-ci, et inversement.
    assert [v["numero"] for _c, v in await db_session.get_configurations_by_prefix_without(org_b.id, prefixe, ["avant"])] == [55]
    assert await db_session.get_configuration_keys_by_prefix(org_b.id, "MARK_BUILDER:10:") == []
