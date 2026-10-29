"""[.mark] passages-fiables, décisions d'Evan du 29/10 après le rebanc : l'arbitre décide AVANT la réponse de l'agent, et
« laisser la parole » ne passe plus par un outil.

Rebanc allumé (runs 50-66) : l'arbitre a voté 74 fois sans passer une seule porte (sa décision, appliquée à la fin de la
réplique de l'agent, était reportée parce que la réplique finissait par une question) ; « laisser la parole » n'a jamais
accordé d'attente (outil appelé à tort, nom d'outil corrompu au run 59, appel légitime du run 65 refusé).

1. **L'arbitre avant la réponse** (comme Retell) : il juge la parole de la personne ; la requête de l'agent attend son
   résultat (borné par le délai de l'étape) ; s'il est sûr et choisit une sortie, l'étape change AVANT que la requête
   parte, et l'étape d'arrivée répond directement (aucun tour de plus). Mêmes exceptions que l'option 2 (fin, retour au
   principal, transfert garanti) : laissées à l'agent. Le passage par l'arbitre à la fin de la réplique n'existe plus.
2. **Laisser la parole sans outil** : la demande de temps est une question oui/non à part dans le même appel au
   classifieur, posée seulement case allumée ; si oui, le code accorde l'attente et l'agent répond normalement.

| Test | Ce qu'il prouve |
|---|---|
| E5, deux familles | la marque non suivie (conversation calquée sur E5) : la requête part DÉJÀ dans l'étape d'arrivée, sans relance ; attente tracée |
| lent, deux familles | l'arbitre dépasse le délai : la requête part sans lui, dans l'étape d'avant ; rien n'est pris plus tard |
| rester, sous le seuil | rien, la requête part dans l'étape |
| fin | une sortie vers une fin : laissée à l'agent, ni avant, ni après la réplique |
| fin de réplique | une décision sûre lue à la fin de la réplique ne fait plus passer (le passage a lieu avant ou pas du tout) |
| une porte par tour | après un passage avant la requête, la fin de la réplique de l'étape d'arrivée ne prend pas une seconde porte |
| arbitre éteint | aucune attente, aucune décision consultée |
| clavier | l'étape d'arrivée répond dans le même tour (un seul modèle consommé) |
| temps accordé | « attendez, je cherche » : l'attente est accordée par le code, aucun outil offert |
| temps refusé | une adresse, un « oui » : rien |
| temps seul | arbitre de l'étape éteint, case allumée : la seule question du temps part, la requête n'attend pas |
| temps et sortie | les deux questions dans le même appel |
| case éteinte | aucune question du temps ; outil jamais offert |
| personne qui reparle | la décision du temps arrivée pendant qu'elle parle n'accorde rien |
| moniteur | l'attente accordée pendant la réponse due la laisse due ; un silence déjà surveillé passe au délai de l'attente |
| clavier, temps | l'attente est tracée au clavier ; l'agent répond normalement |
"""

from __future__ import annotations

import asyncio
import json
from types import SimpleNamespace

import pytest

from api.services.pipecat.call_monitor_processor import CallMonitorProcessor
from api.services.workflow import arbitre as arbitre_mod
from api.services.workflow import decideur_de_fin_de_tour as decideur
from api.services.workflow import laisser_la_parole as parole
from api.services.workflow import passage_sur_la_fiche as passage
from api.services.workflow.arbitre import RESTER, ArbitreDuPassage
from api.tests.mark.test_passages_fiables_agnostique import FAMILLES, _brancher, _requete
from api.tests.mark.test_passages_fiables_arbitre import Faux
from api.tests.mark.test_passages_fiables_fiche import GreffierFactice, _etape, graphe, monter

GRAPHE_LIBRE = {"qui_decide_du_passage": "libre", "champs_etape": "nom,objet"}
# Conversation calquée sur E5 (une marque que l'établissement ne suit pas), sans donnée personnelle.
E5 = [
    {"role": "assistant", "content": "Quelle est la marque de votre appareil ?"},
    {"role": "user", "content": "C'est une marque que vous ne suivez pas, je crois."},
]


def _choix(choix, confiance, temps=None):
    probabilites = {"refus": 0.0, "suite": 0.0, RESTER: 0.0}
    probabilites[choix] = confiance
    reponse = {"passage": {"choice": choix, "probabilities": probabilites}}
    if temps is not None:
        reponse["temps"] = {"probability": temps}
    return json.dumps(reponse)


def _temps(probabilite):
    return json.dumps({"temps": {"probability": probabilite}})


async def _monter_l_arbitre(monkeypatch, faux, etape=None, *, fiche=None, reglages=None, vers_la_fin=False):
    """Le vrai moteur, l'arbitre branché à la conversation comme au téléphone et au clavier."""
    monkeypatch.setattr("api.services.pipecat.greffier.interroger", faux)
    harness = await monter(graphe(etape or GRAPHE_LIBRE, vers_la_fin=vers_la_fin), fiche=fiche, greffier=GreffierFactice())
    engine = harness.engine
    engine.arbitre_service = object()
    engine.arbitre = ArbitreDuPassage(engine)
    if reglages is not None:
        engine.active_agent.reglages = reglages
    decideur._brancher_l_arbitre_a_la_conversation(engine)
    return harness, engine


def _la_personne_parle(engine, messages):
    """La parole de la personne entre dans la conversation : l'arbitre part (téléphone et clavier, même crochet)."""
    for message in messages:
        engine.context.add_message(dict(message))


def _dernier_dit(charge) -> str:
    """La dernière parole de l'agent dans l'historique de la session clavier."""
    dits = [m.get("content") for m in charge["checkpoint"]["messages"] if m.get("role") == "assistant" and m.get("content")]
    return dits[-1] if dits else ""


def _lignes(engine, cle=arbitre_mod.CLE_ARBITRE):
    return engine._gathered_context.get(cle) or []


# --------------------------------------------------------------------------- #
# 1. L'arbitre avant la réponse
# --------------------------------------------------------------------------- #


@pytest.mark.asyncio
@pytest.mark.parametrize("famille", FAMILLES)
async def test_e5_l_etape_d_arrivee_repond_directement_a_la_parole_de_la_personne(famille, monkeypatch):
    harness, engine = await _monter_l_arbitre(monkeypatch, Faux(_choix("suite", 0.95), retard=0.05))
    try:
        cerveau = await _brancher(engine, famille)
        _la_personne_parle(engine, E5)
        await _requete(engine, cerveau, list(E5))
        assert _etape(engine) == "suite"
        [requete] = cerveau.requetes
        assert "Tu es l'étape Suite." in requete["systeme"]  # l'étape d'arrivée répond à la parole de la personne
        engine.active_agent.queue_frame.assert_not_awaited()  # aucun tour de plus
        passe = engine._gathered_context[passage.CLE_PASSAGES][-1]
        assert passe["raison"] == "arbitre" and passe["option"] == 2 and passe["resultat"] == "prise"
        ligne = _lignes(engine)[-1]
        assert ligne["resultat"] == "prise" and ligne["moment"] == "avant_la_reponse"
        assert 0.03 <= ligne["attente"] < 1.0  # l'attente ajoutée est mesurée
        assert 0.03 <= passe["duree_decision"] < 1.0
        # La fin de la réplique de l'étape d'arrivée ne reprend pas la décision.
        qui = await decideur.decider(engine, "Très bien.", engine.etat_pour_le_filet(), engine.jeton_de_visite())
        assert qui is None and _etape(engine) == "suite"
    finally:
        await harness.stop()


@pytest.mark.asyncio
@pytest.mark.parametrize("famille", FAMILLES)
async def test_arbitre_lent_la_requete_part_sans_lui(famille, monkeypatch):
    etape = {**GRAPHE_LIBRE, "delai_du_passage": 0.2}
    harness, engine = await _monter_l_arbitre(monkeypatch, Faux(_choix("suite", 0.95), retard=0.6), etape)
    try:
        cerveau = await _brancher(engine, famille)
        _la_personne_parle(engine, E5)
        debut = asyncio.get_running_loop().time()
        await _requete(engine, cerveau, list(E5))
        assert asyncio.get_running_loop().time() - debut < 0.5  # bornée par le délai de l'étape
        assert _etape(engine) == "etape"
        [requete] = cerveau.requetes
        assert "Tu es l'étape Collecte." in requete["systeme"]
        ligne = _lignes(engine)[-1]
        assert ligne["resultat"] == "trop_lent" and 0.15 <= ligne["attente"] < 0.5
        # Sa décision, arrivée trop tard, ne fait jamais passer à la fin de la réplique.
        await asyncio.sleep(0.6)
        qui = await decideur.decider(engine, "Très bien.", engine.etat_pour_le_filet(), engine.jeton_de_visite())
        assert qui is None and _etape(engine) == "etape"
        engine.active_agent.queue_frame.assert_not_awaited()
    finally:
        await harness.stop()


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "reponse, attendu",
    [(_choix(RESTER, 0.99), "rien"), (_choix("suite", 0.5), "sous_le_seuil"), ("illisible", "illisible")],
    ids=["rester", "sous-le-seuil", "illisible"],
)
async def test_rester_ou_pas_sur_rien_la_requete_part_dans_l_etape(reponse, attendu, monkeypatch):
    harness, engine = await _monter_l_arbitre(monkeypatch, Faux(reponse))
    try:
        cerveau = await _brancher(engine, FAMILLES[0].values[0])
        _la_personne_parle(engine, E5)
        await _requete(engine, cerveau, list(E5))
        assert _etape(engine) == "etape"
        assert "Tu es l'étape Collecte." in cerveau.requetes[0]["systeme"]
        assert _lignes(engine)[-1]["resultat"] == attendu
        assert passage.CLE_PASSAGES not in engine._gathered_context
    finally:
        await harness.stop()


@pytest.mark.asyncio
async def test_une_sortie_vers_une_fin_est_laissee_a_l_agent(monkeypatch):
    harness, engine = await _monter_l_arbitre(monkeypatch, Faux(_choix("suite", 0.99)), vers_la_fin=True)
    try:
        cerveau = await _brancher(engine, FAMILLES[0].values[0])
        _la_personne_parle(engine, E5)
        await _requete(engine, cerveau, list(E5))
        assert _etape(engine) == "etape" and _lignes(engine)[-1]["resultat"] == "laissee_a_l_agent"
        qui = await decideur.decider(engine, "Autre chose ?", engine.etat_pour_le_filet(), engine.jeton_de_visite())
        assert qui is None and _etape(engine) == "etape"
        qui = await decideur.decider(engine, "Très bien.", engine.etat_pour_le_filet(), engine.jeton_de_visite())
        assert qui is None and _etape(engine) == "etape"
        engine.active_agent.queue_frame.assert_not_awaited()
    finally:
        await harness.stop()


@pytest.mark.asyncio
async def test_a_la_fin_de_la_replique_l_arbitre_ne_fait_plus_passer(monkeypatch):
    harness, engine = await _monter_l_arbitre(monkeypatch, Faux(_choix("suite", 0.99)))
    try:
        _la_personne_parle(engine, E5)
        assert (await engine.arbitre.resultat(engine.jeton_de_visite())).veut_passer
        qui = await decideur.decider(engine, "Très bien.", engine.etat_pour_le_filet(), engine.jeton_de_visite())
        assert qui is None and _etape(engine) == "etape"
        engine.active_agent.queue_frame.assert_not_awaited()
    finally:
        await harness.stop()


@pytest.mark.asyncio
async def test_une_seule_porte_par_tour_apres_un_passage_avant_la_requete(monkeypatch):
    """L'arbitre passe à « suite » avant la requête ; « suite » est une collecte déjà complète : la fin de sa réplique ne
    prend pas une seconde porte sur la même parole (au tour suivant, si)."""
    from api.tests.mark.test_passages_fiables_fiche import _arete, _noeud
    from api.services.workflow.dto import ReactFlowDTO
    from api.services.workflow.workflow_graph import WorkflowGraph

    monkeypatch.setattr("api.services.pipecat.greffier.interroger", Faux(_choix("suite", 0.99)))
    g = WorkflowGraph(
        ReactFlowDTO(
            nodes=[
                _noeud("etape", "startCall", "Collecte", qui_decide_du_passage="libre"),
                _noeud("suite", "agentNode", "Suite", qui_decide_du_passage="collecte", champs_etape="nom"),
                _noeud("reprise", "agentNode", "Reprise"),
                _noeud("fin", "endCall", "Fin"),
            ],
            edges=[_arete("etape", "suite", "Suite"), _arete("suite", "reprise", "Reprise"), _arete("reprise", "fin", "Fin")],
        )
    )
    harness = await monter(g, fiche={"nom": "Lemaire"}, greffier=GreffierFactice())
    try:
        engine = harness.engine
        engine.arbitre_service = object()
        engine.arbitre = ArbitreDuPassage(engine)
        decideur._brancher_l_arbitre_a_la_conversation(engine)
        cerveau = await _brancher(engine, FAMILLES[0].values[0])
        _la_personne_parle(engine, E5)
        await _requete(engine, cerveau, list(E5))
        assert _etape(engine) == "suite"
        jeton = engine.jeton_de_visite()
        qui = await decideur.decider(engine, "Très bien.", engine.etat_pour_le_filet(), jeton)
        assert qui is None and _etape(engine) == "suite"  # même parole : une seule porte
        qui = await decideur.decider(engine, "Très bien.", engine.etat_pour_le_filet(), jeton)
        assert qui == "fiche" and _etape(engine) == "reprise"  # au tour suivant, la fiche joue
    finally:
        await harness.stop()


@pytest.mark.asyncio
async def test_arbitre_eteint_aucune_attente_aucune_decision(monkeypatch):
    etape = {"qui_decide_du_passage": "collecte", "champs_etape": "nom,objet"}
    faux = Faux(_choix("suite", 0.99), retard=0.5)
    harness, engine = await _monter_l_arbitre(monkeypatch, faux, etape, fiche={"nom": "Lemaire"})
    try:
        cerveau = await _brancher(engine, FAMILLES[0].values[0])
        _la_personne_parle(engine, E5)
        debut = asyncio.get_running_loop().time()
        await _requete(engine, cerveau, list(E5))
        assert asyncio.get_running_loop().time() - debut < 0.1
        assert faux.requetes == [] and _lignes(engine) == [] and _etape(engine) == "etape"
    finally:
        await harness.stop()


@pytest.mark.asyncio
async def test_session_clavier_l_etape_d_arrivee_repond_dans_le_meme_tour(
    db_session, async_session, test_client_factory, monkeypatch
):
    from api.tests.mark.test_clavier_porte_la_fiche import FICHE, _monter
    from api.tests.mark.test_passages_fiables_fiche import definition_clavier
    from api.tests.mark.test_passation_clavier import _dit, _session, _texte, _vide

    monkeypatch.setattr("api.services.pipecat.greffier.interroger", Faux(_choix("suite", 0.95)))
    user, workflow = await _monter(
        db_session, async_session, FICHE, definition_clavier({"qui_decide_du_passage": "libre"})
    )
    reponses = await _session(
        test_client_factory,
        user,
        workflow,
        [_vide(), _dit(_texte("Voici la suite."))],  # UNE réponse du modèle pour la parole de la personne
        ["c'est une marque que vous ne suivez pas"],
    )
    fiche = reponses[-1]["checkpoint"]["gathered_context"]
    passes = fiche.get(passage.CLE_PASSAGES) or []
    assert [(p["raison"], p["option"], p["resultat"]) for p in passes] == [("arbitre", 2, "prise")], fiche
    assert "Suite" in (fiche.get("nodes_visited") or []), fiche
    assert _dernier_dit(reponses[-1]) == "Voici la suite.", reponses[-1]["checkpoint"]["messages"]


# --------------------------------------------------------------------------- #
# 2. Laisser la parole, sans outil
# --------------------------------------------------------------------------- #

ETAPE_AGENT = {"champs_etape": "nom,objet"}  # passage tout éteint : seule la case de l'agent compte


@pytest.mark.asyncio
async def test_la_demande_de_temps_est_accordee_par_le_code_sans_outil(monkeypatch):
    faux = Faux(_temps(0.93))
    harness, engine = await _monter_l_arbitre(monkeypatch, faux, ETAPE_AGENT, reglages={"laisser_la_parole": True})
    try:
        vus: list[list[str]] = []
        origine = engine._update_llm_context

        async def espion(prompt, fonctions):
            vus.append([f.name for f in fonctions])
            return await origine(prompt, fonctions)

        engine._update_llm_context = espion
        await engine.set_node("etape")
        assert vus and all("laisser_la_parole" not in noms for noms in vus)  # aucun outil offert au modèle
        _la_personne_parle(engine, [{"role": "assistant", "content": "Quel est votre numéro ?"},
                                    {"role": "user", "content": "Attendez, je cherche le document."}])
        await engine.arbitre.resultat(engine.jeton_de_visite())
        assert engine.call_monitor.attente_accordee is True
        trace = engine._gathered_context[parole.CLE_TRACE]
        assert [t["evenement"] for t in trace] == ["accordee"] and trace[0]["probabilite"] == 0.93
        [requete] = faux.requetes
        assert requete["schema"]["required"] == ["temps"]  # arbitre de l'étape éteint : la seule question du temps
    finally:
        engine.call_monitor._cancel_deadline()
        await harness.stop()


@pytest.mark.asyncio
@pytest.mark.parametrize("dit", ["8 rue des Lilas.", "Oui."], ids=["adresse", "oui"])
async def test_une_adresse_ou_un_oui_n_accorde_rien(dit, monkeypatch):
    harness, engine = await _monter_l_arbitre(monkeypatch, Faux(_temps(0.04)), ETAPE_AGENT, reglages={"laisser_la_parole": True})
    try:
        _la_personne_parle(engine, [{"role": "assistant", "content": "C'est bien ça ?"}, {"role": "user", "content": dit}])
        await engine.arbitre.resultat(engine.jeton_de_visite())
        assert engine.call_monitor.attente_accordee is False
        assert parole.CLE_TRACE not in engine._gathered_context
    finally:
        await harness.stop()


@pytest.mark.asyncio
async def test_temps_seul_la_requete_de_l_agent_n_attend_pas(monkeypatch):
    faux = Faux(_temps(0.9), retard=0.5)
    harness, engine = await _monter_l_arbitre(monkeypatch, faux, {**GRAPHE_LIBRE, "arbitre": False},
                                              reglages={"laisser_la_parole": True})
    try:
        cerveau = await _brancher(engine, FAMILLES[0].values[0])
        _la_personne_parle(engine, [{"role": "user", "content": "Attendez, je vérifie."}])
        debut = asyncio.get_running_loop().time()
        await _requete(engine, cerveau, [{"role": "user", "content": "Attendez, je vérifie."}])
        assert asyncio.get_running_loop().time() - debut < 0.2  # la question du temps ne retient pas la réponse
        await engine.arbitre.resultat(engine.jeton_de_visite())
        assert engine.call_monitor.attente_accordee is True
    finally:
        engine.call_monitor._cancel_deadline()
        await harness.stop()


@pytest.mark.asyncio
async def test_temps_et_sortie_dans_le_meme_appel(monkeypatch):
    faux = Faux(_choix(RESTER, 0.9, temps=0.95))
    harness, engine = await _monter_l_arbitre(monkeypatch, faux, reglages={"laisser_la_parole": True})
    try:
        _la_personne_parle(engine, [{"role": "user", "content": "Un instant, je regarde."}])
        decision = await engine.arbitre.resultat(engine.jeton_de_visite())
        [requete] = faux.requetes
        assert sorted(requete["schema"]["required"]) == ["passage", "temps"]
        assert decision.choix == RESTER and decision.temps == 0.95
        assert engine.call_monitor.attente_accordee is True
        texte = f"{requete['systeme']}\n{requete['message']}".lower()
        from api.tests.mark.test_passages_fiables_arbitre import MOTS_DE_METIER

        for mot in MOTS_DE_METIER:
            assert mot not in texte, mot
    finally:
        engine.call_monitor._cancel_deadline()
        await harness.stop()


@pytest.mark.asyncio
async def test_case_eteinte_aucune_question_du_temps_et_aucun_outil(monkeypatch):
    faux = Faux(_choix(RESTER, 0.9))
    harness, engine = await _monter_l_arbitre(monkeypatch, faux)
    try:
        _la_personne_parle(engine, [{"role": "user", "content": "Attendez, je cherche."}])
        await engine.arbitre.resultat(engine.jeton_de_visite())
        assert faux.requetes[0]["schema"]["required"] == ["passage"]
        assert engine.call_monitor.attente_accordee is False
        assert not hasattr(parole, "brancher_laisser_la_parole")  # l'outil n'existe plus
    finally:
        await harness.stop()


@pytest.mark.asyncio
async def test_la_personne_qui_reparle_avant_la_decision_n_obtient_rien(monkeypatch):
    harness, engine = await _monter_l_arbitre(monkeypatch, Faux(_temps(0.95), retard=0.1), ETAPE_AGENT,
                                              reglages={"laisser_la_parole": True})
    try:
        _la_personne_parle(engine, [{"role": "user", "content": "Attendez, je cherche."}])
        engine.call_monitor._user_turn_active = True  # elle reparle avant la décision
        await engine.arbitre.resultat(engine.jeton_de_visite())
        assert engine.call_monitor.attente_accordee is False
    finally:
        engine.call_monitor._user_turn_active = False
        await harness.stop()


def _moniteur(**reglages):
    moniteur = CallMonitorProcessor(
        response_source=lambda: None, on_response_timeout=lambda _s: None, on_user_idle=None,
        conversation_enabled=lambda: True,
    )
    moniteur.user_idle_timeout = 10.0
    moniteur.user_aggregator = SimpleNamespace(user_turn_controller=SimpleNamespace(has_active_user_turn=False))
    moniteur._active = True
    moniteur._waiting_for_user = True
    for nom, valeur in reglages.items():
        setattr(moniteur, nom, valeur)
    return moniteur


@pytest.mark.asyncio
async def test_moniteur_l_attente_accordee_pendant_la_reponse_due_la_laisse_due():
    moniteur = _moniteur()
    attendue = object()
    moniteur._response_watch = attendue  # la personne a fini, l'agent doit répondre : il répondra normalement
    moniteur.accorder_l_attente()
    assert moniteur.attente_accordee is True and moniteur._response_watch is attendue
    moniteur._response_watch = None
    moniteur._cancel_deadline()


@pytest.mark.asyncio
async def test_moniteur_un_silence_deja_surveille_passe_au_delai_de_l_attente():
    moniteur = _moniteur(delai_de_relance=lambda: 45.0 if moniteur.attente_accordee else None)
    moniteur._arm_idle()
    boucle = asyncio.get_running_loop()
    assert 9 < moniteur._deadline.when() - boucle.time() <= 10
    moniteur.accorder_l_attente()
    assert moniteur._deadline_kind == "idle" and 44 < moniteur._deadline.when() - boucle.time() <= 45
    moniteur._cancel_deadline()


@pytest.mark.asyncio
async def test_session_clavier_la_demande_de_temps_est_tracee_et_l_agent_repond(
    db_session, async_session, test_client_factory, monkeypatch
):
    from api.tests.mark.test_clavier_porte_la_fiche import FICHE, _monter
    from api.tests.mark.test_passation_clavier import _dit, _session, _texte

    monkeypatch.setattr("api.services.pipecat.greffier.interroger", Faux(_temps(0.95)))
    user, workflow = await _monter(db_session, async_session, {**FICHE, "laisser_la_parole": True})
    reponses = await _session(
        test_client_factory,
        user,
        workflow,
        [_dit(_texte("Bonjour.")), _dit(_texte("Je vous attends."))],
        ["Attendez, je cherche mon numéro."],
    )
    checkpoint = reponses[-1]["checkpoint"]
    trace = checkpoint["gathered_context"].get(parole.CLE_TRACE) or []
    assert [t["evenement"] for t in trace] == ["accordee"], trace
    assert _dernier_dit(reponses[-1]) == "Je vous attends.", checkpoint["messages"]
    assert not any(m.get("tool_calls") or m.get("role") == "tool" for m in checkpoint["messages"])
