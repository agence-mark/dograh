"""[.mark] passages-fiables, lot B : l'arbitre du passage d'étape.

Plan `Labo-agent-vocal/plans/passages-fiables/` (§ 7, § 12 bis R1/R2/R6, § 12 ter L0-B). Le VRAI moteur (banc fendu) et le
VRAI classifieur (sous-classe de `LLMClassifier`) ; seule la requête au fournisseur (`greffier.interroger`) est remplacée
par une réponse écrite d'avance.

| Test | Ce qu'il prouve |
|---|---|
| choix sûr | l'arbitre est sûr d'une sortie (au-dessus du seuil) : le code la prend, l'étape d'arrivée reparle, coût versé à part |
| rien | « rester », sous le seuil, erreur, délai, JSON illisible, 429 : aucun passage, la raison est tracée, l'appel continue |
| seuil de l'étape | le seuil réglé sur l'étape remplace 0,8 |
| désaccord | l'agent a pris une autre porte que l'arbitre : l'agent gagne, le désaccord est tracé |
| jeton | une décision née dans une autre visite d'étape est jetée et tracée |
| fiche d'abord | la condition sur la fiche passe avant l'arbitre (une porte par tour) |
| format refusé | le fournisseur refuse le schéma : la même requête repart en mode JSON |
| parallèle | la réplique de la personne qui entre dans la conversation lance l'arbitre, sans l'attendre ; étape éteinte : rien ne part |
| aucun mot de métier | la requête envoyée est la consigne générique plus les données de l'étape ; aucun mot de métier dans le code |
| allumage | l'arbitre est éteint par défaut, allumé par défaut sur « choix » et « libre », réglable |
"""

import asyncio
import json
import re
from pathlib import Path

import pytest

from api.services.workflow import arbitre as arbitre_mod
from api.services.workflow import decideur_de_fin_de_tour as decideur
from api.services.workflow import passage_sur_la_fiche as passage
from api.services.workflow.arbitre import (
    ArbitreDuPassage,
    ClassifieurDeLArbitre,
    RESTER,
    derniers_echanges,
    etat_a_juger,
    question_de_l_etape,
)
from api.tests.mark.test_passages_fiables_fiche import (
    _etape,
    graphe,
    monter,
    GreffierFactice,
)

ECHANGES = [
    {"role": "assistant", "content": "Que souhaitez-vous ?"},
    {"role": "user", "content": "Je voudrais continuer."},
]


def _reponse(choix, confiance):
    autres = {"refus": 0.0, "suite": 0.0, RESTER: 0.0}
    autres[choix] = confiance
    return json.dumps({"passage": {"choice": choix, "probabilities": autres}})


class Faux:
    """Le fournisseur de l'arbitre : une réponse écrite d'avance, ou une erreur, ou un retard."""

    def __init__(self, reponse=None, erreur=None, retard=0.0):
        self.reponse, self.erreur, self.retard = reponse, erreur, retard
        self.requetes = []

    async def __call__(self, service, systeme, message, schema=None):
        self.requetes.append({"systeme": systeme, "message": message, "schema": schema})
        if self.retard:
            await asyncio.sleep(self.retard)
        if self.erreur is not None:
            raise self.erreur
        return self.reponse, {"jetons_entree": 120, "jetons_sortie": 15}


class Erreur(Exception):
    def __init__(self, statut):
        super().__init__(f"HTTP {statut}")
        self.status_code = statut


class Collecteur:
    def __init__(self):
        self.verses = []

    def verser_llm(self, nom, modele, entree, sortie):
        self.verses.append((nom, entree, sortie))


GRAPHE_LIBRE = {"qui_decide_du_passage": "libre", "champs_etape": "nom,objet"}


async def _arbitre(faux, monkeypatch, *, etape=None, fiche=None, delai=3.0, greffier=None):
    monkeypatch.setattr("api.services.pipecat.greffier.interroger", faux)
    harness = await monter(graphe(etape or GRAPHE_LIBRE), fiche=fiche, greffier=greffier or GreffierFactice())
    engine = harness.engine
    engine.arbitre_service = object()
    engine.collecteur_de_cout = Collecteur()
    engine.arbitre = ArbitreDuPassage(engine)
    jeton = engine.jeton_de_visite()
    assert engine.arbitre.lancer(jeton, engine.active_agent.current_node, ECHANGES, delai=delai)
    return harness, engine, jeton


def _ligne(engine):
    return engine._gathered_context[arbitre_mod.CLE_ARBITRE][-1]


@pytest.mark.asyncio
async def test_choix_sur_le_code_prend_la_porte_et_le_cout_est_a_part(monkeypatch):
    harness, engine, _ = await _arbitre(Faux(_reponse("suite", 0.95)), monkeypatch)
    try:
        qui, *_ = await _fin(engine)
        assert qui == "arbitre" and _etape(engine) == "suite"
        engine.active_agent.queue_frame.assert_awaited()
        ligne = _ligne(engine)
        assert ligne["choix"] == "suite" and ligne["resultat"] == "prise" and ligne["jetons_entree"] == 120
        passe = engine._gathered_context[passage.CLE_PASSAGES][-1]
        assert passe["raison"] == "arbitre" and passe["resultat"] == "prise"
        assert engine.collecteur_de_cout.verses == [("arbitre", 120, 15)]
    finally:
        await harness.stop()


async def _fin(engine, texte="Très bien."):
    depart, jeton = engine.etat_pour_le_filet(), engine.jeton_de_visite()
    return await decideur.decider(engine, texte, depart, jeton), depart, jeton


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "cas, faux, delai, attendu",
    [
        ("rester", lambda: Faux(_reponse(RESTER, 0.99)), 3.0, "rien"),
        ("sous le seuil", lambda: Faux(_reponse("suite", 0.5)), 3.0, "sous_le_seuil"),
        ("erreur", lambda: Faux(erreur=RuntimeError("boum")), 3.0, "erreur"),
        ("quota", lambda: Faux(erreur=Erreur(429)), 3.0, "429"),
        ("délai", lambda: Faux(_reponse("suite", 0.99), retard=1.0), 0.05, "delai"),
        ("JSON illisible", lambda: Faux("ceci n'est pas du json"), 3.0, "illisible"),
        ("hors options", lambda: Faux(json.dumps({"passage": {"choice": "inconnue", "probabilities": {}}})), 3.0, "illisible"),
    ],
)
async def test_rien_ne_se_passe_et_la_raison_est_tracee(cas, faux, delai, attendu, monkeypatch):
    harness, engine, _ = await _arbitre(faux(), monkeypatch, delai=delai)
    try:
        qui, *_ = await _fin(engine)
        assert qui is None, cas
        assert _etape(engine) == "etape", cas
        assert _ligne(engine)["resultat"] == attendu, (cas, _ligne(engine))
        assert passage.CLE_PASSAGES not in engine._gathered_context
        engine.active_agent.queue_frame.assert_not_awaited()
    finally:
        await harness.stop()


@pytest.mark.asyncio
async def test_le_seuil_de_l_etape_remplace_le_defaut(monkeypatch):
    harness, engine, _ = await _arbitre(
        Faux(_reponse("suite", 0.6)), monkeypatch, etape={**GRAPHE_LIBRE, "seuil_de_l_arbitre": 0.5}
    )
    try:
        qui, *_ = await _fin(engine)
        assert qui == "arbitre" and _etape(engine) == "suite"
    finally:
        await harness.stop()


@pytest.mark.asyncio
async def test_l_agent_a_pris_une_autre_porte_l_agent_gagne_et_le_desaccord_est_trace(monkeypatch):
    harness, engine, jeton = await _arbitre(Faux(_reponse("suite", 0.97)), monkeypatch)
    try:
        depart = engine.etat_pour_le_filet()
        await engine.prendre_porte_ecrite("refus")  # l'agent choisit une autre sortie que l'arbitre
        qui = await decideur.decider(engine, "Entendu.", depart, jeton)
        assert qui is None and _etape(engine) == "refus"
        [desaccord] = engine._gathered_context[arbitre_mod.CLE_DESACCORDS]
        assert desaccord["arbitre"] == "suite" and desaccord["agent_arrive_a"] == "Refus"
    finally:
        await harness.stop()


@pytest.mark.asyncio
async def test_l_agent_et_l_arbitre_d_accord_aucun_desaccord(monkeypatch):
    harness, engine, jeton = await _arbitre(Faux(_reponse("suite", 0.97)), monkeypatch)
    try:
        depart = engine.etat_pour_le_filet()
        await engine.prendre_porte_ecrite("suite")
        await decideur.decider(engine, "Entendu.", depart, jeton)
        assert arbitre_mod.CLE_DESACCORDS not in engine._gathered_context
    finally:
        await harness.stop()


@pytest.mark.asyncio
async def test_une_decision_nee_dans_une_autre_visite_est_jetee(monkeypatch):
    harness, engine, jeton = await _arbitre(Faux(_reponse("suite", 0.97)), monkeypatch)
    try:
        await engine.set_node("etape")  # la visite a changé depuis la demande
        assert await engine.arbitre.resultat(jeton) is not None  # la décision existe...
        assert await engine.arbitre.resultat(engine.jeton_de_visite()) is None  # ...pas pour cette visite
        qui, *_ = await _fin(engine)
        assert qui is None and _etape(engine) == "etape"
    finally:
        await harness.stop()


@pytest.mark.asyncio
async def test_la_condition_sur_la_fiche_passe_avant_l_arbitre(monkeypatch):
    harness, engine, _ = await _arbitre(
        Faux(_reponse("suite", 0.99)), monkeypatch, fiche={"nom": "Lemaire", "objet": "refusé"}, etape={**GRAPHE_LIBRE}
    )
    try:
        qui, *_ = await _fin(engine)
        assert qui == "fiche" and _etape(engine) == "refus"
        assert arbitre_mod.CLE_ARBITRE not in engine._gathered_context
    finally:
        await harness.stop()


@pytest.mark.asyncio
async def test_le_fournisseur_refuse_le_schema_la_meme_requete_repart_en_mode_json(monkeypatch):
    faux = Faux(_reponse("suite", 0.95))
    appels = {"n": 0}
    original = faux.__call__

    async def refuse_le_premier(service, systeme, message, schema=None):
        appels["n"] += 1
        if schema is not None:
            raise Erreur(400)
        return await original(service, systeme, message, schema)

    harness, engine, _ = await _arbitre(refuse_le_premier, monkeypatch)
    try:
        qui, *_ = await _fin(engine)
        assert qui == "arbitre" and appels["n"] == 2
    finally:
        await harness.stop()


# --------------------------------------------------------------------------- #
# Le parallèle, l'allumage, ce que l'arbitre lit
# --------------------------------------------------------------------------- #


@pytest.mark.asyncio
async def test_la_replique_de_la_personne_lance_l_arbitre_sans_l_attendre(monkeypatch):
    faux = Faux(_reponse("suite", 0.95), retard=0.3)
    monkeypatch.setattr("api.services.pipecat.greffier.interroger", faux)
    harness = await monter(graphe(GRAPHE_LIBRE), greffier=GreffierFactice())
    try:
        engine = harness.engine
        engine.arbitre_service = object()
        engine.arbitre = ArbitreDuPassage(engine)
        decideur._brancher_l_arbitre_a_la_conversation(engine)
        decideur._brancher_l_arbitre_a_la_conversation(engine)  # deux fois : un seul crochet
        debut = asyncio.get_running_loop().time()
        engine.context.add_message({"role": "assistant", "content": "Que souhaitez-vous ?"})
        engine.context.add_message({"role": "user", "content": "Je voudrais continuer."})
        assert asyncio.get_running_loop().time() - debut < 0.1  # l'entrée du message n'attend rien
        await asyncio.sleep(0.05)
        assert len(faux.requetes) == 1  # parti en parallèle
        assert (await engine.arbitre.resultat(engine.jeton_de_visite())).choix == "suite"
    finally:
        await harness.stop()


@pytest.mark.asyncio
async def test_etape_sans_arbitre_rien_ne_part(monkeypatch):
    faux = Faux(_reponse("suite", 0.95))
    monkeypatch.setattr("api.services.pipecat.greffier.interroger", faux)
    harness = await monter(graphe({"qui_decide_du_passage": "collecte", "champs_etape": "nom,objet"}), greffier=GreffierFactice())
    try:
        engine = harness.engine
        engine.arbitre_service = object()
        engine.arbitre = ArbitreDuPassage(engine)
        decideur._brancher_l_arbitre_a_la_conversation(engine)
        engine.context.add_message({"role": "user", "content": "Je voudrais continuer."})
        await asyncio.sleep(0.05)
        assert faux.requetes == []
    finally:
        await harness.stop()


def test_l_arbitre_est_eteint_par_defaut_allume_sur_choix_et_libre_et_reglable():
    from types import SimpleNamespace

    def noeud(**donnees):
        return SimpleNamespace(data=SimpleNamespace(**donnees))

    assert not passage.reglages_du_passage(noeud()).arbitre
    assert not passage.reglages_du_passage(noeud(qui_decide_du_passage="agent")).arbitre
    assert not passage.reglages_du_passage(noeud(qui_decide_du_passage="collecte")).arbitre
    assert passage.reglages_du_passage(noeud(qui_decide_du_passage="choix")).arbitre
    assert passage.reglages_du_passage(noeud(qui_decide_du_passage="libre")).arbitre
    assert not passage.reglages_du_passage(noeud(qui_decide_du_passage="libre", arbitre=False)).arbitre
    assert passage.reglages_du_passage(noeud(arbitre=True)).arbitre
    assert passage.reglages_du_passage(noeud()).seuil == 0.8
    assert passage.reglages_du_passage(noeud(seuil_de_l_arbitre=0.9)).seuil == 0.9
    assert passage.reglages_du_passage(noeud(seuil_de_l_arbitre=7)).seuil == 0.8  # hors bornes : le défaut
    # Une valeur inconnue ne casse rien : l'agent garde la main.
    assert passage.reglages_du_passage(noeud(qui_decide_du_passage="autre")).qui == "agent"


@pytest.mark.asyncio
async def test_la_requete_de_l_arbitre_ne_porte_que_la_consigne_generique_et_les_donnees_de_l_etape(monkeypatch):
    faux = Faux(_reponse("suite", 0.95))
    harness, engine, _ = await _arbitre(faux, monkeypatch)
    try:
        await engine.arbitre.resultat(engine.jeton_de_visite())
        [requete] = faux.requetes
        noeud = engine.active_agent.current_node
        question, _ = question_de_l_etape(noeud)
        # Les portes de l'étape avec leur description d'écran, plus « rester » ; les 10 derniers échanges.
        assert set(question.options) == {"refus", "suite", RESTER}
        assert "Suite : Quand Suite." in requete["message"] and "Personne : Je voudrais continuer." in requete["message"]
        assert requete["schema"]["required"] == ["passage"]
        # Le texte envoyé = consigne générique + gabarit de Pipecat + données : aucun mot de métier.
        texte = f"{requete['systeme']}\n{requete['message']}".lower()
        for mot in MOTS_DE_METIER:
            assert mot not in texte, mot
        assert len(derniers_echanges([{"role": "user", "content": str(i)} for i in range(30)])) == 10
        assert derniers_echanges([{"role": "tool", "content": "x"}, {"role": "system", "content": "y"}]) == []
        assert "Étape en cours : Collecte" in etat_a_juger(noeud, [("user", "a")])
    finally:
        await harness.stop()


MOTS_DE_METIER = (
    "poêle", "poele", "cheminée", "granulé", "véranda", "veranda", "devis", "rendez-vous", "entretien", "marque",
    "contrat", "dépannage", "magasin", "facture", "réservation", "ramonage", "garantie",
)


def test_aucun_mot_de_metier_dans_le_code_de_l_arbitre_et_du_passage():
    racine = Path(arbitre_mod.__file__).parent
    for nom in ("arbitre.py", "passage_sur_la_fiche.py", "decideur_de_fin_de_tour.py"):
        source = (racine / nom).read_text(encoding="utf-8").lower()
        for mot in MOTS_DE_METIER:
            assert not re.search(rf"\b{re.escape(mot)}", source), (nom, mot)


def test_le_classifieur_reutilise_le_rendu_le_schema_et_la_lecture_de_pipecat():
    from pipecat.classifiers.llm.classifier import LLMClassifier

    assert issubclass(ClassifieurDeLArbitre, LLMClassifier)
    for nom in ("_render", "_schema", "_parse", "_result"):
        assert getattr(ClassifieurDeLArbitre, nom) is getattr(LLMClassifier, nom)
    assert ClassifieurDeLArbitre._ask is not LLMClassifier._ask  # seul l'appel change (jetons, 429)


@pytest.mark.asyncio
async def test_session_clavier_l_arbitre_sur_a_la_fin_de_la_reponse_le_code_passe(
    db_session, async_session, test_client_factory, monkeypatch
):
    from api.tests.mark.test_clavier_porte_la_fiche import FICHE, _monter
    from api.tests.mark.test_passages_fiables_fiche import definition_clavier
    from api.tests.mark.test_passation_clavier import _dit, _session, _texte, _vide

    monkeypatch.setattr("api.services.pipecat.greffier.interroger", Faux(_reponse("suite", 0.95)))
    user, workflow = await _monter(
        db_session, async_session, FICHE, definition_clavier({"qui_decide_du_passage": "libre"})
    )
    reponses = await _session(
        test_client_factory,
        user,
        workflow,
        [_vide(), _dit(_texte("D'accord."), _texte("Voici la suite."))],
        ["continuons s'il vous plaît"],
    )
    fiche = reponses[-1]["checkpoint"]["gathered_context"]
    assert (fiche.get(arbitre_mod.CLE_ARBITRE) or [{}])[-1].get("resultat") == "prise", fiche
    assert [p["raison"] for p in fiche.get(passage.CLE_PASSAGES) or []] == ["arbitre"], fiche
    assert "Suite" in (fiche.get("nodes_visited") or []), fiche


@pytest.mark.asyncio
async def test_session_clavier_l_arbitre_en_erreur_ne_coute_pas_le_tour(
    db_session, async_session, test_client_factory, monkeypatch
):
    from api.tests.mark.test_clavier_porte_la_fiche import FICHE, _monter
    from api.tests.mark.test_passages_fiables_fiche import definition_clavier
    from api.tests.mark.test_passation_clavier import _dit, _session, _texte, _vide

    monkeypatch.setattr("api.services.pipecat.greffier.interroger", Faux(erreur=Erreur(429)))
    user, workflow = await _monter(
        db_session, async_session, FICHE, definition_clavier({"qui_decide_du_passage": "libre"})
    )
    reponses = await _session(
        test_client_factory, user, workflow, [_vide(), _dit(_texte("D'accord."))], ["continuons s'il vous plaît"]
    )
    fiche = reponses[-1]["checkpoint"]["gathered_context"]
    assert (fiche.get(arbitre_mod.CLE_ARBITRE) or [{}])[-1].get("resultat") == "429", fiche
    assert passage.CLE_PASSAGES not in fiche and "Suite" not in (fiche.get("nodes_visited") or []), fiche
