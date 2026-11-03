"""[.mark] Builder partie 2, U8 (lot G1) : la boucle (« À améliorer »), les indicateurs, la version estampillée, la page Qualité, le corrigé des tests.

Vraie application, vraie base de test, cerveaux factices : aucun appel à un fournisseur, aucune dépense.

| Test | Ce qu'il prouve |
|---|---|
| indicateurs | l'issue par outil, le transfert, les coupures, la latence médiane, les redemandes et le motif se calculent depuis le journal |
| corrigé | l'état final se compile en critères jugés par le code ; « rien d'autre » refuse un outil non prévu ; plus de deux comportements refusés |
| regroupement | deux appels au même critère font UN problème compté deux fois ; un même appel n'est jamais compté deux fois |
| gravité et fréquence | la gravité monte d'un cran à partir d'un appel sur cinq ; « N appels sur M » lit les appels jugés |
| avancement | suite verte : « Testée » ; publication : « Publiée » ; un nouveau cas rouvre un problème réglé |
| cloisonnement | un problème d'une autre organisation est un 404 ; « Testée » et « Publiée » ne se posent pas à la main |
| bilan de l'appel | version, indicateurs et motif sont rangés dans l'appel ; un appel d'essai n'entre jamais |
| juge | un critère raté entre avec sa réplique fautive et le rang de l'appelant ; un réussi n'entre pas |
| relecture | un test réussi que le juge dit mal joué entre « à revoir » ; sans avis, rien n'est inventé |
| qualité | les chiffres, les motifs, les agents et la comparaison des versions viennent des appels |
"""

from __future__ import annotations

import json
import uuid
from datetime import UTC, datetime, timedelta

import pytest

from api.db import db_client
from api.services.boucle import avancement, indicateurs, ingestion, qualite, vues
from api.services.builder.cerveau.factice import CerveauFactice, texte, tour
from api.services.builder.tests_agent import corrige as etat_final
from api.services.builder.tests_agent import creation, juge as juge_des_tests, verdict
from api.services.tests_rejouables.modele import ErreurTestRejouable
from api.tests.mark.builder_commun import graphe_depart
from api.tests.mark.equipe_commun import (  # noqa: F401
    client_http,
    creer_compte,
    creer_organisation,
    entetes,
    sans_preparation_des_organisations,
)

A = "/api/v1/ameliorations"


def ev(genre, instant, payload=None, turn=0):
    return {"type": f"rtf-{genre}", "timestamp": f"2026-11-03T10:00:{instant:02d}", "turn": turn, "payload": payload or {}}


JOURNAL = [
    ev("bot-text", 1, {"text": "Bonjour, que puis-je faire pour vous ?"}, 1),
    ev("bot-started-speaking", 2),
    ev("user-transcription", 3, {"text": "je voudrais un rendez-vous", "final": True}, 1),  # coupure : l'agent parle encore
    ev("bot-stopped-speaking", 4),
    ev("function-call-start", 5, {"function_name": "reserver", "arguments": {}}),
    ev("function-call-end", 6, {"function_name": "reserver", "result": "ok"}),
    ev("latency-measured", 7, {"latency_seconds": 1.0}),
    ev("latency-measured", 8, {"latency_seconds": 3.0}),
    ev("latency-measured", 9, {"latency_seconds": 2.0}),
]


# --- les indicateurs (C) -----------------------------------------------------------------------------------------------------


def test_les_indicateurs_se_calculent_depuis_le_journal():
    i = indicateurs.calculer(JOURNAL, {"call_disposition": "end_call", "motif_appel": " Prise de rendez-vous "}, duree=62.34, cout=0.123456)
    assert i["issue_obtenue"] is True and i["outils"] == 1 and i["outils_en_echec"] == 0
    assert i["coupures"] == 1 and i["latence_mediane"] == 2.0 and i["latence_max"] == 3.0
    assert i["motif"] == "Prise de rendez-vous" and i["duree"] == 62.3 and i["cout"] == 0.1235
    assert i["transfert"] is False and i["raccroche_avant_la_fin"] is False


def test_un_outil_en_echec_n_est_pas_une_issue_et_le_raccroche_se_voit():
    journal = [ev("function-call-end", 1, {"function_name": "reserver", "result": "Error: agenda indisponible"})]
    i = indicateurs.calculer(journal, {"call_disposition": "user_hangup"})
    assert i["outils_en_echec"] == 1 and i["issue_obtenue"] is False and i["raccroche_avant_la_fin"] is True


def test_un_transfert_est_une_issue():
    i = indicateurs.calculer([], {"call_disposition": "transfer_call"})
    assert i["transfert"] is True and i["issue_obtenue"] is True


def test_un_journal_illisible_ne_leve_jamais():
    assert indicateurs.calculer([{"type": 3}], {"call_disposition": 4}) is not None
    assert indicateurs.calculer(None, None)["issue_obtenue"] is False


# --- le corrigé et les critères (F) ------------------------------------------------------------------------------------------


CORRIGE = {"issue": "rdv_pris", "actions": ["reserver"], "champs": {"nom": "Durand"}, "rien_d_autre": True}


def test_le_corrige_se_compile_en_criteres():
    propre = etat_final.valider(CORRIGE)
    types = [c["type"] for c in etat_final.en_criteres(propre)]
    assert types == ["issue", "outil", "champs_justes", "rien_d_autre"]
    assert etat_final.en_criteres(propre)[-1]["permis"] == ["reserver"]


def test_un_corrige_vide_ou_mal_forme_est_refuse():
    for mauvais in ({}, {"issue": None, "actions": [], "champs": {}}, "x", {"champs": ["a"]}):
        with pytest.raises(ErreurTestRejouable):
            etat_final.valider(mauvais)


def test_plus_de_deux_comportements_sont_refuses():
    assert etat_final.comportements_valides(["se corrige", "hésite"]) == ["se corrige", "hésite"]
    with pytest.raises(ErreurTestRejouable, match="one or two"):
        etat_final.comportements_valides(["a", "b", "c"])


def obs(outils, fiche=None):
    return verdict.ObservationConversation(texte="", outils=outils, lignes=[("agent", "ok")], fiche=fiche or {})


def test_rien_d_autre_refuse_un_outil_non_prevu_et_reconnait_les_champs_justes():
    critere = verdict.valider_criteres([{"type": "rien_d_autre", "permis": ["reserver"]}])[0]
    assert verdict.evaluer_un(critere, obs([{"nom": "reserver", "rang": 0}])).reussi is True
    rate = verdict.evaluer_un(critere, obs([{"nom": "reserver", "rang": 0}, {"nom": "annuler", "rang": 1}]))
    assert rate.reussi is False and rate.rang == 1 and "annuler" in rate.raison
    champs = verdict.valider_criteres([{"type": "champs_justes", "champs": {"nom": "Durand"}}])[0]
    assert verdict.evaluer_un(champs, obs([], {"nom": "durand"})).reussi is True
    assert verdict.evaluer_un(champs, obs([], {"nom": "Dupont"})).reussi is False
    assert verdict.evaluer_un(champs, obs([], {})).reussi is False


async def test_un_test_cree_avec_un_corrige_porte_ses_criteres_et_sa_construction():
    async with client_http() as c:  # noqa: F841 -- la base de test et l'application
        org, user, _, agent = await decor("corrige")
        test = await creation.creer(
            org, agent.id, nom="Prise de rendez-vous", criteres=[], scenario="L'appelant veut un rendez-vous", personnage="presse",
            corrige=CORRIGE, comportements=["se corrige"],
        )
        assert [c["type"] for c in test["criteres"]] == ["issue", "outil", "champs_justes", "rien_d_autre"]
        resume = creation.en_resume(test)
        assert resume["corrige"]["actions"] == ["reserver"] and resume["construction"] == {"applicable": True, "conforme": True, "manque": []}
        modifie = await creation.modifier(org, agent.id, test["slug"], corrige={"actions": ["annuler"], "rien_d_autre": False})
        assert [c["type"] for c in modifie["criteres"]] == ["outil"] and modifie["criteres"][0]["nom"] == "annuler"
        retire = await creation.modifier(org, agent.id, test["slug"], corrige={}, criteres=[{"type": "texte_absent", "texte": "zut"}])
        assert retire["corrige"] is None and [c["type"] for c in retire["criteres"]] == ["texte_absent"]


# --- le rang de l'appelant ----------------------------------------------------------------------------------------------------

LIGNES = [("agent", "Bonjour"), ("moi", "Je veux un rdv"), ("agent", "Quel jour ?"), ("moi", "Mardi"), ("agent", "C'est noté")]


def test_le_rang_de_l_appelant_se_rattache_a_la_derniere_replique_de_l_appelant():
    assert ingestion.rang_de_l_appelant(LIGNES, 3) == 1  # une ligne de l'agent : la réplique de l'appelant d'avant
    assert ingestion.rang_de_l_appelant(LIGNES, 4) == 2
    assert ingestion.rang_de_l_appelant(LIGNES, 1) == 1  # l'agent parle en premier : au moins la première
    assert ingestion.rang_de_l_appelant(LIGNES, 99) is None and ingestion.rang_de_l_appelant(LIGNES, None) is None


# --- le décor en base ---------------------------------------------------------------------------------------------------------


async def decor(nom):
    nom_unique = f"{nom}-{uuid.uuid4().hex[:8]}"  # la base de test garde ses lignes d'une exécution à l'autre
    org = await creer_organisation(db_client, f"org-g1-{nom_unique}")
    user, jeton = await creer_compte(db_client, f"g1{nom_unique}@example.test", role="Administrateur", organisations=[org])
    agent = await db_client.create_workflow(f"Agent {nom}", graphe_depart(), user.id, org)
    return org, user, jeton, agent


async def un_appel(agent, user, org, *, contexte=None, annotations=None, journal=None, usage=None):
    run = await db_client.create_workflow_run("appel", agent.id, "smallwebrtc", user.id, organization_id=org, gathered_context=contexte or {}, logs={"realtime_feedback_events": journal or []})
    await db_client.update_workflow_run(run.id, annotations=annotations or {}, usage_info=usage or {}, gathered_context=contexte or {})
    return await db_client.get_workflow_run(run.id)


def verdict_juge(critere, *, v="rate", replique=2, preuve="Je veux un rdv", confiance=0.9):
    return {"critere": critere, "verdict": v, "replique": replique, "preuve": preuve, "confiance": confiance}


# --- le regroupement et le juge (B) -------------------------------------------------------------------------------------------


async def test_deux_appels_au_meme_critere_font_un_probleme_compte_deux_fois():
    org, user, _, agent = await decor("groupe")
    r1, r2 = await un_appel(agent, user, org), await un_appel(agent, user, org)
    for run in (r1, r2, r1):  # le même appel deux fois n'est jamais compté deux fois
        await ingestion.ingerer_un_appel_juge(run, org, [verdict_juge("Suit le parcours"), verdict_juge("Naturel", v="reussi")], LIGNES)
    lignes, suite = await db_client.lister_les_ameliorations(org)
    assert len(lignes) == 1 and suite is False  # le critère réussi n'entre pas
    p = lignes[0]
    assert p["nb_cas"] == 2 and p["releve_par"] == "juge" and p["etat"] == "a_trier" and p["titre"] == "Suit le parcours"
    assert p["replique"] == "Je veux un rdv" and {c["run_id"] for c in p["cas"]} == {r1.id, r2.id}
    assert all(c["rang"] == 1 for c in p["cas"])  # la réplique 2 de la transcription est la 1re de l'appelant


async def test_un_non_verifiable_entre_en_gravite_faible_un_rate_sur_de_lui_en_grave():
    org, user, _, agent = await decor("gravite")
    run = await un_appel(agent, user, org)
    await ingestion.ingerer_un_appel_juge(
        run, org, [verdict_juge("A", v="non_verifiable", replique=None, preuve="rien à lire"), verdict_juge("B", confiance=0.95), verdict_juge("C", confiance=0.65)], LIGNES
    )
    par_titre = {p["titre"]: p["gravite"] for p in (await db_client.lister_les_ameliorations(org))[0]}
    assert par_titre == {"A": 1, "B": 3, "C": 2}


def test_la_gravite_monte_d_un_cran_a_partir_d_un_appel_sur_cinq():
    p = {"gravite": 1}
    assert vues.gravite_effective(p, {"n": 1, "sur": 10, "genre": "appels"}) == 1
    assert vues.gravite_effective(p, {"n": 2, "sur": 10, "genre": "appels"}) == 2
    assert vues.gravite_effective({"gravite": 3}, {"n": 9, "sur": 10, "genre": "appels"}) == 3  # jamais au-delà de 3
    assert vues.gravite_effective(p, {"n": 1, "sur": 1, "genre": "essais"}) == 1  # un test n'est pas une fréquence d'appels


async def test_la_frequence_lit_les_appels_juges_et_les_traces_du_code_lisent_tous_les_appels():
    org, user, _, agent = await decor("frequence")
    for _ in range(3):
        await un_appel(agent, user, org, annotations={"juge": {"etat": "juge", "verdicts": []}})
    await un_appel(agent, user, org)  # non jugé
    run = await un_appel(agent, user, org)
    await ingestion.ingerer_un_appel_juge(run, org, [verdict_juge("X")], LIGNES)
    page = await vues.liste(org, etat="a_trier", workflow_id=None, page=0)
    assert page["lignes"][0]["frequence"] == {"n": 1, "sur": 3, "genre": "appels"} and page["compteurs"]["a_trier"] == 1


# --- les traces du code (B) ---------------------------------------------------------------------------------------------------


async def test_une_impasse_du_code_entre_avec_sa_cause_et_ses_cas_se_regroupent():
    org, user, _, agent = await decor("code")
    contexte = {"impasse": {"impasses": 1, "etape": "Dépannage", "journal": [{"impasse": 1, "motif": "impasse", "tour": 4}]}}
    for _ in range(2):
        run = await un_appel(agent, user, org, contexte=contexte)
        await ingestion.bilan_de_l_appel(run, org)
    lignes, _ = await db_client.lister_les_ameliorations(org)
    assert len(lignes) == 1
    p = lignes[0]
    assert p["releve_par"] == "code" and p["critere"] == "impasse" and p["etape"] == "Dépannage" and p["gravite"] == 3 and p["cause"] == "moteur" and p["nb_cas"] == 2


# --- le bilan de l'appel (C, D, E) -------------------------------------------------------------------------------------------


async def test_le_bilan_range_la_version_les_indicateurs_et_le_motif_dans_l_appel():
    org, user, _, agent = await decor("bilan")
    run = await un_appel(agent, user, org, journal=JOURNAL, contexte={"call_disposition": "end_call", "motif": "Dépannage"}, usage={"call_duration_seconds": 40})
    bilan = await ingestion.bilan_de_l_appel(run, org)
    relu = await db_client.get_workflow_run(run.id)
    assert relu.annotations["boucle"] == bilan
    assert bilan["version"]["definition_id"] == run.definition_id and "recettes" in bilan["version"]
    assert bilan["indicateurs"]["issue_obtenue"] is True and bilan["indicateurs"]["motif"] == "Dépannage" and bilan["indicateurs"]["duree"] == 40.0


async def test_un_appel_d_essai_n_entre_jamais():
    org, user, _, agent = await decor("essai")
    run = await un_appel(agent, user, org, annotations={"tester": True}, contexte={"impasse": {"impasses": 1, "journal": [{"impasse": 1, "motif": "x", "tour": 1}]}})
    assert await ingestion.bilan_de_l_appel(run, org) is None
    assert (await db_client.lister_les_ameliorations(org))[0] == []


# --- l'avancement ------------------------------------------------------------------------------------------------------------


async def un_probleme(org, agent, user, critere="Suit le parcours"):
    run = await un_appel(agent, user, org)
    await ingestion.ingerer_un_appel_juge(run, org, [verdict_juge(critere)], LIGNES)
    return (await db_client.lister_les_ameliorations(org))[0][0], run


async def test_suite_verte_puis_publication_puis_nouveau_cas_qui_rouvre():
    org, user, _, agent = await decor("avance")
    p, _ = await un_probleme(org, agent, user)
    assert await avancement.apres_une_suite_verte(org, agent.id) == 1
    assert (await db_client.lire_une_amelioration(org, p["id"]))["etat"] == "testee"
    assert await avancement.apres_une_publication(org, agent.id) == 1
    relu = await db_client.lire_une_amelioration(org, p["id"])
    assert relu["etat"] == "publiee" and relu["avancement"]["rejoue"] is True and relu["avancement"]["publie"] is True
    nouveau = await un_appel(agent, user, org)
    await ingestion.ingerer_un_appel_juge(nouveau, org, [verdict_juge("Suit le parcours")], LIGNES)
    rouvert = await db_client.lire_une_amelioration(org, p["id"])
    assert rouvert["etat"] == "a_trier" and rouvert["avancement"] == {} and rouvert["nb_cas"] == 2


async def test_un_test_qui_reussit_de_nouveau_regle_son_probleme_seulement():
    org, user, _, agent = await decor("test-vert")
    test = {"slug": "urgence", "nom": "Urgence", "obligatoire": True}
    assert await ingestion.ingerer_un_test(org, agent.id, test, reussis=1, total=3, raison="mauvaise sortie") is True
    autre, _ = await un_probleme(org, agent, user)
    await ingestion.ingerer_un_test(org, agent.id, test, reussis=3, total=3)
    par_titre = {p["titre"]: p for p in (await db_client.lister_les_ameliorations(org, etat="testee"))[0]}
    assert list(par_titre) == ["Urgence"] and par_titre["Urgence"]["gravite"] == 3
    assert (await db_client.lire_une_amelioration(org, autre["id"]))["etat"] == "a_trier"


async def test_un_test_reussi_a_revoir_entre_avec_sa_raison():
    org, user, _, agent = await decor("revoir")
    test = {"slug": "adresse", "nom": "Correction d'adresse"}
    assert await ingestion.ingerer_un_test(org, agent.id, test, reussis=3, total=3, a_revoir="review", raison="La correction n'a jamais été jouée.") is True
    p = (await db_client.lister_les_ameliorations(org))[0][0]
    assert p["releve_par"] == "test" and p["replique"] == "La correction n'a jamais été jouée." and p["cas"][0]["a_revoir"] is True
    assert vues.frequence(p, {}, {}) == {"n": 3, "sur": 3, "genre": "essais"}
    assert await ingestion.ingerer_un_test(org, agent.id, {"slug": "ok", "nom": "Ok"}, reussis=3, total=3) is False


async def test_la_relecture_dit_a_revoir_sans_inventer_quand_le_juge_n_a_pas_d_avis():
    lignes = [("agent", "Bonjour"), ("moi", "Mon adresse est rue Verte")]
    test = {"nom": "Correction d'adresse", "scenario": {"but": "L'appelant corrige son adresse après la confirmation"}, "comportements": ["se corrige"]}
    non = texte(json.dumps({"ok": False, "confiance": 0.9, "raison": "La correction n'est jamais jouée."}))
    assert await juge_des_tests.relire(CerveauFactice(tour(non)), lignes, test) == {"a_revoir": True, "raison": "La correction n'est jamais jouée.", "serre": False}
    oui = texte(json.dumps({"ok": True, "confiance": 0.9, "raison": "Jouée."}))
    assert (await juge_des_tests.relire(CerveauFactice(tour(oui)), lignes, test))["a_revoir"] is False
    illisible = [tour(texte("???"))] * 3
    assert await juge_des_tests.relire(CerveauFactice(*illisible), lignes, test) is None
    assert "Correction" not in juge_des_tests.question_de_relecture({"nom": "x", "scenario": {"but": "le cas visé"}})


# --- les routes ---------------------------------------------------------------------------------------------------------------


async def test_la_liste_le_detail_et_le_cloisonnement(sans_preparation_des_organisations):
    org, user, jeton, agent = await decor("routes")
    autre_org, autre_user, _, autre_agent = await decor("routes-autre")
    p, run = await un_probleme(org, agent, user)
    await un_probleme(autre_org, autre_agent, autre_user, critere="Autre")
    async with client_http() as c:
        liste = (await c.get(A, headers=entetes(jeton, org))).json()
        assert [x["titre"] for x in liste["lignes"]] == ["Suit le parcours"] and liste["compteurs"] == {"a_trier": 1, "en_cours": 0, "testee": 0, "publiee": 0}
        assert liste["lignes"][0]["workflow_nom"] == "Agent routes" and liste["lignes"][0]["origine_suggeree"] == "recette"
        detail = (await c.get(f"{A}/{p['id']}", headers=entetes(jeton, org))).json()
        assert detail["replique"] == "Je veux un rdv" and detail["cas"][0]["run_id"] == run.id and [t["temps"] for t in detail["avancement"]] == ["test_cree", "brouillon", "rejoue", "publie"]
        # un problème d'une autre organisation est introuvable, en lecture comme en écriture
        autre = (await db_client.lister_les_ameliorations(autre_org))[0][0]
        assert (await c.get(f"{A}/{autre['id']}", headers=entetes(jeton, org))).status_code == 404
        assert (await c.put(f"{A}/{autre['id']}", json={"etat": "en_cours"}, headers=entetes(jeton, org))).status_code == 404
        assert (await c.post(f"{A}/{autre['id']}/rejouer", headers=entetes(jeton, org))).status_code == 404


async def test_l_etat_se_change_a_la_main_sauf_testee_et_publiee(sans_preparation_des_organisations):
    org, user, jeton, agent = await decor("etat")
    p, _ = await un_probleme(org, agent, user)
    async with client_http() as c:
        h = entetes(jeton, org)
        assert (await c.put(f"{A}/{p['id']}", json={"etat": "en_cours", "origine": "client"}, headers=h)).json()["etat"] == "en_cours"
        assert (await c.put(f"{A}/{p['id']}", json={"assigne": user.id}, headers=h)).json()["assigne"] == user.id
        assert (await c.put(f"{A}/{p['id']}", json={"assigne": 999999}, headers=h)).status_code == 404
        assert (await c.put(f"{A}/{p['id']}", json={"etat": "testee"}, headers=h)).status_code == 422  # jamais à la main
        assert (await c.put(f"{A}/{p['id']}", json={}, headers=h)).status_code == 422
        await avancement.apres_une_suite_verte(org, agent.id)
        assert (await c.put(f"{A}/{p['id']}", json={"etat": "a_trier"}, headers=h)).status_code == 409
        assert (await c.put(f"{A}/{p['id']}", json={"etat": "ignoree"}, headers=h)).json()["etat"] == "ignoree"
        assert (await c.get(A, headers=h)).json()["lignes"] == []  # un problème ignoré sort de la file


async def test_un_test_depuis_la_replique_fautive_et_le_rejeu(sans_preparation_des_organisations, monkeypatch):
    org, user, jeton, agent = await decor("depuis")
    run = await un_appel(agent, user, org, journal=[ev("user-transcription", 1, {"text": "Je veux un rdv", "final": True}), ev("bot-text", 2, {"text": "D'accord."})])
    await ingestion.ingerer_un_appel_juge(run, org, [verdict_juge("Suit le parcours", replique=2, preuve="D'accord")], [("moi", "Je veux un rdv"), ("agent", "D'accord.")])
    p = (await db_client.lister_les_ameliorations(org))[0][0]
    async with client_http() as c:
        h = entetes(jeton, org)
        r = await c.post(f"{A}/{p['id']}/test", headers=h)
        assert r.status_code == 200, r.text
        tests = await db_client.lire_une_amelioration(org, p["id"])
        assert tests["avancement"]["test_cree"] is True
        sans_criteres = await db_client.lister_les_ameliorations(org)  # le problème est encore là
        assert len(sans_criteres[0]) == 1
        # un problème du code n'a pas de réplique à interdire : les critères sont demandés
        contexte = {"impasse": {"impasses": 1, "journal": [{"impasse": 1, "motif": "x", "tour": 2}]}}
        await ingestion.bilan_de_l_appel(await un_appel(agent, user, org, contexte=contexte), org)
        code = next(x for x in (await db_client.lister_les_ameliorations(org))[0] if x["releve_par"] == "code")
        assert (await c.post(f"{A}/{code['id']}/test", headers=h)).status_code == 422
        # le rejeu passe par la fonction de l'action, la suite verte fait passer le problème « Testée »
        async def suite_verte(*_a, **_k):
            await avancement.apres_une_suite_verte(org, agent.id)
            return {"ok": True, "reussis": 2, "total": 2, "suite_complete": True}

        monkeypatch.setattr("api.routes.ameliorations.executer", lambda *_a, **_k: suite_verte())
        rejeu = (await c.post(f"{A}/{p['id']}/rejouer", headers=h)).json()
        assert rejeu == {"ok": True, "reussis": 2, "total": 2, "suite_complete": True, "etat": "testee"}


# --- la page Qualité (C, D, E) -----------------------------------------------------------------------------------------------


def bilan(issue, *, motif=None, transfert=False, raccroche=False, latence=1.0, version=1):
    return {
        "boucle": {
            "version": {"version": version},
            "indicateurs": {"issue_obtenue": issue, "transfert": transfert, "raccroche_avant_la_fin": raccroche, "latence_mediane": latence, "impasses": 0, "motif": motif, "cout": 0.1},
        }
    }


async def test_la_qualite_agrege_les_chiffres_les_motifs_les_agents_et_les_versions(sans_preparation_des_organisations):
    org, user, jeton, agent = await decor("qualite")
    definitions = await db_client.get_workflow(agent.id, organization_id=org)  # noqa: F841
    juge_ok = {"juge": {"etat": "juge", "verdicts": [{"verdict": "reussi"}, {"verdict": "reussi"}]}}
    juge_mi = {"juge": {"etat": "juge", "verdicts": [{"verdict": "reussi"}, {"verdict": "rate"}]}}
    await un_appel(agent, user, org, annotations={**bilan(True, motif="Rendez-vous", latence=1.0), **juge_ok})
    await un_appel(agent, user, org, annotations={**bilan(True, motif="Rendez-vous", latence=3.0), **juge_mi})
    await un_appel(agent, user, org, annotations={**bilan(False, motif="Tarif", raccroche=True, latence=2.0)})
    await un_appel(agent, user, org, annotations=bilan(True, transfert=True, latence=2.0))
    async with client_http() as c:
        q = (await c.get("/api/v1/qualite", headers=entetes(jeton, org))).json()
    g = q["global"]
    assert g["appels"] == 4 and g["juges"] == 2 and g["note"] == 3.75  # (5 + 2,5) / 2
    assert g["issues"] == 3 and g["part_issue"] == 0.75 and g["transferts"] == 1 and g["raccroches"] == 1 and g["reponse_mediane"] == 2.0
    assert q["motifs"] == [{"motif": "Rendez-vous", "appels": 2, "part_resolu": 1.0}, {"motif": "Tarif", "appels": 1, "part_resolu": 0.0}]
    assert q["agents"][0]["workflow_nom"] == "Agent qualite" and q["agents"][0]["appels"] == 4
    assert q["versions"] == []  # une seule version dans la fenêtre : rien à comparer


async def test_la_qualite_accepte_la_fenetre_envoyee_par_l_ecran_en_texte(sans_preparation_des_organisations):
    """L'écran envoie `?jours=7` ou `?jours=30` : un `Literal[7, 30]` refusait toujours le texte (la page restait en erreur)."""
    org, user, jeton, agent = await decor("qualitefenetre")
    async with client_http() as c:
        for jours in (7, 30):
            r = await c.get(f"/api/v1/qualite?jours={jours}", headers=entetes(jeton, org))
            assert r.status_code == 200, (jours, r.text)
        assert (await c.get("/api/v1/qualite?jours=14", headers=entetes(jeton, org))).status_code == 422


def test_la_comparaison_avant_apres_garde_les_versions_vues_par_agent():
    def ligne(wf, version, issue):
        return {"workflow_id": wf, "workflow_nom": f"A{wf}", "version": version, "annotations": bilan(issue, version=version)}

    lignes = [ligne(1, 3, False), ligne(1, 3, True), ligne(1, 4, True), ligne(2, 1, True)]
    compare = qualite._versions(lignes)
    assert [(v["workflow_id"], v["version"], v["appels"], v["part_issue"]) for v in compare] == [(1, 4, 1, 1.0), (1, 3, 2, 0.5)]  # l'agent 2 n'a qu'une version


def test_une_ligne_illisible_ne_casse_pas_les_chiffres():
    assert qualite.note_du_juge({"etat": "juge", "verdicts": []}) is None and qualite.note_du_juge({}) is None
    assert qualite.part(1, 0) is None


async def test_la_file_a_juger_se_lit_avec_l_agent_et_la_duree(sans_preparation_des_organisations):
    from api.services.juge import file

    org, user, jeton, agent = await decor("ajuger")
    run = await un_appel(agent, user, org, annotations=bilan(True, motif="Dépannage"), usage={"call_duration_seconds": 75})
    await file.ajouter(org, {"id": f"appel-{run.id}", "type": "appel", "workflow_id": agent.id, "run_id": run.id})
    async with client_http() as c:
        lignes = (await c.get(f"{A}/a-juger", headers=entetes(jeton, org))).json()
    assert len(lignes) == 1 and lignes[0]["workflow_nom"] == "Agent ajuger" and lignes[0]["duree"] == 75.0 and lignes[0]["motif"] == "Dépannage"


def test_la_fenetre_de_frequence_ignore_les_cas_trop_anciens():
    vieux = (datetime.now(UTC) - timedelta(days=45)).isoformat()
    recent = datetime.now(UTC).isoformat()
    p = {"releve_par": "juge", "workflow_id": 1, "cas": [{"le": vieux}, {"le": recent}]}
    assert vues.frequence(p, {1: 4}, {1: 9}) == {"n": 1, "sur": 4, "genre": "appels"}
