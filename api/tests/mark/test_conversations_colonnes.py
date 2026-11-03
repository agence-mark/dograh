"""[.mark] Lot C4 : les colonnes de Conversations (Client, Motif, Note du juge, Version, Canal), leurs filtres et tris, la recherche
dans les transcriptions.

Ce qui doit tenir : la note du juge est une part des critères vérifiés, sur 5 (aucun critère vérifié = pas de note) ; elle est écrite
par la fonction commune aux deux portes du juge et rejuger la remplace ; la liste rend client, motif, note, version et canal dans la
MÊME requête ; chaque filtre et chaque tri ne lit que l'organisation de l'appelant ; la recherche est bornée (3 lettres, période,
nombre d'appels), cloisonnée, et traite les jokers comme du texte.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import select

from api.db.models import OrganizationModel, UserModel, WorkflowDefinitionModel, WorkflowRunModel
from api.services.juge import appels, note

GRAPHE = {"nodes": [{"id": "1", "type": "startCall", "data": {"name": "Start", "prompt": "Hello"}}], "edges": []}


def _v(verdict):
    return {"critere": "c", "verdict": verdict}


# --- la note ---------------------------------------------------------------------------------------------------------


def test_la_note_est_la_part_des_criteres_verifies_sur_5():
    assert note.calculer([_v("reussi")] * 3 + [_v("rate")]) == 3.8
    assert note.calculer([_v("reussi")] * 2) == 5.0
    assert note.calculer([_v("rate")] * 2) == 0.0


def test_un_critere_non_verifiable_sort_du_calcul_et_sans_critere_verifie_pas_de_note():
    assert note.calculer([_v("reussi"), _v("non_verifiable")]) == 5.0
    assert note.calculer([_v("non_verifiable")]) is None
    assert note.calculer([]) is None and note.calculer(None) is None


def test_seul_l_etat_juge_porte_une_note():
    assert note.de_un_resultat({"etat": "a_juger", "verdicts": [_v("reussi")]}) is None
    assert note.de_un_resultat({"etat": "juge", "verdicts": [_v("reussi"), _v("rate")]}) == 2.5


# --- la base ---------------------------------------------------------------------------------------------------------


async def _monde(async_session, db_session, nom):
    org = OrganizationModel(provider_id=f"org-c4-{nom}")
    async_session.add(org)
    await async_session.flush()
    user = UserModel(provider_id=f"user-c4-{nom}", selected_organization_id=org.id)
    async_session.add(user)
    await async_session.flush()
    agent = await db_session.create_workflow(name=f"Agent {nom}", workflow_definition=GRAPHE, user_id=user.id, organization_id=org.id)
    return org, agent


async def _run(async_session, agent, *, jours=1, mode="twilio", fiche=None, note_juge=None, journal=None, annotations=None, definition_id=None):
    run = WorkflowRunModel(
        name="run",
        workflow_id=agent.id,
        mode=mode,
        created_at=datetime.now(UTC) - timedelta(days=jours),
        usage_info={"call_duration_seconds": 30},
        initial_context={"caller_number": "+33611111111"},
        gathered_context=fiche or {},
        logs={"realtime_feedback_events": journal or []},
        annotations=annotations or {},
        note_juge=note_juge,
        definition_id=definition_id,
    )
    async_session.add(run)
    await async_session.flush()
    return run


def _replique(texte, genre="rtf-user-transcription"):
    return {"type": genre, "payload": {"text": texte, "final": True}, "timestamp": "2026-11-04T10:00:00+00:00", "turn": 0}


@pytest.fixture
async def monde(db_session, async_session):
    org_a, agent_a = await _monde(async_session, db_session, "a")
    org_b, agent_b = await _monde(async_session, db_session, "b")
    return org_a, agent_a, org_b, agent_b


async def _liste(db_session, org, **options):
    runs, total, _, _ = await db_session.get_usage_history(org.id, **options)
    return runs, total


def _f(attribut, genre, valeur):
    return {"attribute": attribut, "type": genre, "value": valeur}


async def _definition(async_session, agent):
    return (
        await async_session.execute(select(WorkflowDefinitionModel).where(WorkflowDefinitionModel.workflow_id == agent.id))
    ).scalars().first()


async def test_la_liste_rend_client_motif_note_version_et_canal_d_une_seule_requete(db_session, async_session, monde):
    org_a, agent_a, _, _ = monde
    definition = await _definition(async_session, agent_a)
    await _run(
        async_session, agent_a, fiche={"prenom": "Claire", "nom": "Dupont", "motif_appel": "Devis"}, note_juge=4.2, definition_id=definition.id
    )
    runs, total = await _liste(db_session, org_a)
    (r,) = runs
    assert total == 1 and r["client"] == "Claire Dupont" and r["motif"] == "Devis" and r["note_juge"] == 4.2
    assert r["canal"] == "telephony" and r["version"] == definition.version_number


async def test_le_canal_site_vient_de_la_marque_du_widget_pas_du_mode(db_session, async_session, monde):
    org_a, agent_a, _, _ = monde
    await _run(async_session, agent_a, mode="smallwebrtc", annotations={"embed": {"source": "embed_widget"}})
    await _run(async_session, agent_a, mode="smallwebrtc")
    runs, _ = await _liste(db_session, org_a)
    assert sorted(r["canal"] for r in runs) == ["site", "web"]
    site, total = await _liste(db_session, org_a, filters=[_f("callChannel", "radio", {"status": "site"})])
    assert total == 1 and site[0]["canal"] == "site"


async def test_filtres_par_note_motif_client_et_tri_par_note(db_session, async_session, monde):
    org_a, agent_a, _, _ = monde
    await _run(async_session, agent_a, fiche={"nom": "Martin", "motif": "Urgence"}, note_juge=2.0)
    await _run(async_session, agent_a, fiche={"nom": "Durand", "motif": "Devis"}, note_juge=4.5)
    await _run(async_session, agent_a, fiche={"nom": "Petit", "motif": "Devis"})  # pas jugé
    _, bas = await _liste(db_session, org_a, filters=[_f("judgeNote", "numberRange", {"max": 3.5})])
    assert bas == 1  # l'appel non jugé ne ressemble jamais à un mauvais appel
    _, n = await _liste(db_session, org_a, filters=[_f("callReason", "text", {"value": "dev"})])
    assert n == 2
    _, n = await _liste(db_session, org_a, filters=[_f("callClient", "text", {"value": "mart"})])
    assert n == 1
    _, n = await _liste(db_session, org_a, filters=[_f("callClient", "text", {"value": "+3361111"})])
    assert n == 3  # le numéro compte aussi quand la fiche n'a pas de nom
    asc, _ = await _liste(db_session, org_a, sort_by="judge_note", sort_order="asc")
    assert [r["note_juge"] for r in asc] == [2.0, 4.5, None]
    desc, _ = await _liste(db_session, org_a, sort_by="judge_note", sort_order="desc")
    assert [r["note_juge"] for r in desc] == [4.5, 2.0, None]


async def test_les_filtres_ne_lisent_que_l_organisation_de_l_appelant(db_session, async_session, monde):
    org_a, agent_a, org_b, agent_b = monde
    await _run(async_session, agent_b, fiche={"nom": "Autre", "motif": "Devis"}, note_juge=1.0)
    for filtre in (
        _f("judgeNote", "numberRange", {"max": 5}),
        _f("callReason", "text", {"value": "dev"}),
        _f("callClient", "text", {"value": "autre"}),
    ):
        assert (await _liste(db_session, org_a, filters=[filtre]))[1] == 0
        assert (await _liste(db_session, org_b, filters=[filtre]))[1] == 1


async def test_un_motif_avec_des_jokers_est_du_texte(db_session, async_session, monde):
    org_a, agent_a, _, _ = monde
    await _run(async_session, agent_a, fiche={"motif": "Devis"})
    _, n = await _liste(db_session, org_a, filters=[_f("callReason", "text", {"value": "%"})])
    assert n == 0


async def test_la_version_jouee_se_filtre_et_se_trie(db_session, async_session, monde):
    org_a, agent_a, _, _ = monde
    definition = await _definition(async_session, agent_a)
    await _run(async_session, agent_a, definition_id=definition.id)
    await _run(async_session, agent_a)
    numero = definition.version_number
    runs, n = await _liste(db_session, org_a, filters=[_f("agentVersion", "number", {"value": numero})])
    assert n == 1 and runs[0]["version"] == numero
    _, n = await _liste(db_session, org_a, filters=[_f("agentVersion", "number", {"value": 999})])
    assert n == 0
    tri, _ = await _liste(db_session, org_a, sort_by="version", sort_order="desc")
    assert tri[0]["version"] == numero and tri[1]["version"] is None


async def test_ecrire_la_note_remplace_et_peut_effacer(db_session, async_session, monde):
    org_a, agent_a, _, _ = monde
    run = await _run(async_session, agent_a)
    await appels.ecrire_dans_le_run(run.id, {"etat": "juge", "verdicts": [_v("reussi"), _v("rate")]})
    assert (await db_session.get_workflow_run_by_id(run.id)).note_juge == 2.5
    await appels.ecrire_dans_le_run(run.id, {"etat": "juge", "verdicts": [_v("reussi")]})  # rejuger remplace
    assert (await db_session.get_workflow_run_by_id(run.id)).note_juge == 5.0
    await appels.ecrire_dans_le_run(run.id, {"etat": "a_juger"})
    relu = await db_session.get_workflow_run_by_id(run.id)
    assert relu.note_juge is None and relu.annotations["juge"]["etat"] == "a_juger"


# --- la recherche dans les transcriptions ----------------------------------------------------------------------------


async def test_la_recherche_trouve_une_replique_de_l_un_ou_l_autre_sans_tenir_compte_de_la_casse(db_session, async_session, monde):
    org_a, agent_a, _, _ = monde
    await _run(async_session, agent_a, journal=[_replique("Je veux un RENDEZ-VOUS demain")])
    await _run(async_session, agent_a, journal=[_replique("Bonjour, un rendez-vous ?", "rtf-bot-text")])
    await _run(async_session, agent_a, journal=[_replique("Au revoir")])
    runs, n = await _liste(db_session, org_a, recherche="rendez-vous")
    assert n == 2 and len(runs) == 2


async def test_la_recherche_est_cloisonnee_par_organisation(db_session, async_session, monde):
    org_a, agent_a, org_b, agent_b = monde
    await _run(async_session, agent_b, journal=[_replique("Un secret de l'autre client")])
    assert (await _liste(db_session, org_a, recherche="secret"))[1] == 0
    assert (await _liste(db_session, org_b, recherche="secret"))[1] == 1


async def test_la_recherche_est_bornee_trois_lettres_periode_et_jokers_en_texte(db_session, async_session, monde):
    org_a, agent_a, _, _ = monde
    await _run(async_session, agent_a, journal=[_replique("Je veux un devis")])
    await _run(async_session, agent_a, jours=45, journal=[_replique("Un vieux devis")])
    # moins de 3 lettres : pas de recherche (toute la liste), jamais un balayage
    assert (await _liste(db_session, org_a, recherche="de"))[1] == 2
    # sans date de début : 30 jours seulement
    assert (await _liste(db_session, org_a, recherche="devis"))[1] == 1
    # avec une date de début plus ancienne, la période s'élargit
    assert (await _liste(db_session, org_a, recherche="devis", start_date=datetime.now(UTC) - timedelta(days=90)))[1] == 2
    # « % » et « _ » sont du texte
    assert (await _liste(db_session, org_a, recherche="%%%"))[1] == 0
    assert (await _liste(db_session, org_a, recherche="d_vis"))[1] == 0


async def test_un_journal_mal_forme_ne_fait_pas_tomber_la_recherche(db_session, async_session, monde):
    org_a, agent_a, _, _ = monde
    run = await _run(async_session, agent_a)
    run.logs = {"realtime_feedback_events": "pas une liste"}
    await async_session.flush()
    assert (await _liste(db_session, org_a, recherche="devis"))[1] == 0
