"""[.mark] builder-agent-vocal, lot 6 : les tests de l'agent et la boucle d'amélioration.

Cerveau factice, moteur factice, système du client simulé : aucun appel réel. Ce qui doit tenir : création depuis une réplique,
données rendues fictives, suite rejouée en entier (B38), un test obligatoire qui échoue suffit à refuser (B42), la raison écrite sur
la réplique fautive (B40), le diagnostic avant correction (B39), le juge jamais bloquant (B43), la parité clavier / téléphone, la
publication bloquée, le tri, le retour arrière, la mise à jour des agents quand une recette change (B30).
"""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from api.services.builder import brouillon
from api.services.builder.actions.registre import Contexte, executer
from api.services.builder.bibliotheque import service
from api.services.builder.bibliotheque.modele import Banc
from api.services.builder.cerveau.factice import CerveauFactice, texte, tour
from api.services.builder.controle import service as service_controle
from api.services.builder.controle.regles import ObjetConnu
from api.services.builder.donnees_fictives import est_fictive
from api.services.builder.tests_agent import (
    boucle,
    creation,
    diagnostic,
    execution,
    export,
    jeu,
    juge,
    mise_a_jour,
    publication,
    stockage,
    verdict,
)
from api.services.builder.tests_agent.verdict import ObservationConversation
from api.services.tests_rejouables.rejeu import Essai, ResultatTest
from api.tests.mark.builder_commun import AGENT, ORG_CLIENT, ORG_MARK, graphe_depart, utilisateur

EQUIPE = Contexte(user=utilisateur(1), workflow_id=AGENT)
OBLIGATOIRE = {"type": "texte_absent", "texte": "outil_interne"}


@pytest.fixture
def banc(monde, monkeypatch):
    """Le monde simulé + les couches de ce lot branchées sur la même base en mémoire. Un brouillon version 2 existe."""
    for chemin in ("api.services.builder.tests_agent.boucle", "api.services.builder.controle.service", "api.services.builder.essai_outil"):
        import importlib

        monkeypatch.setattr(importlib.import_module(chemin), "db_client", monde)
    monkeypatch.setattr("api.db.db_client", monde)
    monde.brouillons[AGENT] = SimpleNamespace(workflow_json=graphe_depart(), version_number=2, status="draft", workflow_configurations={})
    monde.get_tools_by_uuids = AsyncMock(return_value=[])

    async def pas_d_objets(_):
        return []

    monkeypatch.setattr(service_controle, "objets_du_client", pas_d_objets)
    dependances = execution.Dependances(noms_d_outils=AsyncMock(return_value={"noter"}))
    monkeypatch.setattr(execution, "DEPENDANCES", dependances)
    return monde


def essai(numero, texte_dit, *, outils=(), etape=("2", "Fin"), reussi=True, erreur=None):
    return Essai(
        numero,
        reussi,
        "",
        {"texte": texte_dit, "outils": [{"nom": n, "arguments": {}} for n in outils], "etape": {"id": etape[0], "nom": etape[1]}, "etapes_traversees": [etape[1]], "simules": []},
        erreur=erreur,
    )


def un_rejeu(*reponses_par_test):
    """Un ``rejouer_un_tour`` factice : la réponse (liste d'essais) de chaque appel, dans l'ordre."""
    restantes = list(reponses_par_test)
    appels = []

    async def rejouer(test, agent_id, essais, organisation_id):
        appels.append(test.nom)
        liste = restantes.pop(0)
        return ResultatTest(nom=test.nom, agent_id=agent_id, essais=liste[:essais])

    rejouer.appels = appels
    return rejouer


async def un_test(nom="test-a", criteres=None, *, obligatoire=False, replique="Bonjour, je voudrais un renseignement."):
    return await creation.creer(
        ORG_CLIENT, AGENT, nom=nom, criteres=criteres or [OBLIGATOIRE], obligatoire=obligatoire, replique=replique, historique=[]
    )


# --- création -------------------------------------------------------------------------------------------------------------------------


def faux_run(organisation=ORG_CLIENT):
    """Un run clavier : l'appelant donne un vrai numéro et un vrai e-mail ; l'agent les répète."""
    evenements = [
        {"type": "rtf-bot-text", "timestamp": "2026-10-31T10:00:01", "payload": {"text": "Bonjour, quel est votre nom ?"}},
        {"type": "rtf-user-transcription", "timestamp": "2026-10-31T10:00:02", "payload": {"final": True, "text": "Marie Dupont, mon mail est marie.dupont@gmail.com"}},
        {"type": "rtf-bot-text", "timestamp": "2026-10-31T10:00:03", "payload": {"text": "Merci Marie Dupont, je note marie.dupont@gmail.com."}},
        {"type": "rtf-user-transcription", "timestamp": "2026-10-31T10:00:04", "payload": {"final": True, "text": "Et mon numéro est le 06 12 34 56 78."}},
    ]
    run = SimpleNamespace(
        logs={"realtime_feedback_events": evenements},
        gathered_context={"nom_client": "Marie Dupont", "telephone": "06 12 34 56 78"},
        workflow=SimpleNamespace(name="agent-42"),
        workflow_id=AGENT,
    )
    return run, organisation


async def test_un_test_cree_depuis_une_replique_d_un_appel_ne_garde_aucune_donnee_reelle(banc, monkeypatch):
    from api.services.tests_rejouables import creation as creation_amont

    run, org = faux_run()
    monkeypatch.setattr(creation_amont, "db_client", banc)
    banc.get_workflow_run_with_context = AsyncMock(return_value=(run, org))
    resultat = await executer(
        "tests_creer",
        {"nom": "Numéro répété", "run_id": 7, "rang": 2, "criteres": [{"type": "texte_absent", "texte": "06 12 34 56 78"}], "obligatoire": True, "origine": "client"},
        EQUIPE,
    )
    assert resultat["ok"] is True, resultat
    assert resultat["test"]["obligatoire"] is True and resultat["test"]["origine"] == "client"
    test = await stockage.lire(ORG_CLIENT, AGENT, resultat["test"]["slug"])
    brut = str(test)
    for reel in ("Marie Dupont", "gmail", "06 12 34 56 78"):
        assert reel not in brut
    assert est_fictive(test) and test["donnees_fictives"] is True
    # La même fausse valeur partout : la réplique à rejouer, l'historique et le critère se retrouvent.
    faux_numero = test["criteres"][0]["texte"]
    assert faux_numero in test["replique"] and test["source"]["run_id"] == 7


async def test_un_run_d_une_autre_organisation_est_refuse(banc, monkeypatch):
    from api.services.tests_rejouables import creation as creation_amont

    run, _ = faux_run()
    monkeypatch.setattr(creation_amont, "db_client", banc)
    banc.get_workflow_run_with_context = AsyncMock(return_value=(run, 999))
    resultat = await executer("tests_creer", {"nom": "x", "run_id": 7, "rang": 1, "criteres": [OBLIGATOIRE]}, EQUIPE)
    assert resultat["ok"] is False and await stockage.lister(ORG_CLIENT, AGENT) == []


async def test_creation_a_la_main_en_conversation_libre_et_refus_des_cas_invalides(banc):
    ok = await executer(
        "tests_creer",
        {"nom": "Appelant pressé", "scenario": "Veut un rendez-vous demain.", "personnage": "presse", "criteres": [{"type": "sans_redite"}], "origine": "fiche"},
        EQUIPE,
    )
    assert ok["ok"] is True and ok["test"]["genre"] == "conversation"
    for refuse in (
        {"nom": "sans critère", "replique": "bonjour"},
        {"nom": "critère inconnu", "replique": "bonjour", "criteres": [{"type": "inventé"}]},
        {"nom": "ni réplique ni scénario", "criteres": [OBLIGATOIRE]},
        {"nom": "origine inconnue", "replique": "bonjour", "criteres": [OBLIGATOIRE], "origine": "ailleurs"},
    ):
        assert (await executer("tests_creer", refuse, EQUIPE))["ok"] is False
    assert len(await stockage.lister(ORG_CLIENT, AGENT)) == 1


async def test_deux_tests_de_meme_nom_ont_deux_identifiants(banc):
    a, b = await un_test("Même nom"), await un_test("Même nom")
    assert a["slug"] != b["slug"]


# --- verdict par le code, B40, parité ---------------------------------------------------------------------------------------------------


def conversation(*lignes, **plus):
    return ObservationConversation(texte=" ".join(t for r, t in lignes if r == "agent"), lignes=list(lignes), **plus)


def test_chaque_critere_de_conversation_est_detecte_et_pas_detecte_a_tort():
    bon = conversation(("agent", "Bonjour."), ("moi", "Oui."), ("agent", "Très bien, c'est noté."), issue="rendez_vous", clos_par_l_agent=True, fiche={"nom": "Camille Exemple"})
    mauvais = conversation(("agent", "Merci d'avoir répondu."), ("moi", "Oui."), ("agent", "J'appelle chercher_un_creneau pour vous."), issue="abandon", clos_par_l_agent=False, fiche={})
    criteres = [
        {"type": "issue", "attendue": "rendez_vous"},
        {"type": "appel_clos_par_l_agent"},
        {"type": "mecanique_dite", "noms": ["chercher_un_creneau"]},
        {"type": "merci_en_tete", "max": 0},
        {"type": "coordonnees_prises", "champs": ["nom"]},
    ]
    assert all(r.reussi for r in verdict.evaluer_criteres(criteres, bon))
    assert not any(r.reussi for r in verdict.evaluer_criteres(criteres, mauvais))


def test_la_raison_est_ecrite_sur_la_replique_fautive():
    obs = conversation(("agent", "Bonjour."), ("moi", "Salut"), ("agent", "Je lance chercher_un_creneau."), ("moi", "ok"), ("agent", "Voilà."))
    r = verdict.evaluer_un({"type": "mecanique_dite", "noms": ["chercher_un_creneau"]}, obs)
    assert r.reussi is False and r.rang == 1 and "chercher_un_creneau" in r.raison
    r = verdict.evaluer_un({"type": "texte_absent", "texte": "voilà"}, obs)
    assert r.rang == 2 and "must not" in r.raison
    assert verdict.evaluer_un({"type": "texte_present", "texte": "introuvable"}, obs).rang == 2


def test_redites_et_rigidite_sont_relevees_sur_la_bonne_replique():
    redit = conversation(
        ("agent", "Quel est votre numéro de téléphone pour vous joindre ?"),
        ("moi", "Le 06 39 98 00 01"),
        ("agent", "Très bien. Quel est votre numéro de téléphone pour vous joindre ?"),
    )
    r = verdict.evaluer_un({"type": "sans_redite"}, redit)
    assert r.reussi is False and r.rang == 1
    assert verdict.evaluer_un({"type": "sans_rigidite"}, redit).rang == 1
    sain = conversation(("agent", "Quel est votre nom de famille ?"), ("moi", "Exemple"), ("agent", "Et votre prénom ?"))
    assert verdict.evaluer_un({"type": "sans_redite"}, sain).reussi and verdict.evaluer_un({"type": "sans_rigidite"}, sain).reussi


def journal(*evenements):
    return [{"type": t, "timestamp": f"2026-10-31T10:00:{i:02d}", "payload": p} for i, (t, p) in enumerate(evenements)]


def test_parite_clavier_et_appel_simule_meme_journal_meme_verdict():
    """Le clavier et l'appel simulé écrivent le même journal : ``observation_depuis_un_run`` rend le même verdict."""
    evts = journal(
        ("rtf-node-transition", {"node_id": "1", "node_name": "Départ"}),
        ("rtf-bot-text", {"text": "Bonjour, je vous écoute."}),
        ("rtf-user-transcription", {"final": True, "text": "Un rendez-vous."}),
        ("rtf-function-call-start", {"function_name": "noter", "arguments": {"x": 1}}),
        ("rtf-bot-text", {"text": "C'est noté, au revoir."}),
        ("rtf-node-transition", {"node_id": "2", "node_name": "Fin"}),
    )
    contexte = {"call_disposition": "rendez_vous"}
    clavier = verdict.observation_depuis_un_run(evts, contexte, {"2"})
    telephone = verdict.observation_depuis_un_run(list(reversed(evts)), contexte, {"2"})  # l'ordre du journal ne compte pas
    criteres = [
        {"type": "issue", "attendue": "rendez_vous"},
        {"type": "appel_clos_par_l_agent"},
        {"type": "outil", "nom": "noter"},
        {"type": "etape", "attendue": "Fin"},
    ]
    a, b = verdict.evaluer_criteres(criteres, clavier), verdict.evaluer_criteres(criteres, telephone)
    assert [r.reussi for r in a] == [r.reussi for r in b] == [True] * 4
    assert clavier.lignes == telephone.lignes and clavier.outils == telephone.outils


# --- la suite : contrat, B38, B42 -----------------------------------------------------------------------------------------------------------


async def test_une_suite_vide_dit_qu_elle_n_est_pas_disponible_et_ne_depense_rien(banc):
    r = await executer("tests_rejouer", {}, EQUIPE)
    assert r["disponible"] is False and r["ok"] is False and r["total"] == 0


async def test_la_suite_verte_rend_ok_total_et_echecs_vides_et_garde_les_trois_dernieres_executions(banc):
    await un_test("a")
    execution.DEPENDANCES.rejouer_un_tour = un_rejeu(*[[essai(i, "Bien sûr.") for i in (1, 2, 3)]] * 4)
    for _ in range(4):
        r = await executer("tests_rejouer", {}, EQUIPE)
    assert (r["ok"], r["echecs"], r["total"], r["suite_complete"]) == (True, [], 1, True)
    assert len(await stockage.resultats(ORG_CLIENT, AGENT, "a")) == 3  # 3 dernières exécutions seulement
    assert r["elements"][0]["statut"] == "ok" and r["carte"]["type"] == "tests"


async def test_un_seul_essai_rate_sur_trois_fait_echouer_le_test(banc):
    await un_test("a")
    execution.DEPENDANCES.rejouer_un_tour = un_rejeu([essai(1, "Bien."), essai(2, "Je lance outil_interne."), essai(3, "Bien.")])
    r = await executer("tests_rejouer", {}, EQUIPE)
    assert r["ok"] is False and r["resultats"][0]["reussis"] == 2 and r["resultats"][0]["statut"] == "echec"
    echec = r["echecs"][0]
    assert echec["essai"] == 2 and echec["rang"] == 0 and echec["replique"] == "Je lance outil_interne."
    assert "must not" in echec["raison"] and echec["diagnostic"]["cause"] == "agent" and echec["diagnostic"]["accord_requis"] is True


async def test_un_test_obligatoire_qui_echoue_suffit_a_refuser_jamais_la_moyenne(banc):
    await un_test("facile-1")
    await un_test("facile-2")
    await un_test("critique", obligatoire=True)
    bon, mauvais = [essai(i, "Bien.") for i in (1, 2, 3)], [essai(1, "Bien."), essai(2, "Bien."), essai(3, "outil_interne")]
    execution.DEPENDANCES.rejouer_un_tour = un_rejeu(mauvais, bon, bon)  # l'ordre est celui des noms : critique, facile-1, facile-2
    r = await executer("tests_rejouer", {}, EQUIPE)
    assert r["refus"] is True and r["ok"] is False and r["reussis"] == 2  # 2 tests sur 3 verts : la moyenne ne sauve rien
    assert r["echecs"][0]["obligatoire"] is True


async def test_rejouer_une_partie_de_la_suite_ne_verifie_jamais_l_agent(banc):
    await un_test("a")
    await un_test("b")
    execution.DEPENDANCES.rejouer_un_tour = un_rejeu([essai(i, "Bien.") for i in (1, 2, 3)])
    r = await executer("tests_rejouer", {"tests": ["a"]}, EQUIPE)
    assert r["ok"] is False and r["partiel"] is True and r["suite_complete"] is False and r["total"] == 1
    assert "Only part" in r["message"]


async def test_un_essai_en_erreur_est_une_cause_d_execution_et_pas_de_l_agent(banc):
    await un_test("a")
    execution.DEPENDANCES.rejouer_un_tour = un_rejeu([essai(i, "", reussi=False, erreur="TimeoutError: modèle") for i in (1, 2, 3)])
    r = await executer("tests_rejouer", {}, EQUIPE)
    assert r["ok"] is False and r["resultats"][0]["statut"] == "erreur"
    assert r["echecs"][0]["diagnostic"]["cause"] == "execution" and r["echecs"][0]["rang"] is None


def test_le_diagnostic_classe_agent_test_ou_execution():
    etapes, outils = {"depart", "fin"}, {"noter"}
    assert diagnostic.classer({"type": "etape", "attendue": "Inconnue"}, erreur=None, etapes_de_l_agent=etapes, outils_de_l_agent=outils)["cause"] == "test"
    assert diagnostic.classer({"type": "etape", "attendue": "Fin"}, erreur=None, etapes_de_l_agent=etapes, outils_de_l_agent=outils)["cause"] == "agent"
    assert diagnostic.classer({"type": "outil", "nom": "autre"}, erreur=None, etapes_de_l_agent=etapes, outils_de_l_agent=outils)["cause"] == "test"
    assert diagnostic.classer({"type": "texte_absent", "texte": "a"}, erreur=None, etapes_de_l_agent=etapes, outils_de_l_agent=outils)["cause"] == "test"
    assert diagnostic.classer(None, erreur="boom", etapes_de_l_agent=etapes, outils_de_l_agent=outils)["cause"] == "execution"


async def test_un_agent_protege_n_est_jamais_rejoue(banc):
    from api.services.tests_rejouables.modele import ErreurTestRejouable

    with pytest.raises(ErreurTestRejouable):
        await execution.rejouer_la_suite(utilisateur(1), SimpleNamespace(id=140))


# --- la conversation libre : appelant simulé et personnage --------------------------------------------------------------------------------


class MoteurFactice:
    """L'agent répond selon un script ; l'appel se clôt au tour voulu."""

    def __init__(self, repliques, fin_au_tour=None, outils=()):
        self.modele = list(repliques)
        self.repliques, self.fin_au_tour, self.vus, self.clos, self.ouvertures = list(repliques), fin_au_tour, [], False, 0
        self.lignes: list[tuple[str, str]] = []
        self.outils = outils

    def en_moteur(self):
        async def ouvrir(workflow, test):
            self.ouvertures += 1
            self.repliques, self.lignes, self.vus = list(self.modele), [], []  # chaque essai repart du début
            self.lignes.append(("agent", self.repliques.pop(0)))
            return jeu.Session(1, {"2"}), jeu.TourAgent(self.lignes[0][1])

        async def tour_(session, texte_dit):
            self.vus.append(texte_dit)
            self.lignes.append(("moi", texte_dit))
            dit = self.repliques.pop(0)
            self.lignes.append(("agent", dit))
            return jeu.TourAgent(dit, termine=self.fin_au_tour == len(self.vus))

        async def lire(session):
            return ObservationConversation(
                texte=" ".join(t for r, t in self.lignes if r == "agent"),
                lignes=list(self.lignes),
                issue="rendez_vous",
                clos_par_l_agent=self.fin_au_tour is not None,
                outils=[{"nom": n, "arguments": {}} for n in self.outils],
            )

        async def clore(session):
            self.clos = True

        return jeu.Moteur(ouvrir, tour_, lire, clore)


class AppelantScripte:
    def __init__(self, *dits):
        self.dits, self.vu = list(dits), []

    async def repondre(self, lignes):
        self.vu.append(list(lignes))
        return self.dits.pop(0)


async def test_la_conversation_s_arrete_quand_l_agent_clot_et_le_run_est_clos():
    m = MoteurFactice(["Bonjour.", "Quel est votre nom ?", "Parfait, au revoir."], fin_au_tour=2)
    appelant = AppelantScripte("Je voudrais un rendez-vous.", "Camille Exemple.")
    obs = await jeu.jouer_une_conversation(SimpleNamespace(id=1), {"scenario": {"tours_max": 10}}, appelant, m.en_moteur())
    assert [r for r, _ in obs.lignes] == ["agent", "moi", "agent", "moi", "agent"] and m.clos is True
    assert appelant.dits == []  # pas un mot de plus après la clôture


async def test_la_conversation_respecte_le_plafond_de_tours_et_l_ouverture_du_scenario():
    m = MoteurFactice(["Bonjour.", "Oui ?", "Et ensuite ?", "Encore ?"])
    appelant = AppelantScripte("encore", "toujours")
    obs = await jeu.jouer_une_conversation(SimpleNamespace(id=1), {"scenario": {"ouverture": "Allô, c'est pour un devis.", "tours_max": 3}}, appelant, m.en_moteur())
    assert m.vus[0] == "Allô, c'est pour un devis." and len(m.vus) == 3 and len(obs.lignes) == 7


async def test_le_prompt_de_l_appelant_porte_le_personnage_et_rien_d_un_metier():
    personnage = {"description": "Une personne âgée qui épelle mal.", "comportements": ["se reprend", "épelle une lettre de travers"], "fin": "dit merci et raccroche"}
    consigne = jeu.consigne_de_l_appelant(personnage, {"but": "prendre un rendez-vous"})
    assert "personne âgée" in consigne and "épelle une lettre de travers" in consigne and "prendre un rendez-vous" in consigne and "raccroche" in consigne
    assert "ne joues QUE l'appelant" in consigne


async def test_le_personnage_vient_de_la_bibliotheque(banc):
    await service.creer("personnages-appelant", "presse", "Pressé", {"description": "Toujours pressé.", "but": "aller vite"}, "evan")
    assert (await jeu.personnage_de({"personnage": "presse"}))["description"] == "Toujours pressé."
    assert await jeu.personnage_de({"personnage": "inconnu"}) == {}


async def test_l_appelant_par_cerveau_joue_l_appelant_et_pas_l_agent():
    cerveau = CerveauFactice(tour(texte(' "Je voudrais un rendez-vous." ')))
    appelant = jeu.AppelantParCerveau(cerveau, "consigne")
    dit = await appelant.repondre([("agent", "Bonjour, je vous écoute.")])
    assert dit == "Je voudrais un rendez-vous."
    msgs = cerveau.requetes[0]["messages"]
    assert msgs == [{"role": "user", "content": "Bonjour, je vous écoute."}] and cerveau.requetes[0]["outils"] == []


async def test_une_suite_de_conversations_libres_se_juge_par_le_code_avec_le_cerveau_factice(banc):
    await executer(
        "tests_creer",
        {"nom": "Libre", "scenario": "Prendre un rendez-vous.", "criteres": [{"type": "issue", "attendue": "rendez_vous"}, {"type": "appel_clos_par_l_agent"}]},
        EQUIPE,
    )
    moteur = MoteurFactice(["Bonjour.", "Noté, au revoir."], fin_au_tour=1)
    execution.DEPENDANCES.moteur = moteur.en_moteur
    execution.DEPENDANCES.cerveau = AsyncMock(return_value=CerveauFactice(*[tour(texte("Un rendez-vous, s'il vous plaît.")) for _ in range(3)]))
    r = await executer("tests_rejouer", {}, EQUIPE)
    assert r["ok"] is True, r["resultats"][0]["essais"]
    assert r["resultats"][0]["reussis"] == 3 and moteur.ouvertures == 3


async def test_sans_cerveau_une_conversation_libre_est_une_erreur_d_execution_pas_un_echec_de_l_agent(banc):
    await executer("tests_creer", {"nom": "Libre", "scenario": "x", "criteres": [{"type": "sans_redite"}]}, EQUIPE)
    execution.DEPENDANCES.cerveau = AsyncMock(return_value=None)
    r = await executer("tests_rejouer", {}, EQUIPE)
    assert r["ok"] is False and r["echecs"][0]["diagnostic"]["cause"] == "execution"


# --- le juge : à part, non bloquant, plusieurs passes quand c'est serré ----------------------------------------------------------------------


async def test_le_juge_ne_change_jamais_le_verdict_du_code(banc):
    await creation.creer(ORG_CLIENT, AGENT, nom="Avec juge", criteres=[OBLIGATOIRE], replique="Bonjour", questions_juge=["Le ton est-il naturel ?"])
    execution.DEPENDANCES.rejouer_un_tour = un_rejeu([essai(i, "Bien.") for i in (1, 2, 3)])
    execution.DEPENDANCES.cerveau = AsyncMock(return_value=CerveauFactice(tour(texte('{"ok": false, "confiance": 0.95, "raison": "froid"}'))))
    r = await executer("tests_rejouer", {}, EQUIPE)
    assert r["ok"] is True  # le juge dit non, le code dit oui : le code décide
    avis = r["resultats"][0]["juge"]
    assert avis["bloquant"] is False and avis["avis"][0]["ok"] is False and avis["avis"][0]["serre"] is False


async def test_plusieurs_passes_quand_c_est_serre_et_majorite():
    cerveau = CerveauFactice(
        tour(texte('{"ok": true, "confiance": 0.4, "raison": "peut-être"}')),
        tour(texte('{"ok": false, "confiance": 0.9, "raison": "non"}')),
        tour(texte('{"ok": false, "confiance": 0.8, "raison": "non"}')),
    )
    r = await juge.juger(cerveau, [("agent", "Bonjour.")], ["Naturel ?"])
    assert r["avis"][0] == {"question": "Naturel ?", "ok": False, "serre": True, "passes": 3, "raison": "non"} and r["bloquant"] is False


async def test_un_juge_en_panne_ou_illisible_ne_bloque_rien_et_ne_dit_pas_oui():
    from api.services.builder.cerveau.appel import ErreurCerveau

    en_panne = await juge.juger(CerveauFactice(ErreurCerveau("reseau", "down")), [("agent", "x")], ["q ?"])
    assert en_panne["bloquant"] is False and en_panne["avis"] == []
    illisible = await juge.juger(CerveauFactice(*[tour(texte("je ne sais pas"))] * 3), [("agent", "x")], ["q ?"])
    assert illisible["avis"][0]["ok"] is None


def test_la_calibration_compare_le_juge_a_nos_notes():
    avis = [{"id": str(i), "ok": i % 2 == 0} for i in range(6)]
    accord = juge.calibrer(avis, [{"id": str(i), "ok": i % 2 == 0} for i in range(6)])
    assert accord["accord"] == 1.0 and accord["calibre"] is True
    desaccord = juge.calibrer(avis, [{"id": str(i), "ok": True} for i in range(6)])
    assert desaccord["calibre"] is False and desaccord["desaccords"] == ["1", "3", "5"]
    assert juge.calibrer(avis, [{"id": "0", "ok": True}])["calibre"] is False  # trop peu de notes


# --- la publication bloquée ----------------------------------------------------------------------------------------------------------------


def brouillon_v(version, graphe=None):
    return SimpleNamespace(workflow_json=graphe or graphe_depart(), version_number=version)


def empreinte_de(graphe=None, configurations=None):
    return boucle.empreinte_du_brouillon(graphe or graphe_depart(), configurations or {})


async def enregistrer_execution(slug, *, version, statut="ok", empreinte="defaut"):
    empreinte = empreinte_de() if empreinte == "defaut" else empreinte
    await stockage.ajouter_un_resultat(ORG_CLIENT, AGENT, slug, {"le": "t", "version": version, "empreinte": empreinte, "statut": statut, "reussis": 3 if statut == "ok" else 1, "total": 3, "essais": []})


async def test_un_agent_que_le_builder_ne_suit_pas_se_publie_comme_avant(banc):
    assert await publication.verifier_avant_publication(banc.workflows[AGENT], brouillon_v(2, {"nodes": [], "edges": []}), ORG_CLIENT) is None


async def test_la_publication_est_bloquee_par_le_controle_du_prompt(banc):
    await un_test("a")  # l'agent est suivi
    mauvais = {
        "nodes": [
            {"id": "1", "type": "startCall", "position": {}, "data": {"name": "Départ", "prompt": "Appelle le 06 12 34 56 78."}},
            {"id": "2", "type": "endCall", "position": {}, "data": {"name": "Fin", "prompt": "Au revoir."}},
        ],
        "edges": [{"id": "e", "source": "1", "target": "2", "data": {}}],
    }
    refus = await publication.verifier_avant_publication(banc.workflows[AGENT], brouillon_v(2, mauvais), ORG_CLIENT)
    assert refus["is_valid"] is False and refus["garde"] == "builder"
    assert any("[Prompt check]" in e["message"] for e in refus["errors"]) and refus["controle"][0]["code"] == "exemple_de_valeur"


async def test_la_publication_est_bloquee_par_un_test_obligatoire_qui_echoue_pas_rejoue_ou_rejoue_sur_une_autre_version(banc):
    await un_test("echoue", obligatoire=True)
    await un_test("jamais-rejoue", obligatoire=True)
    await un_test("ancienne-version", obligatoire=True)
    await un_test("facultatif-rouge")
    await un_test("vert", obligatoire=True)
    await enregistrer_execution("echoue", version=2, statut="echec")
    await enregistrer_execution("ancienne-version", version=1)
    await enregistrer_execution("facultatif-rouge", version=2, statut="echec")
    await enregistrer_execution("vert", version=2)
    refus = await publication.verifier_avant_publication(banc.workflows[AGENT], brouillon_v(2), ORG_CLIENT)
    raisons = {t["slug"]: t["raison"] for t in refus["tests_obligatoires"]}
    assert set(raisons) == {"echoue", "jamais-rejoue", "ancienne-version"}  # le facultatif rouge et le vert ne bloquent pas
    assert "failed" in raisons["echoue"] and "never" in raisons["jamais-rejoue"] and "version 1" in raisons["ancienne-version"]


async def test_tout_vert_sur_le_brouillon_courant_la_publication_passe_et_l_interrupteur_la_libere(banc, monkeypatch):
    await un_test("a", obligatoire=True)
    await enregistrer_execution("a", version=2)
    assert await publication.verifier_avant_publication(banc.workflows[AGENT], brouillon_v(2), ORG_CLIENT) is None
    await enregistrer_execution("a", version=2, statut="echec")
    assert await publication.verifier_avant_publication(banc.workflows[AGENT], brouillon_v(2), ORG_CLIENT) is not None
    monkeypatch.setenv(publication.INTERRUPTEUR, "1")
    assert await publication.verifier_avant_publication(banc.workflows[AGENT], brouillon_v(2), ORG_CLIENT) is None


async def test_un_brouillon_modifie_sans_changer_de_numero_n_est_pas_publie_avant_un_nouveau_rejeu(banc):
    """Revue R1 : ``save_workflow_draft`` ne change pas le numéro de version ; seule l'empreinte (graphe + réglages) le voit."""
    await un_test("a", obligatoire=True)
    await enregistrer_execution("a", version=2)  # suite verte sur le brouillon d'origine
    assert await publication.verifier_avant_publication(banc.workflows[AGENT], brouillon_v(2), ORG_CLIENT) is None
    # le prompt est modifié, la version reste 2 : refus
    modifie = graphe_depart()
    modifie["nodes"][0]["data"]["prompt"] = "Un autre prompt, jamais rejoué."
    refus = await publication.verifier_avant_publication(banc.workflows[AGENT], brouillon_v(2, modifie), ORG_CLIENT)
    assert refus is not None and "changed since the last replay" in refus["tests_obligatoires"][0]["raison"]
    # un réglage de l'agent modifié, même graphe : refus aussi
    reglage = brouillon_v(2)
    reglage.workflow_configurations = {"fiche_au_fil_de_leau": True}
    assert await publication.verifier_avant_publication(banc.workflows[AGENT], reglage, ORG_CLIENT) is not None
    # rejoué sur le nouveau brouillon : la publication passe
    await enregistrer_execution("a", version=2, empreinte=empreinte_de(modifie))
    assert await publication.verifier_avant_publication(banc.workflows[AGENT], brouillon_v(2, modifie), ORG_CLIENT) is None
    # une exécution rangée sans empreinte (avant ce correctif) ne prouve rien
    await enregistrer_execution("a", version=2, empreinte=None)
    assert await publication.verifier_avant_publication(banc.workflows[AGENT], brouillon_v(2, modifie), ORG_CLIENT) is not None


async def test_le_rejeu_range_l_empreinte_du_graphe_et_des_reglages(banc):
    await un_test("a", obligatoire=True)
    banc.brouillons[AGENT].workflow_configurations = {"fiche_au_fil_de_leau": True}
    execution.DEPENDANCES.rejouer_un_tour = un_rejeu([essai(i, "Bien.") for i in (1, 2, 3)])
    await executer("tests_rejouer", {}, EQUIPE)
    derniere = await stockage.derniere_execution(ORG_CLIENT, AGENT, "a")
    assert derniere["empreinte"] == empreinte_de(None, {"fiche_au_fil_de_leau": True}) != empreinte_de()
    # la publication du MÊME brouillon (graphe + réglages) passe
    banc.brouillons[AGENT].version_number = 2
    assert await publication.verifier_avant_publication(banc.workflows[AGENT], banc.brouillons[AGENT], ORG_CLIENT) is None


async def test_la_route_de_publication_applique_la_garde(banc, monkeypatch):
    """Le geste d'amont (``publier_un_agent``, aussi celui du groupe) s'arrête sur le refus du builder."""
    from fastapi import HTTPException

    from api.routes import workflow as route_workflow

    await un_test("a", obligatoire=True)  # jamais rejoué
    monkeypatch.setattr(route_workflow, "db_client", banc)
    monkeypatch.setattr(route_workflow, "_validate_workflow_definition", AsyncMock(return_value=[]))
    publie = AsyncMock()
    monkeypatch.setattr(banc, "publish_workflow_draft", publie, raising=False)
    with pytest.raises(HTTPException) as e:
        await route_workflow.publier_un_agent(AGENT, utilisateur(1))
    assert e.value.status_code == 422 and e.value.detail["garde"] == "builder" and publie.await_count == 0


# --- la boucle : historique, retour arrière, tri ------------------------------------------------------------------------------------------------


def graphe_avec(prompt):
    g = graphe_depart()
    g["nodes"][0]["data"]["prompt"] = prompt
    return g


async def test_chaque_version_testee_est_gardee_et_le_retour_arriere_remet_un_brouillon(banc):
    await boucle.noter_la_version_testee(ORG_CLIENT, AGENT, graphe_avec("v1"), 2, False)
    await boucle.noter_la_version_testee(ORG_CLIENT, AGENT, graphe_avec("v1"), 2, True)  # même graphe : mise à jour, pas de doublon
    await boucle.noter_la_version_testee(ORG_CLIENT, AGENT, graphe_avec("v2"), 3, False)
    historique = await boucle.historique(ORG_CLIENT, AGENT)
    assert [h["id"] for h in historique] == ["c2", "c1"] and historique[1]["vert"] is True
    assert "changed: Départ" in historique[0]["resume"] and "instantane" not in historique[0] and historique[0]["retour_possible"] is True
    banc.brouillons[AGENT] = SimpleNamespace(workflow_json=graphe_avec("v2"), version_number=3, status="draft", workflow_configurations={})
    resultat = await boucle.retour_arriere(ORG_CLIENT, AGENT, "c1")
    assert resultat["ok"] is True and "Replay the whole suite" in resultat["message"]
    assert banc.brouillons[AGENT].workflow_json["nodes"][0]["data"]["prompt"] == "v1"
    assert banc.workflows[AGENT].released_definition.version_number == 1  # jamais une publication
    apres = await boucle.historique(ORG_CLIENT, AGENT)
    assert apres[0]["restaure_de"] == "c1" and apres[0]["vert"] is False  # à rejouer


async def test_le_retour_arriere_refuse_une_correction_inconnue(banc):
    with pytest.raises(boucle.RetourImpossible):
        await boucle.retour_arriere(ORG_CLIENT, AGENT, "c9")


async def test_rejouer_la_suite_alimente_l_historique_des_corrections(banc):
    await un_test("a")
    execution.DEPENDANCES.rejouer_un_tour = un_rejeu([essai(i, "Bien.") for i in (1, 2, 3)])
    await executer("tests_rejouer", {}, EQUIPE)
    historique = await boucle.historique(ORG_CLIENT, AGENT)
    assert len(historique) == 1 and historique[0]["vert"] is True and historique[0]["version"] == 2


def test_l_origine_est_suggeree_par_le_type_du_signalement_puis_choisie():
    assert boucle.origine_suggeree({"source": "code", "type": "impasse"}) == "code"
    assert boucle.origine_suggeree({"source": "agent", "categorie": "règle inconnue"}) == "client"
    assert boucle.origine_suggeree({"source": "agent", "categorie": "demande ambiguë"}) == "recette"
    assert set(boucle.SUITE_DE_L_ORIGINE) == {"client", "recette", "code"}


def test_le_tri_par_origine_filtre_sur_l_origine_posee_sinon_suggeree():
    from api.services.tri import pages

    contexte = {"signalements": [{"source": "agent", "motif": "m", "categorie": "règle inconnue", "tour": 1}], "impasse": {"impasses": 1, "journal": [{"impasse": 1, "motif": "x", "tour": 2}]}}
    run = {"run_id": 1, "workflow_id": AGENT, "workflow_nom": "a", "cree_le": None, "extrait": contexte, "annotations": {"tri": {"agent:0": {"statut": "ouvert", "assigne": 5, "origine": "recette"}}}}
    toutes = pages.lignes_de_tri([run])
    assert {l["id"]: (l["assigne"], l["origine"], l["origine_suggeree"]) for l in toutes} == {"agent:0": (5, "recette", "client"), "impasse:1": (None, None, "code")}
    assert [l["id"] for l in pages.lignes_de_tri([run], origine="recette")] == ["agent:0"]  # posée > suggérée
    assert [l["id"] for l in pages.lignes_de_tri([run], origine="code")] == ["impasse:1"]
    assert pages.lignes_de_tri([run], origine="client") == []


# --- B30 : mise à jour des agents quand une recette change ----------------------------------------------------------------------------------------


REGLE_V1 = {"motif": "outil_tarde", "portee": "agent", "variantes": ["Un instant, je regarde."]}
REGLE_V2 = {"motif": "outil_tarde", "portee": "agent", "variantes": ["Je regarde cela, un instant."]}
BANC = Banc(description="banc de test")


async def recette_deux_versions():
    await service.creer("phrases-du-code", "attente-outil", "Attente d'outil", {"regles": [REGLE_V1]}, "evan")
    await service.marquer("phrases-du-code", "attente-outil", 1, service.Statut.RECETTE, "evan", banc=BANC)
    await service.ajouter_version("phrases-du-code", "attente-outil", {"regles": [REGLE_V2]}, "evan")


async def test_une_recette_qui_change_prepare_des_brouillons_rejoue_les_suites_et_ne_publie_rien(banc, monkeypatch):
    from api.services.builder.actions.bibliotheque import appliquer_un_element

    await recette_deux_versions()
    # Trois agents l'utilisent en v1 : un intact, un personnalisé, un d'une autre organisation.
    banc.ajouter_agent(ORG_CLIENT, 43)
    banc.ajouter_agent(ORG_CLIENT, 44)
    banc.ajouter_agent(8, 45)
    for agent, org in ((AGENT, ORG_CLIENT), (43, ORG_CLIENT), (44, ORG_CLIENT), (45, 8)):
        await service.enregistrer_utilisation("phrases-du-code", "attente-outil", 1, org, agent)
    # Ce que la v1 a écrit dans les agents 42 et 44 (le 43 est resté tel quel, sans règle : écart = personnalisation).
    await mise_a_jour.reglages_agent.regler_phrases(ORG_CLIENT, AGENT, [REGLE_V1])
    await mise_a_jour.reglages_agent.regler_phrases(ORG_CLIENT, 44, [{**REGLE_V1, "variantes": ["Texte du client."]}])
    suites = []

    async def fausse_suite(user, workflow, **k):
        suites.append(workflow.id)
        return {"ok": True, "total": 2, "echecs": [], "disponible": True, "message": ""}

    monkeypatch.setattr(execution, "rejouer_la_suite", fausse_suite)
    ecritures_avant = len(banc.ecritures_de_reglages)
    r = await mise_a_jour.preparer(EQUIPE, "phrases-du-code", "attente-outil")
    etats = {a["agent"]: a["etat"] for a in r["agents"]}
    assert etats[AGENT] == mise_a_jour.ETAT_BROUILLON and etats[44] == mise_a_jour.ETAT_PROPOSITION
    assert etats[45] == mise_a_jour.ETAT_AUTRE_ORGANISATION
    assert etats[43] == mise_a_jour.ETAT_PROPOSITION  # sans la règle v1 : elle diffère de ce que la recette écrivait
    assert suites == [AGENT]  # seule la suite de l'agent préparé est rejouée
    # Le brouillon de l'agent 42 porte la v2 ; celui de l'agent personnalisé n'a pas bougé ; rien n'est publié.
    ecrit = banc.ecritures_de_reglages[ecritures_avant:]
    assert len(ecrit) == 1 and ecrit[0]["workflow_id"] == AGENT
    assert ecrit[0]["configurations"]["phrases_regles"][0]["variantes"] == REGLE_V2["variantes"]
    assert r["publie"] == 0 and all(w.released_definition.version_number == 1 for w in banc.workflows.values())
    del appliquer_un_element


async def test_la_liste_des_agents_d_une_recette_dit_la_version_utilisee(banc):
    await recette_deux_versions()
    await service.enregistrer_utilisation("phrases-du-code", "attente-outil", 1, ORG_CLIENT, AGENT)
    vue = await mise_a_jour.agents_qui_utilisent("phrases-du-code", "attente-outil")
    assert vue["version"] == 2 and vue["agents"] == [{"organisation": ORG_CLIENT, "agent": AGENT, "version": 1, "a_jour": False}]


async def test_une_famille_ecrite_par_le_builder_est_proposee_jamais_ecrasee(banc, monkeypatch):
    await service.creer("moules-etape", "accueil", "Accueil", {"texte": "v1"}, "evan")
    await service.ajouter_version("moules-etape", "accueil", {"texte": "v2"}, "evan")
    await service.enregistrer_utilisation("moules-etape", "accueil", 1, ORG_CLIENT, AGENT)
    ecritures = len(banc.ecritures_de_reglages)
    r = await mise_a_jour.preparer(EQUIPE, "moules-etape", "accueil", rejouer_la_suite=False)
    assert r["agents"][0]["etat"] == mise_a_jour.ETAT_PROPOSITION and len(banc.ecritures_de_reglages) == ecritures


# --- l'export ---------------------------------------------------------------------------------------------------------------------------------


async def test_l_export_est_un_fichier_sans_organisation_et_sans_donnee_reelle(banc):
    await un_test("a", obligatoire=True)
    await enregistrer_execution("a", version=2)
    lot = await export.exporter(ORG_CLIENT, AGENT, "agent-42")
    assert lot["format"] == "tests-agent-mark" and lot["tests"][0]["slug"] == "a" and "organisation_id" not in lot["tests"][0]
    assert lot["tests"][0]["executions"][0]["statut"] == "ok"
    assert b"agent-42" in export.en_octets(lot)
    assert {o for (o, _cle) in banc.configs} == {ORG_CLIENT}  # aucune écriture hors de l'organisation de l'agent
