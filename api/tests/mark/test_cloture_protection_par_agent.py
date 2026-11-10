"""[.mark] Clôture, lot B (D5, D6, D7) : « Protéger la version en ligne » est un réglage PAR AGENT.

| Test | Ce qu'il prouve |
|---|---|
| D5 règle | non réglée : allumée chez un client en ligne, éteinte au Labo (comme avant) |
| D5 réglage | allumée ou éteinte par l'équipe pour CET agent, chez un client comme au Labo ; « null » revient à la règle |
| D6 | un agent neuf chez un client n'est pas protégé (le builder le construit librement) ; il l'est dès sa première publication par une personne |
| D5 route | la route pose le choix, la vue le montre, le geste est écrit au journal avec la personne |
| D7 | les corrections en un clic et les modèles de réglages écrivent par ``update_workflow`` : sur un agent protégé ils sont refusés (donc par une branche), levée la protection ils écrivent |
"""

from __future__ import annotations

import pytest

from api.db.protection_principale import PrincipaleProtegee
from api.tests.mark.test_principale_protegee import (  # noqa: F401  (fixtures et aides)
    AUTRE,
    GRAPHE,
    _agent,
    _branche_fermee,
    _protegee,
    labo_est,
)
from api.tests.mark.test_apres_appel import _organisation, base_v4, smtp  # noqa: F401
from api.tests.mark.test_sous_dossiers_et_groupe import _oublier, autre_org, org  # noqa: F401


async def test_non_reglee_la_regle_par_defaut_joue(org, autre_org, db_session, labo_est):
    agent = await _agent(db_session, org)
    assert await db_session.protection_reglee_de_la_principale(org.organisation.id, agent.id) is None
    labo_est(autre_org.organisation.id)
    assert await _protegee(db_session, agent.id) is True  # un client en ligne
    labo_est(org.organisation.id)
    assert await _protegee(db_session, agent.id) is False  # le Labo


async def test_l_equipe_leve_ou_pose_la_protection_d_un_agent_puis_revient_a_la_regle(org, autre_org, db_session, labo_est):
    agent = await _agent(db_session, org)
    org_id = org.organisation.id
    labo_est(autre_org.organisation.id)  # l'agent est chez un client
    await db_session.regler_la_protection_de_la_principale(org_id, agent.id, False)
    assert await _protegee(db_session, agent.id) is False
    await db_session.save_workflow_draft(agent.id, workflow_definition=AUTRE)  # la protection levée : il s'écrit
    await db_session.regler_la_protection_de_la_principale(org_id, agent.id, None)
    assert await _protegee(db_session, agent.id) is True  # retour à la règle
    labo_est(org_id)  # l'agent est au Labo : la règle n'impose rien
    assert await _protegee(db_session, agent.id) is False
    await db_session.regler_la_protection_de_la_principale(org_id, agent.id, True)
    assert await _protegee(db_session, agent.id) is True
    assert await db_session.protection_reglee_de_la_principale(org_id, agent.id) is True
    with pytest.raises(PrincipaleProtegee):
        await db_session.save_workflow_draft(agent.id, workflow_definition=GRAPHE)


async def test_un_agent_neuf_chez_un_client_se_construit_puis_la_premiere_publication_par_une_personne_l_allume(org, autre_org, db_session, labo_est):
    neuf = await _agent(db_session, org, publie_par_une_personne=False)
    labo_est(autre_org.organisation.id)
    assert await _protegee(db_session, neuf.id) is False
    await db_session.save_workflow_draft(neuf.id, workflow_definition=AUTRE)  # le builder construit librement
    from api.db.models import WorkflowDefinitionModel

    async with db_session.async_session() as s:  # la première publication par une personne (version de la principale de plus)
        s.add(WorkflowDefinitionModel(workflow_id=neuf.id, workflow_json=GRAPHE, status="archived", is_current=False))
        await s.commit()
    assert await _protegee(db_session, neuf.id) is True


async def test_les_corrections_et_les_modeles_de_reglages_ecrivent_par_update_workflow_et_suivent_la_protection(org, autre_org, db_session, labo_est):
    agent = await _agent(db_session, org)
    org_id = org.organisation.id
    labo_est(autre_org.organisation.id)

    async def ecrire():
        await db_session.update_workflow(
            workflow_id=agent.id,
            name=None,
            workflow_definition=AUTRE,
            template_context_variables=None,
            workflow_configurations=None,
            organization_id=org_id,
        )

    with pytest.raises(PrincipaleProtegee):
        await ecrire()
    await db_session.regler_la_protection_de_la_principale(org_id, agent.id, False)
    await ecrire()


async def test_la_route_pose_le_choix_la_vue_le_montre_et_le_journal_garde_la_personne(org, autre_org, db_session, async_session, test_client_factory, labo_est):
    agent = await _agent(db_session, org)
    labo_est(autre_org.organisation.id)
    await _oublier(async_session)
    async with test_client_factory(org.utilisateur) as client:
        adresse = f"/api/v1/builder/branches/{agent.id}/principale/protection"
        leve = await client.put(adresse, json={"protegee": False})
        assert leve.status_code == 200 and leve.json()["protegee"] is False and leve.json()["reglee"] is False, leve.text
        vue = (await client.get(f"/api/v1/builder/branches/{agent.id}")).json()["branches"][0]
        assert vue["protegee"] is False and vue["protection_reglee"] is False
    lignes, _ = await db_session.lister_journal(limit=10, offset=0, organization_id=org.organisation.id, actions=["agents.principale_protegee"])
    assert lignes and lignes[0]["detail"]["reglee"] is False and lignes[0]["user_id"] == org.utilisateur.id


# --- D7 : sur un agent protégé, une correction ou un modèle s'écrit sur une copie de travail ----------------------------------------
async def test_sur_un_agent_protege_le_geste_s_ecrit_sur_une_branche_et_la_principale_ne_bouge_pas(org, autre_org, db_session, labo_est):
    from api.db import branche_ouverte
    from api.services.branches.sur_une_branche import sur_une_branche_si_protegee

    agent = await _agent(db_session, org)
    org_id = org.organisation.id
    labo_est(autre_org.organisation.id)  # chez un client : protégé par la règle
    async with sur_une_branche_si_protegee(org_id, agent, org.utilisateur, "d'un réglage") as branche:
        assert branche is not None and branche["nom"].startswith("Correction")
        assert branche_ouverte.courante().branch_id == branche["id"]
        await db_session.update_workflow(
            workflow_id=agent.id,
            name=None,
            workflow_definition=AUTRE,
            template_context_variables=None,
            workflow_configurations=None,
            organization_id=org_id,
        )
    assert branche_ouverte.courante().branch_id is None  # la requête retrouve la principale
    relu = await db_session.get_workflow(agent.id, organization_id=org_id)
    assert relu.workflow_definition == GRAPHE  # la principale n'a pas bougé
    vue = await db_session.lister_les_branches(org_id, agent.id)
    assert [b.nom for b in vue if not b.est_principale] == [branche["nom"]]
    # un second geste ne reprend pas le nom pris
    async with sur_une_branche_si_protegee(org_id, agent, org.utilisateur, "d'un réglage") as seconde:
        assert seconde["nom"] != branche["nom"]


async def test_sans_protection_ou_sur_une_branche_deja_ouverte_rien_ne_change(org, autre_org, db_session, labo_est):
    from api.db import branche_ouverte
    from api.services.branches.sur_une_branche import sur_une_branche_si_protegee

    agent = await _agent(db_session, org)
    org_id = org.organisation.id
    labo_est(org_id)  # au Labo : pas protégé
    async with sur_une_branche_si_protegee(org_id, agent, org.utilisateur, "d'un réglage") as branche:
        assert branche is None
    labo_est(autre_org.organisation.id)
    branche_ouverte.ouvrir(12345, org.utilisateur.id)  # la personne travaille déjà sur une branche
    async with sur_une_branche_si_protegee(org_id, agent, org.utilisateur, "d'un réglage") as branche:
        assert branche is None
    assert branche_ouverte.courante().branch_id == 12345


async def test_une_correction_qui_echoue_n_laisse_pas_de_branche_orpheline(org, autre_org, db_session, labo_est):
    """SA-9 (7) : si le geste échoue après la création de la branche « Correction … », la branche est archivée et l'erreur d'origine est relevée."""
    from api.db import branche_ouverte
    from api.services.branches.sur_une_branche import sur_une_branche_si_protegee

    agent = await _agent(db_session, org)
    org_id = org.organisation.id
    labo_est(autre_org.organisation.id)
    avant = [b.nom for b in await db_session.lister_les_branches(org_id, agent.id)]
    with pytest.raises(RuntimeError, match="geste en échec"):
        async with sur_une_branche_si_protegee(org_id, agent, org.utilisateur, "d'un réglage"):
            raise RuntimeError("geste en échec")
    assert [b.nom for b in await db_session.lister_les_branches(org_id, agent.id)] == avant  # plus aucune branche active en plus
    assert any(b.nom.startswith("Correction") and b.statut == "archived" for b in await db_session.lister_les_branches(org_id, agent.id, avec_archivees=True))
    assert branche_ouverte.courante().branch_id is None
    # la principale n'est jamais archivée par ce chemin
    principale = next(b for b in await db_session.lister_les_branches(org_id, agent.id) if b.est_principale)
    assert await db_session.archiver_une_branche_ouverte_en_vain(org_id, agent.id, principale.id) is False
    # un geste réussi garde sa branche (elle se relit et se fusionne)
    async with sur_une_branche_si_protegee(org_id, agent, org.utilisateur, "d'un réglage") as reussie:
        pass
    assert reussie["nom"] in [b.nom for b in await db_session.lister_les_branches(org_id, agent.id)]
