"""[.mark] Partie 3, N3b, sous-lot 1 : le motif devient un filtre EXACT (liste des appels et statistiques) et chaque appel a un résumé.

Ce qui doit tenir : « Devis » ne prend plus « Devis urgent » (casse et espaces mis à part) ; le filtre ne lit que l'organisation de
l'appelant ; les statistiques d'UN motif ne comptent que ses appels ; le résumé réutilise la synthèse de l'après-appel (deux phrases
au plus) et passe avant celui du modèle ; le résumé par un modèle est ÉTEINT par défaut, jamais pour un appel d'essai ni pour un
appel qui a déjà sa synthèse, compté dans la dépense du mois des rôles (rôle « resume »), refusé quand le budget est atteint, et
rejouable sans effet double. Cerveaux factices : aucun appel réel.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from api.db import db_client
from api.db.models import OrganizationModel, UserModel, WorkflowRunModel
from api.schemas.appel_simule import ReglagesAppelantSimule, RoleSimule
from api.services import resume_appel
from api.services.boucle import qualite
from api.services.builder.cerveau import budget_roles, simules
from api.services.builder.cerveau import reglages as reglages_cerveau
from api.services.builder.cerveau.factice import CerveauFactice, texte, tour
from api.services.builder.cerveau.reglages import ReglagesCerveau
from api.services.resume_appel import generation
from api.tests.mark.equipe_commun import creer_organisation

GRAPHE = {"nodes": [{"id": "1", "type": "startCall", "data": {"name": "Start", "prompt": "Hello"}}], "edges": []}
SYNTHESE = "La personne voulait un devis pour une chaudière. L'assistant a pris ses coordonnées. Un rappel a été promis demain. Rien d'autre."


# --- le résumé : lecture pure ------------------------------------------------------------------------------------------


def test_le_resume_garde_deux_phrases_et_ne_coupe_pas_sur_une_abreviation():
    assert resume_appel.resume_court(SYNTHESE) == "La personne voulait un devis pour une chaudière. L'assistant a pris ses coordonnées."
    assert resume_appel.resume_court("M. Dupont voulait un devis. Il a rappelé.") == "M. Dupont voulait un devis. Il a rappelé."
    assert resume_appel.resume_court("   ") is None and resume_appel.resume_court(None) is None


def test_un_resume_trop_long_est_coupe_au_mot_avec_des_points_de_suspension():
    long = "mot " * 200
    court = resume_appel.resume_court(long)
    assert court.endswith("…") and len(court) <= resume_appel.CARACTERES_MAX + 1 and " …" not in court


def test_la_synthese_de_l_apres_appel_passe_avant_le_resume_du_modele():
    annotations = {"mark_apres_appel": {"synthese": SYNTHESE}, "resume_appel": {"texte": "Résumé du modèle."}}
    assert resume_appel.lire(annotations) == {"texte": resume_appel.resume_court(SYNTHESE), "source": "synthese"}
    assert resume_appel.lire({"resume_appel": {"texte": "Résumé du modèle."}}) == {"texte": "Résumé du modèle.", "source": "modele"}
    assert resume_appel.lire({}) is None and resume_appel.lire(None) is None and resume_appel.lire({"mark_apres_appel": "x"}) is None


# --- la base : filtre exact du motif, résumé dans la liste ---------------------------------------------------------------


async def _monde(async_session, db_session, nom):
    org = OrganizationModel(provider_id=f"org-n3b-{nom}-{uuid.uuid4().hex[:6]}")
    async_session.add(org)
    await async_session.flush()
    user = UserModel(provider_id=f"user-n3b-{nom}-{uuid.uuid4().hex[:6]}", selected_organization_id=org.id)
    async_session.add(user)
    await async_session.flush()
    agent = await db_session.create_workflow(name=f"Agent {nom}", workflow_definition=GRAPHE, user_id=user.id, organization_id=org.id)
    return org, agent


async def _run(async_session, agent, *, fiche=None, annotations=None, jours=1):
    run = WorkflowRunModel(
        name="run",
        workflow_id=agent.id,
        mode="twilio",
        created_at=datetime.now(UTC) - timedelta(days=jours),
        usage_info={"call_duration_seconds": 30},
        initial_context={"caller_number": "+33611111111"},
        gathered_context=fiche or {},
        logs={"realtime_feedback_events": []},
        annotations=annotations or {},
    )
    async_session.add(run)
    await async_session.flush()
    return run


def _f(valeur):
    return {"attribute": "callReason", "type": "text", "value": {"value": valeur}}


@pytest.fixture
async def monde(db_session, async_session):
    a = await _monde(async_session, db_session, "a")
    b = await _monde(async_session, db_session, "b")
    return a, b


async def _liste(db_session, org, **options):
    runs, total, _, _ = await db_session.get_usage_history(org.id, **options)
    return runs, total


async def test_le_filtre_du_motif_est_exact_sans_tenir_compte_de_la_casse_ni_des_espaces(db_session, async_session, monde):
    (org_a, agent_a), _ = monde
    await _run(async_session, agent_a, fiche={"motif": "Devis"})
    await _run(async_session, agent_a, fiche={"motif_appel": "  devis  "})
    await _run(async_session, agent_a, fiche={"motif": "Devis urgent"})
    await _run(async_session, agent_a, fiche={"motif": "Prise  de rendez-vous"})
    assert (await _liste(db_session, org_a, filters=[_f("Devis")]))[1] == 2  # plus « Devis urgent »
    assert (await _liste(db_session, org_a, filters=[_f("DEVIS")]))[1] == 2
    assert (await _liste(db_session, org_a, filters=[_f("dev")]))[1] == 0  # un morceau ne suffit plus
    assert (await _liste(db_session, org_a, filters=[_f("Prise de rendez-vous")]))[1] == 1  # espaces repliés comme le bilan de la boucle
    assert (await _liste(db_session, org_a, filters=[_f("%")]))[1] == 0  # les jokers sont du texte


async def test_le_filtre_du_motif_ne_lit_que_l_organisation_de_l_appelant(db_session, async_session, monde):
    (org_a, agent_a), (org_b, agent_b) = monde
    await _run(async_session, agent_b, fiche={"motif": "Devis"})
    assert (await _liste(db_session, org_a, filters=[_f("Devis")]))[1] == 0
    assert (await _liste(db_session, org_b, filters=[_f("Devis")]))[1] == 1


async def test_la_liste_rend_le_resume_de_la_synthese_sinon_celui_du_modele_sinon_rien(db_session, async_session, monde):
    (org_a, agent_a), _ = monde
    await _run(async_session, agent_a, fiche={"motif": "A"}, annotations={"mark_apres_appel": {"synthese": SYNTHESE}})
    await _run(async_session, agent_a, fiche={"motif": "B"}, annotations={"resume_appel": {"texte": "Un rappel demandé."}})
    await _run(async_session, agent_a, fiche={"motif": "C"})
    lignes, _ = await _liste(db_session, org_a)
    par_motif = {r["motif"]: r for r in lignes}
    assert par_motif["A"]["resume"] == "La personne voulait un devis pour une chaudière. L'assistant a pris ses coordonnées."
    assert par_motif["A"]["resume_source"] == "synthese"
    assert par_motif["B"]["resume"] == "Un rappel demandé." and par_motif["B"]["resume_source"] == "modele"
    assert par_motif["C"]["resume"] is None and par_motif["C"]["resume_source"] is None


async def test_les_statistiques_d_un_motif_ne_comptent_que_ses_appels_et_son_organisation(db_session, async_session, monde):
    (org_a, agent_a), (org_b, agent_b) = monde

    def bilan(motif, issue=True):
        return {"boucle": {"indicateurs": {"motif": motif, "issue_obtenue": issue}}}

    await _run(async_session, agent_a, annotations=bilan("Devis"))
    await _run(async_session, agent_a, annotations=bilan("devis", issue=False))
    await _run(async_session, agent_a, annotations=bilan("Dépannage"))
    await _run(async_session, agent_b, annotations=bilan("Devis"))
    tout = await qualite.calculer(org_a.id, jours=7)
    assert tout["global"]["appels"] == 3 and tout["motif"] is None
    un = await qualite.calculer(org_a.id, jours=7, motif="Devis")
    assert un["global"]["appels"] == 2 and un["motif"] == "Devis" and [m["motif"] for m in un["motifs"]] == ["Devis", "devis"]
    assert (await qualite.calculer(org_b.id, jours=7, motif="Dépannage"))["global"]["appels"] == 0  # cloisonné
    assert (await qualite.calculer(org_a.id, jours=7, motif="Dép"))["global"]["appels"] == 0  # exact, pas un morceau


# --- le résumé par un modèle : éteint par défaut, budget, idempotent ------------------------------------------------------

LIGNES = [
    {"type": "rtf-bot-text", "payload": {"text": "Bonjour, que puis-je faire pour vous ?"}, "timestamp": "2026-11-03T10:00:00+00:00", "turn": 0},
    {"type": "rtf-user-transcription", "payload": {"text": "Je voudrais un devis.", "final": True}, "timestamp": "2026-11-03T10:00:02+00:00", "turn": 1},
]
PRIX = (10.0, 10.0)  # un tour factice (100 + 50 jetons) = 0,0015 $


def _run_factice(identifiant=7, **champs):
    base = dict(id=identifiant, workflow_id=1, logs={"realtime_feedback_events": LIGNES}, gathered_context={}, annotations={}, definition=None)
    return SimpleNamespace(**{**base, **champs})


@pytest.fixture(autouse=True)
def _dans_une_transaction_annulee(db_session):
    yield


@pytest.fixture
async def organisation():
    return await creer_organisation(db_client, f"org-resume-{uuid.uuid4().hex[:8]}")


@pytest.fixture
def banc(monkeypatch):
    ecrits: list[tuple[int, dict]] = []
    monkeypatch.setattr(
        generation.db_client, "update_workflow_run", AsyncMock(side_effect=lambda run_id, annotations=None, **_: ecrits.append((run_id, annotations)))
    )
    monkeypatch.setattr(reglages_cerveau, "lire", AsyncMock(return_value=ReglagesCerveau(modele="builder-m")))
    return ecrits


def _roles(monkeypatch, **champs):
    from api.services.appel_simule import reglages as appel_simule

    roles = ReglagesAppelantSimule(resume=RoleSimule(consigne="Résume.", modele="openai/resume-m", identifiant="k", **champs))
    monkeypatch.setattr(appel_simule, "lire_reglages", AsyncMock(return_value=roles))


def _cerveau(monkeypatch, *tours):
    factice = CerveauFactice(*tours)
    monkeypatch.setattr("api.services.appel_simule.serie.cle_d_identifiant", AsyncMock(return_value="cle-factice"))
    monkeypatch.setattr(simules, "fabriquer", lambda reglages, cle: factice)
    monkeypatch.setattr(simules, "prix_du_role", AsyncMock(return_value=PRIX))
    return factice


async def test_le_resume_par_un_modele_est_eteint_par_defaut(banc, monkeypatch, organisation):
    assert ReglagesAppelantSimule().resume.actif is False  # le réglage tel qu'il naît
    _roles(monkeypatch)  # une clé et un modèle posés, mais l'interrupteur reste éteint
    factice = _cerveau(monkeypatch, tour(texte("Ne doit jamais être lu.")))
    assert await generation.apres_appel(_run_factice(), organisation) is None
    assert banc == [] and factice.requetes == []  # aucun appel au fournisseur


async def test_allume_le_resume_est_ecrit_et_sa_depense_entre_dans_celle_du_mois(banc, monkeypatch, organisation):
    _roles(monkeypatch, actif=True, budget_mois=100.0)
    factice = _cerveau(monkeypatch, tour(texte("La personne voulait un devis. Un rappel a été promis. Une troisième phrase de trop.")))
    rendu = await generation.apres_appel(_run_factice(), organisation)
    assert rendu == "La personne voulait un devis. Un rappel a été promis."
    ((run_id, annotations),) = banc
    assert run_id == 7 and annotations["resume_appel"]["texte"] == rendu and annotations["resume_appel"]["modele"] == "openai/resume-m"
    assert annotations["resume_appel"]["jetons"] == 150 and annotations["resume_appel"]["cout"] == pytest.approx(0.0015)
    mois = await budget_roles.depense_du_mois(organisation)
    assert mois["resume"]["jetons"] == 150 and mois["resume"]["cout"] == pytest.approx(0.0015)
    assert mois["juge"]["jetons"] == 0 and mois["appelant"]["jetons"] == 0  # un seul compteur, chaque rôle le sien
    assert "Je voudrais un devis." in factice.requetes[0]["messages"][0]["content"]


async def test_un_resume_deja_ecrit_n_est_jamais_refait(banc, monkeypatch, organisation):
    _roles(monkeypatch, actif=True)
    factice = _cerveau(monkeypatch, tour(texte("Autre texte.")))
    run = _run_factice(annotations={"resume_appel": {"texte": "Déjà là."}})
    assert await generation.apres_appel(run, organisation) is None
    assert banc == [] and factice.requetes == []


async def test_un_appel_qui_a_sa_synthese_ou_dont_l_agent_la_fait_n_est_pas_resume(banc, monkeypatch, organisation):
    _roles(monkeypatch, actif=True)
    factice = _cerveau(monkeypatch, tour(texte("Jamais lu.")))
    assert await generation.apres_appel(_run_factice(annotations={"mark_apres_appel": {"synthese": SYNTHESE}}), organisation) is None
    definition = SimpleNamespace(workflow_configurations={"apres_appel": {"actif": True, "synthese": True}})
    assert generation._agent_fait_sa_synthese(SimpleNamespace(definition=definition)) is True
    assert generation._agent_fait_sa_synthese(SimpleNamespace(definition=None)) is False  # après-appel éteint : pas de synthèse à attendre
    assert await generation.apres_appel(_run_factice(definition=definition), organisation) is None
    assert banc == [] and factice.requetes == []


async def test_un_appel_d_essai_n_est_jamais_resume(banc, monkeypatch, organisation):
    _roles(monkeypatch, actif=True)
    factice = _cerveau(monkeypatch, tour(texte("Jamais lu.")))
    assert await generation.apres_appel(_run_factice(annotations={"tester": True}), organisation) is None
    assert banc == [] and factice.requetes == []


async def test_un_budget_atteint_refuse_avant_le_fournisseur(banc, monkeypatch, organisation):
    _roles(monkeypatch, actif=True, budget_mois=0.001)
    await budget_roles.enregistrer(organisation, "resume", entree=100, sortie=50, prix_entree=10.0, prix_sortie=10.0)  # 0,0015 : atteint
    factice = _cerveau(monkeypatch, tour(texte("Jamais lu.")))
    assert await generation.apres_appel(_run_factice(), organisation) is None
    assert banc == [] and factice.requetes == []


async def test_un_resume_en_panne_n_abime_pas_l_apres_appel(banc, monkeypatch, organisation):
    _roles(monkeypatch, actif=True)
    monkeypatch.setattr(simules, "cerveau_du_role", AsyncMock(side_effect=RuntimeError("panne")))
    assert await generation.apres_appel(_run_factice(), organisation) is None
    assert banc == []
