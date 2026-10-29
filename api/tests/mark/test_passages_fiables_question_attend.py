"""[.mark] passages-fiables, correction du banc local (29/10) : une réplique qui pose une question attend la réponse.

Banc local : le décideur de fin de tour passait à la fin d'une réplique de l'agent qui posait une question.

- runs 19 et 27 : la collecte complète passe au rendez-vous juste après « Je note …, c'est bien ça ? » (relecture du
  mail, de l'adresse) : l'étape d'arrivée enchaîne sa question, la personne n'a jamais pu confirmer ;
- run 20 : l'arbitre, lancé sur « Non, je ne veux pas de contrat », a pris la fin juste après « Est-ce que je peux faire
  autre chose pour vous ? » : l'appel s'est clos sans réponse.

Règle mécanique et générale : à la fin d'une réplique qui finit par une question, le code ne prend aucune porte sur la
fiche ; la décision se refait à la fin de la réplique suivante, sur la réponse de la personne. Jamais deux tours de suite
dans la même visite d'étape (un passage sauté reste rattrapé au tour d'après).

Depuis le 29/10 (décision d'Evan après le rebanc), l'arbitre ne joue plus du tout à la fin d'une réplique : il décide sur
la parole de la personne, AVANT la réponse de l'agent. Le cas du run 20 ne peut donc plus se produire : la décision et la
parole jugée sont les mêmes.

| Test | Ce qu'il prouve |
|---|---|
| question | la détection : « ? » final, guillemets et espaces ignorés ; une question au milieu ne compte pas |
| téléphone, fiche | relecture « c'est bien ça ? » : rien ; au tour suivant la personne confirme : le code passe |
| téléphone, fiche | deux questions de suite : la seconde ne reporte plus, le code passe |
| téléphone, arbitre | « autre chose ? » : la fin de la réplique ne prend rien et ne lit plus l'arbitre ; la décision se prend sur la réponse, avant la requête |
| clavier, fiche | même chose dans une vraie session : rien au tour de la question, passage au tour de la confirmation |
| clavier, arbitre | « rester » sur la première parole, la question est posée ; la réponse fait passer avant la requête |
"""

from __future__ import annotations

import pytest

from api.services.workflow import arbitre as arbitre_mod
from api.services.workflow import decideur_de_fin_de_tour as decideur
from api.services.workflow import passage_sur_la_fiche as passage
from api.services.workflow.arbitre import ArbitreDuPassage
from api.tests.mark.test_passages_fiables_arbitre import ECHANGES, GRAPHE_LIBRE, Collecteur, Faux, _reponse
from api.tests.mark.test_passages_fiables_fiche import GreffierFactice, _etape, definition_clavier, graphe, monter

RELECTURE = "Je note Lemaire, c'est bien ça ?"
AUTRE_CHOSE = "Je comprends. Est-ce que je peux faire autre chose pour vous ?"


def _complete():
    return {"nom": "Lemaire", "objet": "une demande"}


async def _fin(engine, texte):
    depart, jeton = engine.etat_pour_le_filet(), engine.jeton_de_visite()
    return await decideur.decider(engine, texte, depart, jeton)


def _passages(engine):
    return engine._gathered_context.get(passage.CLE_PASSAGES) or []


@pytest.mark.parametrize(
    "texte, attendu",
    [
        (RELECTURE, True),
        ("Vous préférez lequel ? »", True),
        ("C'est noté ?  ", True),
        ("Très bien, merci.", False),
        ("C'est bien ça ? Je continue.", False),
        ("", False),
    ],
)
def test_la_replique_pose_une_question(texte, attendu):
    assert decideur.la_replique_pose_une_question(texte) is attendu


# --------------------------------------------------------------------------- #
# Téléphone : le moteur réel
# --------------------------------------------------------------------------- #


@pytest.mark.asyncio
async def test_telephone_fiche_la_relecture_attend_la_confirmation_puis_le_code_passe():
    harness = await monter(fiche=_complete(), greffier=GreffierFactice())
    try:
        engine = harness.engine
        assert await _fin(engine, RELECTURE) is None
        assert _etape(engine) == "etape"
        engine.active_agent.queue_frame.assert_not_awaited()
        assert [(p["raison"], p["resultat"]) for p in _passages(engine)] == [("question", "reportee_question")]
        # La personne confirme ; l'agent répond sans question : le code passe.
        assert await _fin(engine, "Merci.") == "fiche"
        assert _etape(engine) == "suite"
        assert _passages(engine)[-1]["resultat"] == "prise"
    finally:
        await harness.stop()


@pytest.mark.asyncio
async def test_telephone_fiche_deux_questions_de_suite_la_seconde_ne_reporte_plus():
    harness = await monter(fiche=_complete(), greffier=GreffierFactice())
    try:
        engine = harness.engine
        assert await _fin(engine, RELECTURE) is None
        assert await _fin(engine, "Quel jour vous arrangerait ?") == "fiche"
        assert _etape(engine) == "suite"
    finally:
        await harness.stop()


@pytest.mark.asyncio
async def test_telephone_arbitre_autre_chose_la_decision_d_avant_n_est_pas_prise(monkeypatch):
    from pipecat.processors.aggregators.llm_context import LLMContext

    monkeypatch.setattr("api.services.pipecat.greffier.interroger", Faux(_reponse("suite", 0.95)))
    harness = await monter(graphe(GRAPHE_LIBRE), greffier=GreffierFactice())
    try:
        engine = harness.engine
        engine.arbitre_service = object()
        engine.collecteur_de_cout = Collecteur()
        engine.arbitre = ArbitreDuPassage(engine)
        noeud = engine.active_agent.current_node
        assert engine.arbitre.lancer(engine.jeton_de_visite(), noeud, ECHANGES, delai=3.0)
        await engine.arbitre.resultat(engine.jeton_de_visite())
        # La fin de la réplique « autre chose ? » : rien, et l'arbitre n'y est plus lu.
        assert await _fin(engine, AUTRE_CHOSE) is None
        assert _etape(engine) == "etape" and arbitre_mod.CLE_ARBITRE not in engine._gathered_context
        # Même une réplique sans question ne fait plus passer l'arbitre à sa fin.
        assert await _fin(engine, "Très bien.") is None and _etape(engine) == "etape"
        # La personne répond : l'arbitre repart sur sa réponse et passe AVANT la requête de l'agent.
        assert engine.arbitre.lancer(engine.jeton_de_visite(), noeud, ECHANGES, delai=3.0)
        contexte = LLMContext(messages=[dict(m) for m in ECHANGES])
        assert await decideur.arbitre_avant_la_requete(engine, engine.active_agent.llm, contexte)
        assert _etape(engine) == "suite"
    finally:
        await harness.stop()


# --------------------------------------------------------------------------- #
# Clavier : une vraie session
# --------------------------------------------------------------------------- #


@pytest.mark.asyncio
async def test_clavier_fiche_rien_a_la_relecture_passage_a_la_confirmation(
    db_session, async_session, test_client_factory
):
    from api.tests.mark.test_clavier_porte_la_fiche import FICHE, _monter, _noter
    from api.tests.mark.test_passation_clavier import _dit, _session, _texte, _vide

    etape = {"champs_etape": "nom", "qui_decide_du_passage": "collecte"}
    user, workflow = await _monter(db_session, async_session, FICHE, definition_clavier(etape))
    reponses = await _session(
        test_client_factory,
        user,
        workflow,
        [
            _vide(),
            _dit(_noter({"nom": "Lemaire"}, "n1"), _texte(RELECTURE)),
            _dit(_texte("Merci."), _texte("Voici la suite.")),
        ],
        ["je m'appelle Lemaire", "oui c'est ça"],
    )
    apres_la_question = reponses[0]["checkpoint"]["gathered_context"]
    assert "Suite" not in (apres_la_question.get("nodes_visited") or []), apres_la_question
    assert [p["resultat"] for p in apres_la_question.get(passage.CLE_PASSAGES) or []] == ["reportee_question"]
    fiche = reponses[-1]["checkpoint"]["gathered_context"]
    assert [p["resultat"] for p in fiche.get(passage.CLE_PASSAGES) or []] == ["reportee_question", "prise"], fiche
    assert "Suite" in (fiche.get("nodes_visited") or []), fiche


class FauxEnSuite(Faux):
    """Une réponse écrite d'avance par appel, dans l'ordre."""

    def __init__(self, *reponses):
        super().__init__()
        self.suite = list(reponses)

    async def __call__(self, service, systeme, message, schema=None):
        self.reponse = self.suite.pop(0) if len(self.suite) > 1 else self.suite[0]
        return await super().__call__(service, systeme, message, schema)


@pytest.mark.asyncio
async def test_clavier_arbitre_rien_apres_autre_chose_passage_sur_la_reponse(
    db_session, async_session, test_client_factory, monkeypatch
):
    from api.services.workflow.arbitre import RESTER
    from api.tests.mark.test_clavier_porte_la_fiche import FICHE, _monter
    from api.tests.mark.test_passation_clavier import _dit, _session, _texte, _vide

    faux = FauxEnSuite(_reponse(RESTER, 0.9), _reponse("suite", 0.95))
    monkeypatch.setattr("api.services.pipecat.greffier.interroger", faux)
    user, workflow = await _monter(
        db_session, async_session, FICHE, definition_clavier({"qui_decide_du_passage": "libre"})
    )
    reponses = await _session(
        test_client_factory,
        user,
        workflow,
        [_vide(), _dit(_texte(AUTRE_CHOSE)), _dit(_texte("Voici la suite."))],
        ["non, je ne veux pas", "non, c'est tout"],
    )
    apres_la_question = reponses[0]["checkpoint"]["gathered_context"]
    assert "Suite" not in (apres_la_question.get("nodes_visited") or []), apres_la_question
    assert [l["resultat"] for l in apres_la_question.get(arbitre_mod.CLE_ARBITRE) or []] == ["rien"], apres_la_question
    fiche = reponses[-1]["checkpoint"]["gathered_context"]
    assert [l["resultat"] for l in fiche.get(arbitre_mod.CLE_ARBITRE) or []] == ["rien", "prise"], fiche
    pris = [p for p in fiche.get(passage.CLE_PASSAGES) or [] if p.get("resultat") == "prise"]
    assert [(p["raison"], p["option"]) for p in pris] == [("arbitre", 2)], fiche
    assert "Suite" in (fiche.get("nodes_visited") or []), fiche
