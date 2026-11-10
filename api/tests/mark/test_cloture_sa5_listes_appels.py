"""[.mark] Clôture SA-5 (Evan, 09/11) : les listes d'appels d'un agent (É35) et de tous les clients (É8) comme la maquette.

Ce qui doit tenir : chaque ligne rend motif, résumé (celui de l'après-appel, sinon du modèle), issue, durée, « jugé par » et note dans la
MÊME requête ; le filtre de motif est exact et la recherche (motif, issue, résumé) se font dans la requête, cloisonnés par organisation (et
par agent), bornés (3 lettres, jokers = texte) ; la liste des motifs proposée au filtre ne porte que les motifs de la portée ; aucune
migration (colonnes déjà là : ``note_juge``, annotations ``juge`` et ``mark_apres_appel``).
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from api.db.appels_liste import juge_par
from api.db.models import OrganizationModel, UserModel, WorkflowRunModel

GRAPHE = {"nodes": [{"id": "1", "type": "startCall", "data": {"name": "Start", "prompt": "Hello"}}], "edges": []}
SYNTHESE = "La personne voulait un devis pour une chaudière. L'assistant a pris ses coordonnées. Un rappel a été promis."


async def _monde(async_session, db_session, nom):
    org = OrganizationModel(provider_id=f"org-sa5-{nom}")
    async_session.add(org)
    await async_session.flush()
    user = UserModel(provider_id=f"user-sa5-{nom}", selected_organization_id=org.id)
    async_session.add(user)
    await async_session.flush()
    agent = await db_session.create_workflow(name=f"Agent {nom}", workflow_definition=GRAPHE, user_id=user.id, organization_id=org.id)
    return org, agent


async def _run(async_session, agent, *, fiche=None, annotations=None, note=None, duree=42, jours=1):
    run = WorkflowRunModel(
        name="run",
        workflow_id=agent.id,
        mode="twilio",
        created_at=datetime.now(UTC) - timedelta(days=jours),
        usage_info={"call_duration_seconds": duree},
        cost_info={"call_duration_seconds": duree},
        initial_context={"caller_number": "+33611111111"},
        gathered_context=fiche or {},
        logs={"realtime_feedback_events": []},
        annotations=annotations or {},
        note_juge=note,
    )
    async_session.add(run)
    await async_session.flush()
    return run


@pytest.fixture
async def monde(db_session, async_session):
    return await _monde(async_session, db_session, "a"), await _monde(async_session, db_session, "b")


# --- É35 : la liste d'un agent ----------------------------------------------------------------------------------------------------


async def test_la_liste_d_un_agent_rend_motif_resume_issue_juge_par_et_note(db_session, async_session, monde):
    (org_a, agent_a), _ = monde
    await _run(
        async_session, agent_a, fiche={"motif": "Devis", "mapped_call_disposition": "RDV_pris"}, note=4.5,
        annotations={"mark_apres_appel": {"synthese": SYNTHESE}, "juge": {"etat": "juge", "source": "cle_api", "modele": "openai/juge-m"}},
    )
    await _run(async_session, agent_a, fiche={"motif": "Dépannage"})
    runs, total = await db_session.get_workflow_runs_by_workflow_id(agent_a.id, organization_id=org_a.id)
    assert total == 2
    un = next(r for r in runs if r.motif == "Devis")
    assert un.resume == "La personne voulait un devis pour une chaudière. L'assistant a pris ses coordonnées." and un.resume_source == "synthese"
    assert un.note_juge == 4.5 and un.juge_par == "openai/juge-m"
    assert un.gathered_context["mapped_call_disposition"] == "RDV_pris"
    vide = next(r for r in runs if r.motif == "Dépannage")
    assert vide.resume is None and vide.juge_par is None and vide.note_juge is None


async def test_le_filtre_du_motif_d_un_agent_est_exact_et_cloisonne(db_session, async_session, monde):
    (org_a, agent_a), (org_b, agent_b) = monde
    await _run(async_session, agent_a, fiche={"motif": "Devis"})
    await _run(async_session, agent_a, fiche={"motif": "Devis urgent"})
    await _run(async_session, agent_b, fiche={"motif": "Devis"})
    runs, total = await db_session.get_workflow_runs_by_workflow_id(agent_a.id, organization_id=org_a.id, motif="devis")
    assert total == 1 and runs[0].motif == "Devis"
    # L'agent d'un autre client : rien, même avec le bon motif.
    _, ailleurs = await db_session.get_workflow_runs_by_workflow_id(agent_b.id, organization_id=org_a.id, motif="Devis")
    assert ailleurs == 0
    _, joker = await db_session.get_workflow_runs_by_workflow_id(agent_a.id, organization_id=org_a.id, motif="%")
    assert joker == 0


async def test_la_recherche_d_un_agent_lit_motif_issue_et_resume_dans_la_requete(db_session, async_session, monde):
    (org_a, agent_a), (_, agent_b) = monde
    await _run(async_session, agent_a, fiche={"motif": "Prise de rendez-vous"})
    await _run(async_session, agent_a, fiche={"motif": "Autre", "mapped_call_disposition": "Rappel_promis"})
    await _run(async_session, agent_a, fiche={"motif": "Troisième"}, annotations={"mark_apres_appel": {"synthese": SYNTHESE}})
    await _run(async_session, agent_a, fiche={"motif": "Quatrième"}, annotations={"resume_appel": {"texte": "Une plainte sur la facture."}})
    await _run(async_session, agent_b, fiche={"motif": "Prise de rendez-vous"})

    async def chercher(terme):
        _, total = await db_session.get_workflow_runs_by_workflow_id(agent_a.id, organization_id=org_a.id, recherche=terme)
        return total

    assert await chercher("rendez") == 1  # le motif, pas l'agent d'à côté
    assert await chercher("RAPPEL_pro") == 1  # l'issue, sans tenir compte de la casse
    assert await chercher("chaudière") == 1  # le résumé de l'après-appel
    assert await chercher("facture") == 1  # le résumé du modèle
    assert await chercher("ch") == 4  # trop court : ignoré, la liste entière
    assert await chercher("%%%") == 0  # les jokers sont du texte
    assert await chercher("introuvable") == 0


async def test_les_motifs_proposes_ne_viennent_que_de_l_agent_et_de_son_organisation(db_session, async_session, monde):
    (org_a, agent_a), (org_b, agent_b) = monde
    for motif in ("Devis", "devis ", "Dépannage"):
        await _run(async_session, agent_a, fiche={"motif": motif})
    await _run(async_session, agent_a)
    await _run(async_session, agent_b, fiche={"motif": "Secret du voisin"})
    motifs = await db_session.lister_motifs_de_l_agent(agent_a.id, organization_id=org_a.id)
    assert [m.casefold() for m in motifs] == ["dépannage", "devis"]  # « Devis » et « devis » ne font qu'un
    assert await db_session.lister_motifs_de_l_agent(agent_b.id, organization_id=org_a.id) == []


# --- É8 : la liste de tous les clients ----------------------------------------------------------------------------------------------


async def test_la_liste_de_tous_les_clients_rend_les_memes_colonnes_filtre_et_recherche(db_session, async_session, monde):
    (org_a, agent_a), (org_b, agent_b) = monde
    await _run(
        async_session, agent_a, fiche={"motif": "Devis", "mapped_call_disposition": "RDV_pris"}, note=2.0, duree=75,
        annotations={"mark_apres_appel": {"synthese": SYNTHESE}, "juge": {"etat": "juge", "source": "claude_code", "par": "Léa"}},
    )
    await _run(async_session, agent_b, fiche={"motif": "Dépannage"})
    toutes = [org_a.id, org_b.id]
    lignes, total = await db_session.lister_conversations_des_organisations(organisations=toutes, limit=25, offset=0)
    assert total == 2
    devis = next(r for r in lignes if r["motif"] == "Devis")
    assert devis["issue"] == "RDV_pris" and devis["duree"] == 75 and devis["note_juge"] == 2.0
    assert devis["juge_par"] == "Claude Code · Léa" and devis["resume_source"] == "synthese"
    assert devis["workflow_name"] == "Agent a" and devis["organization_id"] == org_a.id
    filtrees, total_filtre = await db_session.lister_conversations_des_organisations(organisations=toutes, limit=25, offset=0, motif="DÉPANNAGE")
    assert total_filtre == 1 and filtrees[0]["motif"] == "Dépannage"
    _, par_texte = await db_session.lister_conversations_des_organisations(organisations=toutes, limit=25, offset=0, recherche="chaudière")
    assert par_texte == 1
    _, par_agent = await db_session.lister_conversations_des_organisations(organisations=toutes, limit=25, offset=0, recherche="Agent b")
    assert par_agent == 1  # le nom de l'agent se cherche aussi (la maquette)


async def test_la_liste_de_tous_les_clients_ne_lit_que_les_organisations_ouvertes(db_session, async_session, monde):
    (org_a, agent_a), (org_b, agent_b) = monde
    await _run(async_session, agent_a, fiche={"motif": "Devis"})
    await _run(async_session, agent_b, fiche={"motif": "Devis"})
    _, seul = await db_session.lister_conversations_des_organisations(organisations=[org_a.id], limit=25, offset=0, motif="Devis")
    assert seul == 1
    assert await db_session.lister_motifs_des_organisations([org_a.id]) == ["Devis"]
    assert await db_session.lister_motifs_des_organisations([org_b.id, org_a.id]) == ["Devis"]  # réunis entre clients
    assert await db_session.lister_motifs_des_organisations([]) == []
    # Pagination : une page, le total reste celui du filtre.
    page, total = await db_session.lister_conversations_des_organisations(organisations=[org_a.id, org_b.id], limit=1, offset=0, motif="Devis")
    assert len(page) == 1 and total == 2


def test_juge_par_dit_la_personne_derriere_claude_code_quand_elle_est_connue():
    assert juge_par({"juge": {"etat": "juge", "source": "claude_code", "par": "Léa"}}) == "Claude Code · Léa"
    assert juge_par({"juge": {"etat": "juge", "source": "claude_code"}}) == "Claude Code"
    assert juge_par({"juge": {"etat": "juge", "source": "cle_api", "modele": "openai/gpt-x", "par": "Léa"}}) == "openai/gpt-x"
