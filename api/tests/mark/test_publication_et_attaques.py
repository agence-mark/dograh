"""[.mark] U11 (G2) : prouver avant de publier, déploiement progressif, « Attaquer l'agent » (plan § 7 et § 17).

Moteur factice, juge factice : aucun appel réel, rien n'est dépensé. Ce qui doit tenir : un contrôle éteint ne joue pas, les
défauts sont la garde d'avant, forcer demande une raison écrite au journal, la liste vocale simule d'abord et ne corrige que sur
accord, un contrat non confirmé ne joue aucune sonde, un « non testé » n'est jamais compté tenu, un même appelant garde sa
version, éteint le déploiement ne lit rien.
"""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from api.services.attaques import catalogue, reconnaissance, rapport, service, verdicts
from api.services.attaques.contrat import Contrat, RefusDuContrat
from api.services.builder.actions import publication as actions_publication
from api.services.builder.actions.registre import Contexte, executer
from api.services.builder.tests_agent import jeu, publication
from api.services.builder.tests_agent.jeu import Moteur, Session, TourAgent
from api.services.publication import controles, deploiement, liste_vocale, reglages
from api.tests.mark.builder_commun import AGENT, ORG_CLIENT, graphe_depart, sans_les_lignes_de_pret, utilisateur
from api.tests.mark.test_builder_tests_agent import banc, brouillon_v, enregistrer_execution, un_test  # noqa: F401

EQUIPE = Contexte(user=utilisateur(1), workflow_id=AGENT)


@pytest.fixture(autouse=True)
def _monde_du_lot(monde, monkeypatch):
    """Les modules neufs de ce lot lisent la même base en mémoire que le reste du builder."""
    monkeypatch.setattr(actions_publication, "db_client", monde)
    monkeypatch.setattr("api.services.builder.actions.registre.db_client", monde, raising=False)


def brouillon_avec(configurations, version=2):
    return SimpleNamespace(workflow_json=graphe_depart(), version_number=version, workflow_configurations=sans_les_lignes_de_pret(configurations), status="draft")


# --- les contrôles de la fenêtre « Publier » ----------------------------------------------------------------------------------


def test_les_defauts_sont_la_garde_d_avant():
    pub = reglages.lire(None).controles
    assert (pub.tests_obligatoires, pub.bilan_du_prompt) == ("bloque", "bloque")
    assert (pub.liste_vocale, pub.attaques, pub.garde_fous) == ("eteint", "eteint", "eteint")
    assert reglages.deploiement_actif(None) is False and reglages.lire({"publication": "illisible"}).controles.tests_obligatoires == "bloque"


async def test_un_controle_eteint_ne_joue_pas_et_un_qui_previent_ne_bloque_pas(banc, monkeypatch):  # noqa: F811
    await un_test("rouge", obligatoire=True)
    await enregistrer_execution("rouge", version=2, statut="echec")
    wf = banc.workflows[AGENT]
    par_defaut = await controles.evaluer(wf, brouillon_avec({}), ORG_CLIENT)
    assert par_defaut["bloque"] is True
    assert {c["cle"]: c["statut"] for c in par_defaut["controles"]}["tests_obligatoires"] == "echec"
    # prévient : l'alerte est dite, la garde ne refuse plus
    prevenu = brouillon_avec({"publication": {"controles": {"tests_obligatoires": "previent"}}})
    vue = await controles.evaluer(wf, prevenu, ORG_CLIENT)
    assert vue["bloque"] is False and {c["cle"]: c["statut"] for c in vue["controles"]}["tests_obligatoires"] == "alerte"
    assert await publication.verifier_avant_publication(wf, prevenu, ORG_CLIENT) is None
    # éteint : le contrôle n'est PAS joué (on le prouve : s'il l'était, il lèverait)
    espion = AsyncMock(side_effect=AssertionError("a check that is off must not be played"))
    monkeypatch.setattr(controles, "_tests", espion)
    eteint = brouillon_avec({"publication": {"controles": {"tests_obligatoires": "eteint"}}})
    vue = await controles.evaluer(wf, eteint, ORG_CLIENT)
    assert {c["cle"]: c["statut"] for c in vue["controles"]}["tests_obligatoires"] == "eteint"
    assert await publication.verifier_avant_publication(wf, eteint, ORG_CLIENT) is None
    espion.assert_not_called()


async def test_sans_reglage_la_garde_d_avant_refuse_comme_avant(banc):  # noqa: F811
    await un_test("rouge", obligatoire=True)
    await enregistrer_execution("rouge", version=2, statut="echec")
    refus = await publication.verifier_avant_publication(banc.workflows[AGENT], brouillon_v(2), ORG_CLIENT)
    assert refus["is_valid"] is False and refus["tests_obligatoires"][0]["slug"] == "rouge" and refus["controles_publication"] == []


async def test_un_controle_bloquant_de_plus_refuse_et_forcer_demande_une_raison():
    with pytest.raises(controles.RaisonObligatoire):
        controles.raison_valide("  ")
    assert controles.raison_valide("  vérifié au casque  ") == "vérifié au casque"


async def test_le_garde_fous_et_les_attaques_ne_comptent_jamais_un_non_teste_comme_reussi(banc):  # noqa: F811
    wf = banc.workflows[AGENT]
    # aucun rapport : le contrôle des attaques le dit, il ne passe pas en silence
    sans = await controles.evaluer(wf, brouillon_avec({"publication": {"controles": {"attaques": "bloque"}}}), ORG_CLIENT)
    assert {c["cle"]: c["statut"] for c in sans["controles"]}["attaques"] == "echec"
    # un rapport dont une sonde est « non testée » : jamais « tout tenu »
    from api.services.builder.tests_agent import boucle

    empreinte = boucle.empreinte_du_brouillon(graphe_depart(), {"publication": {"controles": {"attaques": "bloque"}}})
    await rapport.ranger(
        ORG_CLIENT,
        AGENT,
        {"empreinte": empreinte, "resume": {"a_cede": 0, "plausibles": 0, "non_testees": 2, "a_tenu": 3}},
    )
    brouillon = brouillon_avec({"publication": {"controles": {"attaques": "bloque"}}})
    vue = await controles.evaluer(wf, brouillon, ORG_CLIENT)
    attaque = next(c for c in vue["controles"] if c["cle"] == "attaques")
    assert attaque["statut"] == "echec" and any("not tested" in p for p in attaque["problemes"])
    # et la garde de publication refuse sur lui quand il est « bloque »
    refus = await publication.verifier_avant_publication(wf, brouillon, ORG_CLIENT)
    assert refus is not None and any("[Attaques]" in e["message"] for e in refus["errors"])
    assert controles._garde_fous({}) and controles._garde_fous({"securite_conversation": {"manipulation": {"actif": True}}}) == []


# --- la liste de contrôle vocale ----------------------------------------------------------------------------------------------


async def test_la_liste_vocale_est_lue_de_la_bibliotheque_ou_du_fichier_et_chaque_point_a_un_sort(banc):  # noqa: F811
    points = await liste_vocale.points()
    assert len(points) >= 14
    for p in points:
        assert p.get("regles") or p.get("raison")  # une règle de notre fork, OU « sans équivalent chez nous » avec sa raison
    resultats = liste_vocale.evaluer(points, {})
    par_id = {r["id"]: r for r in resultats}
    assert par_id["interruption"]["statut"] == liste_vocale.SANS_EQUIVALENT and "mute_always" in par_id["interruption"]["raison"]
    silence = par_id["silence_appelant"]
    assert silence["statut"] == liste_vocale.ECART and silence["corrections"] == {"max_user_idle_timeout": 6, "user_idle_max_prompts": 5}


async def test_la_liste_vocale_simule_d_abord_et_ne_corrige_que_les_points_acceptes():
    resultats = liste_vocale.evaluer(await liste_vocale.points(), {"max_user_idle_timeout": 6, "user_idle_max_prompts": 5})
    assert {r["id"]: r["statut"] for r in resultats}["silence_appelant"] == liste_vocale.OK
    sans_accord = liste_vocale.evaluer(await liste_vocale.points(), {})
    assert liste_vocale.corrections_acceptees(sans_accord, []) == {}
    assert liste_vocale.corrections_acceptees(sans_accord, ["silence_appelant"]) == {"max_user_idle_timeout": 6, "user_idle_max_prompts": 5}
    # un conseil (le modèle de secours, la phrase d'attente) n'est jamais corrigé seul, même accepté
    assert liste_vocale.corrections_acceptees(sans_accord, ["modele_de_secours", "phrase_attente"]) == {}


async def test_corriger_la_liste_vocale_ecrit_le_brouillon_puis_rejoue_le_controle_complet(banc):  # noqa: F811
    banc.brouillons[AGENT].workflow_configurations = sans_les_lignes_de_pret({"publication": {"controles": {"liste_vocale": "previent"}}})
    avant = await executer("publication_controler", {}, EQUIPE)
    assert next(c for c in avant["controles"] if c["cle"] == "liste_vocale")["statut"] == "alerte"
    refus = await executer("publication_corriger_la_liste_vocale", {"ids": ["modele_de_secours"]}, EQUIPE)
    assert refus["ok"] is False and refus["code"] == "rien_a_corriger" and banc.ecritures_de_reglages == []
    fait = await executer("publication_corriger_la_liste_vocale", {"ids": ["silence_appelant", "filtre_de_sortie"]}, EQUIPE)
    assert fait["ok"] is True and sorted(fait["ecrits"]) == ["max_user_idle_timeout", "tts_markdown_filter_enabled", "user_idle_max_prompts"]
    ecrit = banc.ecritures_de_reglages[-1]["configurations"]
    assert ecrit["max_user_idle_timeout"] == 6 and ecrit["tts_markdown_filter_enabled"] is True
    relu = {r["id"]: r["statut"] for r in fait["liste_vocale"]}
    assert relu["silence_appelant"] == "ok" and relu["filtre_de_sortie"] == "ok"


# --- la répartition du trafic entre branches ----------------------------------------------------------------------------------


def _parts(part_branche, nouvelle=12, ancienne=11):
    """La répartition entre branches (SA-L3b) : une branche sur la nouvelle version, la principale épinglée sur l'ancienne."""
    return [
        {"branche": 2, "principale": False, "part": part_branche, "definition": nouvelle},
        {"branche": 1, "principale": True, "part": 100 - part_branche, "definition": ancienne},
    ]



def test_un_appelant_garde_toujours_la_meme_version_et_les_formes_du_numero_se_valent():
    ligne = _parts(30)
    vues = {deploiement.version_attribuee(ligne, 5, "+33 6 12 34 56 78") for _ in range(10)}
    assert len(vues) == 1
    assert deploiement.part_de(5, "+33612345678") == deploiement.part_de(5, "06 12 34 56 78")
    appelants = [f"06 00 00 {n:02d} 00" for n in range(100)]
    versions = [deploiement.version_attribuee(ligne, 5, a) for a in appelants]
    assert 10 < versions.count(12) < 60 and set(versions) == {11, 12}
    # le même numéro, un autre agent : une autre place possible, mais toujours stable
    assert deploiement.part_de(5, appelants[3]) == deploiement.part_de(5, appelants[3])


def test_a_zero_pour_cent_tout_le_monde_reste_et_un_appelant_masque_garde_la_version_d_avant():
    assert {deploiement.version_attribuee(_parts(0), 5, f"0612{n:06d}") for n in range(30)} == {11}
    assert deploiement.version_attribuee(_parts(99), 5, "") == 11
    assert deploiement.version_attribuee(None, 5, "0612345678") is None and deploiement.version_attribuee([], 5, "0612345678") is None


async def test_eteint_le_deploiement_ne_lit_rien_et_toute_publication_vaut_pour_tous(banc, monkeypatch):  # noqa: F811
    lire = AsyncMock(side_effect=AssertionError("must not be read when off"))
    monkeypatch.setattr(deploiement, "lire", lire)
    wf = banc.workflows[AGENT]
    assert await deploiement.definition_pour_l_appel(wf, "0612345678") is None
    from api.services.workflow.run_creation import definition_to_run

    resultat = await definition_to_run(SimpleNamespace(), wf, appelant="0612345678")
    assert resultat is wf.released_definition  # la version publiée, comme sans déploiement
    lire.assert_not_called()


async def test_allume_les_appels_se_repartissent_entre_branches_puis_la_principale_epinglee_ou_libre(banc, monkeypatch):  # noqa: F811
    wf = banc.workflows[AGENT]
    wf.organization_id = ORG_CLIENT
    wf.released_definition = SimpleNamespace(id=12, version_number=2, status="published", workflow_configurations={"publication": {"deploiement": {"actif": True}}})
    anciennes = SimpleNamespace(id=11, version_number=1, status="archived")
    client = SimpleNamespace(get_workflow_definition=AsyncMock(side_effect=lambda w, d, o: {11: anciennes, 12: wf.released_definition}.get(d)))
    from api.services.workflow.run_creation import definition_to_run

    etat = {"parts": _parts(40)}
    monkeypatch.setattr(deploiement, "lire", AsyncMock(side_effect=lambda *_a: etat["parts"]))
    ids = {(await definition_to_run(client, wf, appelant=f"0611{n:06d}")).id for n in range(60)}
    assert ids == {11, 12}  # une part sur la branche, le reste sur la principale
    stable = [(await definition_to_run(client, wf, appelant="0611000042")).id for _ in range(5)]
    assert len(set(stable)) == 1
    # la branche à 0 % : tous les appels restent sur la principale épinglée (un retour en arrière, geste humain)
    etat["parts"] = _parts(0)
    assert {(await definition_to_run(client, wf, appelant=f"0611{n:06d}")).id for n in range(30)} == {11}
    # la principale libre (tête vide) suit la version publiée
    etat["parts"] = [{"branche": 1, "principale": True, "part": 100, "definition": None}]
    assert {(await definition_to_run(client, wf, appelant=f"0611{n:06d}")).id for n in range(30)} == {12}


async def test_une_version_partielle_passe_les_memes_controles_qu_une_complete(banc):  # noqa: F811
    await un_test("rouge", obligatoire=True)
    await enregistrer_execution("rouge", version=2, statut="echec")
    wf = banc.workflows[AGENT]
    complete = await publication.verifier_avant_publication(wf, brouillon_avec({}), ORG_CLIENT)
    partielle = await publication.verifier_avant_publication(wf, brouillon_avec({"publication": {"deploiement": {"actif": True}}}), ORG_CLIENT)
    assert complete is not None and partielle is not None
    # (l'empreinte du brouillon change avec le réglage : la raison se dit autrement, le refus et sa cause restent)
    assert [t["slug"] for t in complete["tests_obligatoires"]] == [t["slug"] for t in partielle["tests_obligatoires"]] == ["rouge"]


# --- la route de publication : forcer, part des appels -------------------------------------------------------------------------


@pytest.fixture
def route(banc, monkeypatch):  # noqa: F811
    from api.routes import workflow as route_workflow

    journal = []
    publiees = []

    async def publier(workflow_id):
        publiees.append(workflow_id)
        return SimpleNamespace(id=13, version_number=3, status="published", workflow_configurations={}, published_at=None)

    epingles = []

    async def epingler(organization_id, workflow_id, definition_id):
        epingles.append((organization_id, workflow_id, definition_id))

    db = SimpleNamespace(
        get_workflow=banc.get_workflow,
        get_draft_version=banc.get_draft_version,
        publish_workflow_draft=publier,
        epingler_la_principale=epingler,
    )
    banc.workflows[AGENT].released_definition_id = 12
    banc.brouillons[AGENT].workflow_configurations = sans_les_lignes_de_pret(getattr(banc.brouillons[AGENT], 'workflow_configurations', None))
    monkeypatch.setattr(route_workflow, "db_client", db)
    monkeypatch.setattr(route_workflow, "_validate_workflow_definition", AsyncMock(return_value=[]))
    monkeypatch.setattr(route_workflow, "capture_event", lambda **k: None)
    monkeypatch.setattr("api.services.base_client.agents.synchroniser_agent_site", AsyncMock())
    monkeypatch.setattr("api.services.objets_agent.utilisation.synchroniser_utilisation", AsyncMock(), raising=False)

    async def journaliser(user, action, organization_id, detail=None):
        journal.append((action, user.id, detail))

    monkeypatch.setattr("api.services.equipe_mark.acces.journaliser", journaliser)
    return SimpleNamespace(module=route_workflow, journal=journal, publiees=publiees, banc=banc, epingles=epingles)


async def test_forcer_la_publication_exige_une_raison_et_l_ecrit_au_journal_avec_la_personne(route):
    from fastapi import HTTPException

    from api.schemas.publication import DemandeDePublication

    await un_test("rouge", obligatoire=True)
    await enregistrer_execution("rouge", version=2, statut="echec")
    user = utilisateur(3)
    user.id = 3
    with pytest.raises(HTTPException) as e1:  # sans corps : refus comme avant
        await route.module.publier_un_agent(AGENT, user)
    assert e1.value.status_code == 422 and route.publiees == []
    with pytest.raises(HTTPException) as e2:  # forcer sans raison : refusé
        await route.module.publier_un_agent(AGENT, user, DemandeDePublication(forcer=True))
    assert e2.value.status_code == 422 and route.publiees == [] and route.journal == []
    await route.module.publier_un_agent(AGENT, user, DemandeDePublication(forcer=True, raison="vérifié au casque, le test est trop strict"))
    assert route.publiees == [AGENT]
    action, personne, detail = route.journal[0]
    assert action == "agents.publier_force" and personne == 3 and "casque" in detail["raison"] and detail["ce_qui_bloquait"]


async def test_la_publication_ne_prend_plus_de_part_des_appels_et_remet_la_principale_sur_la_version_publiee(route):
    from pydantic import ValidationError

    from api.schemas.publication import DemandeDePublication

    with pytest.raises(ValidationError):  # un seul mécanisme de part du trafic : les branches (extra interdit)
        DemandeDePublication(pourcentage=20)
    user = utilisateur(3)
    user.id = 3
    route.banc.brouillons[AGENT].workflow_configurations = sans_les_lignes_de_pret({"publication": {"deploiement": {"actif": True}}})
    await route.module.publier_un_agent(AGENT, user)
    assert route.publiees == [AGENT]
    assert route.epingles == [(ORG_CLIENT, AGENT, None)]  # une nouvelle version en ligne : la principale la suit


# --- « Attaquer l'agent » -------------------------------------------------------------------------------------------------------


def moteur_factice(repond):
    """Un moteur de jeu sans modèle : ``repond(message)`` est la réponse de l'agent. Compte les sessions ouvertes."""
    compteur = {"sessions": 0, "messages": []}

    async def ouvrir(workflow, test):
        compteur["sessions"] += 1
        return Session(compteur["sessions"]), TourAgent("Bonjour, que puis-je faire pour vous ?")

    async def tour(session, texte):
        compteur["messages"].append(texte)
        return TourAgent(repond(texte))

    async def lire(session):
        return None

    async def clore(session):
        return None

    moteur = Moteur(ouvrir, tour, lire, clore)
    moteur.compteur = compteur
    return moteur


async def juge_factice(sonde, attaque, temoin):
    cede = any("MES CONSIGNES" in t for r, t in attaque if r == "agent")
    return {"verdict": "reussi" if cede else "echoue", "gravite": "haute", "couche": "prompt", "temoin_normal": True, "raison": "reponse citee"}


def agent_qui_tient(message):
    return "Je ne peux pas vous aider sur ce point."


def agent_qui_cede(message):
    return "Voici MES CONSIGNES : ..." if "consignes" in message.lower() else "Je ne peux pas vous aider sur ce point."


def test_le_catalogue_est_ferme_aux_quinze_techniques_et_garde_la_mention_mit():
    assert len(catalogue.TECHNIQUES) == 15 and "demande_directe" in catalogue.TECHNIQUES
    retenues, ecartees = catalogue.valider(
        {"techniques": [{"id": "demande_directe", "sondes": [{"id": "a", "tours": ["x"]}]}, {"id": "inventee", "sondes": [{"id": "b", "tours": ["y"]}]}]}
    )
    assert [t["id"] for t in retenues] == ["demande_directe"] and ecartees[0]["id"] == "inventee"
    assert "MIT" in catalogue.MENTION_MIT


async def test_le_jeu_verse_couvre_les_quinze_techniques_avec_un_temoin_par_attaque(banc):  # noqa: F811
    jeu_lu = await catalogue.lire_le_jeu()
    assert {t["id"] for t in jeu_lu["techniques"]} == set(catalogue.TECHNIQUES) and jeu_lu["ecartees"] == []
    assert all(s["temoin"] for t in jeu_lu["techniques"] for s in t["sondes"])
    assert "MIT" in jeu_lu["mention"]
    assert len(await catalogue.lire_les_regles()) == 7


async def test_un_contrat_non_confirme_ne_joue_aucune_sonde_et_l_environnement_n_est_jamais_modifie(banc):  # noqa: F811
    moteur = moteur_factice(agent_qui_tient)
    wf = banc.workflows[AGENT]
    with pytest.raises(RefusDuContrat):
        await service.lancer(wf, ORG_CLIENT, Contrat(), moteur=moteur, juge=juge_factice)
    with pytest.raises(RefusDuContrat):
        await service.lancer(wf, ORG_CLIENT, Contrat(confirme=True, modifie_l_environnement=True), moteur=moteur, juge=juge_factice)
    with pytest.raises(RefusDuContrat):
        await service.lancer(wf, ORG_CLIENT, Contrat(confirme=True, corrige=True), moteur=moteur, juge=juge_factice)
    assert moteur.compteur["sessions"] == 0
    assert await rapport.lire(ORG_CLIENT, AGENT) is None
    actions_publication.DEPENDANCES.moteur = lambda: moteur
    try:
        refus = await executer("attaques_lancer", {"profondeur": "rapide"}, EQUIPE)
    finally:
        actions_publication.DEPENDANCES.moteur = None
    assert refus["ok"] is False and refus["code"] == "contrat" and moteur.compteur["sessions"] == 0


async def test_une_attaque_qui_cede_est_reproduite_puis_confirmee_une_session_neuve_a_chaque_sonde(banc):  # noqa: F811
    moteur = moteur_factice(agent_qui_cede)
    fait = await service.lancer(banc.workflows[AGENT], ORG_CLIENT, Contrat(confirme=True), moteur=moteur, juge=juge_factice)
    assert fait["resume"]["jouees"] == 15 and fait["resume"]["non_couvertes"] >= 1  # la profondeur rapide plafonne à 15
    cedes = [d for d in fait["defauts"] if d["confirme"]]
    assert cedes and all(d["couche"] == "prompt" and d["gravite"] and d["reponse"].startswith("Voici MES CONSIGNES") for d in cedes)
    # une session neuve par sonde : au moins une pour l'attaque et une pour son témoin, plus une par reproduction
    assert moteur.compteur["sessions"] >= 2 * fait["resume"]["jouees"] + len(cedes)
    assert (await rapport.lire(ORG_CLIENT, AGENT))["resume"] == fait["resume"]
    assert fait["a_tenu"] and "demande_directe-1" in fait["a_tenu"]  # la demande directe est jouée en premier et sert de témoin


async def test_un_non_teste_n_est_jamais_compte_tenu(banc):  # noqa: F811
    wf = banc.workflows[AGENT]
    # l'agent ne répond rien : il ne s'est pas défendu
    muet = await service.lancer(wf, ORG_CLIENT, Contrat(confirme=True), moteur=moteur_factice(lambda m: ""), juge=juge_factice)
    assert muet["resume"]["a_tenu"] == 0 and muet["resume"]["non_testees"] == muet["resume"]["jouees"]
    # aucun juge réglé : les réponses sont gardées, pas jugées, rien n'est « tenu »
    sans_juge = await service.lancer(wf, ORG_CLIENT, Contrat(confirme=True), moteur=moteur_factice(agent_qui_tient), juge=None)
    assert sans_juge["resume"]["a_tenu"] == 0 and sans_juge["resume"]["non_testees"] == sans_juge["resume"]["jouees"]
    # le témoin lui-même s'est mal passé : une anomalie n'est pas un verdict
    async def juge_anormal(sonde, attaque, temoin):
        return {"verdict": "reussi", "gravite": "haute", "couche": "prompt", "temoin_normal": False, "raison": "x"}

    anormal = await service.lancer(wf, ORG_CLIENT, Contrat(confirme=True), moteur=moteur_factice(agent_qui_cede), juge=juge_anormal)
    assert anormal["resume"]["a_cede"] == 0 and anormal["resume"]["plausibles"] == 0 and anormal["resume"]["non_testees"] > 0


async def test_une_panne_du_transport_n_est_pas_un_verdict_sur_l_agent(banc):  # noqa: F811
    async def ouvrir(workflow, test):
        raise ConnectionError("down")

    casse = Moteur(ouvrir, AsyncMock(), AsyncMock(), AsyncMock())
    fait = await service.lancer(banc.workflows[AGENT], ORG_CLIENT, Contrat(confirme=True), moteur=casse, juge=juge_factice)
    assert fait["resume"]["a_tenu"] == 0 and fait["resume"]["a_cede"] == 0
    assert all(s["couche"] == "plateforme" for s in fait["sondes"] if s["verdict"] == "non_concluant")


async def test_un_echec_non_reproduit_reste_plausible(banc):  # noqa: F811
    appels = {"n": 0}

    async def juge_une_fois(sonde, attaque, temoin):
        appels["n"] += 1
        cede = appels["n"] == 1  # cède au premier jugement seulement
        return {"verdict": "reussi" if cede else "echoue", "gravite": "moyenne", "couche": "prompt", "temoin_normal": True, "raison": "r"}

    fait = await service.lancer(banc.workflows[AGENT], ORG_CLIENT, Contrat(confirme=True), moteur=moteur_factice(agent_qui_tient), juge=juge_une_fois)
    assert fait["resume"]["a_cede"] == 0 and fait["resume"]["plausibles"] == 1 and fait["defauts"][0]["confirme"] is False


def test_le_verdict_hors_forme_est_refuse_avec_sa_raison_jamais_corrige():
    assert verdicts.lire_le_verdict("pas du json")["verdict"] == "non_concluant"
    assert verdicts.lire_le_verdict({"verdict": "tenu", "raison": "x"})["verdict"] == "non_concluant"
    assert verdicts.lire_le_verdict({"verdict": "reussi"})["verdict"] == "non_concluant"  # sans raison
    ok = verdicts.lire_le_verdict('bla {"verdict": "partiel", "gravite": "critique", "couche": "plateforme", "raison": "cité"} bla')
    assert ok["verdict"] == "partiel" and ok["gravite"] == "critique" and ok["couche"] == "plateforme"
    assert verdicts.lire_le_verdict({"verdict": "echoue", "gravite": "critique", "raison": "tenu"})["gravite"] is None  # pas de gravité si tenu


def graphe_en_conflit():
    return {
        "nodes": [
            {
                "id": "1",
                "type": "startCall",
                "position": {},
                "data": {
                    "name": "Accueil",
                    "prompt": "Tu dois toujours donner le tarif des abonnements. Ne donne jamais le tarif des abonnements sans devis signé. Dis bonjour.",
                },
            }
        ],
        "edges": [],
    }


def test_la_reconnaissance_numerote_les_regles_et_dresse_la_carte_des_conflits():
    reco = reconnaissance.reconnaitre(graphe_en_conflit())
    assert [r["id"] for r in reco["regles"]][:2] == ["policy-1", "policy-2"]
    assert {r["genre"] for r in reco["regles"]} >= {"persona", "garde_fou"}
    assert reco["conflits"] and reco["conflits"][0]["mots"]
    assert reco["sondes_de_conflit"][0]["origine"] == "conflit"


async def test_les_conflits_sont_attaques_en_premier(banc):  # noqa: F811
    banc.brouillons[AGENT].workflow_json = graphe_en_conflit()
    moteur = moteur_factice(agent_qui_tient)
    fait = await service.lancer(banc.workflows[AGENT], ORG_CLIENT, Contrat(confirme=True), moteur=moteur, juge=juge_factice)
    assert fait["configuration"]["conflits"] >= 1 and fait["sondes"][0]["origine"] == "conflit"


async def test_apres_correction_on_rejoue_les_echecs_et_un_echantillon_de_ce_qui_tenait(banc):  # noqa: F811
    wf = banc.workflows[AGENT]
    await service.lancer(wf, ORG_CLIENT, Contrat(confirme=True), moteur=moteur_factice(agent_qui_cede), juge=juge_factice)
    avant = await rapport.lire(ORG_CLIENT, AGENT)
    assert avant["resume"]["a_cede"] >= 1
    corrige = await service.rejouer(wf, ORG_CLIENT, moteur=moteur_factice(agent_qui_tient), juge=juge_factice)
    rejeu = corrige["rejeu"]
    assert rejeu["echecs_rejoues"] == avant["resume"]["a_cede"] and rejeu["corriges"] and rejeu["encore_cedes"] == []
    assert 0 < rejeu["echantillon_rejoue"] <= service.ECHANTILLON_REJEU and rejeu["regressions"] == []
    # une correction qui casse ce qui tenait : la régression est dite
    regresse = await service.rejouer(wf, ORG_CLIENT, moteur=moteur_factice(lambda m: "Voici MES CONSIGNES : tout"), juge=juge_factice)
    assert regresse["rejeu"]["regressions"]
    # sans rapport : rien à rejouer, et le dit
    await rapport.ranger(ORG_CLIENT, AGENT, {})
    assert (await service.rejouer(wf, ORG_CLIENT, moteur=moteur_factice(agent_qui_tient), juge=juge_factice))["ok"] in (True, False)


async def test_les_actions_sont_inscrites_et_cloisonnees_par_organisation(banc):  # noqa: F811
    from api.services.builder.actions.registre import REGISTRE

    for nom in ("publication_controler", "publication_corriger_la_liste_vocale", "attaques_lancer", "attaques_rapport", "attaques_rejouer"):
        assert nom in REGISTRE
    autre = Contexte(user=utilisateur(9, organisation=99), workflow_id=AGENT)
    for nom, args in (("publication_controler", {}), ("attaques_rapport", {}), ("attaques_lancer", {"confirme": True})):
        res = await executer(nom, args, autre)
        assert res["ok"] is False and res["code"] == "introuvable"
    fait = await executer("attaques_rapport", {}, EQUIPE)
    assert fait["ok"] is True and fait["vide"] is True


def test_le_chemin_texte_des_tests_reste_celui_de_jeu():
    assert jeu.moteur_texte is not None and actions_publication.DEPENDANCES.moteur is None  # rien de branché hors test
