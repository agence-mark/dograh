"""[.mark] passages-fiables, sous-agent 10 (second rebanc, runs 67, 68, 74, 76, 77, 82) : la première réplique de l'étape
d'arrivée quand c'est LE CODE qui change d'étape.

Défaut : l'arbitre (ou l'option 2 de la collecte) passe vers l'étape d'arrivée AVANT la requête ; l'étape répond
directement mais sans la consigne de sa première réplique (que la porte parlée donne à l'agent qui prend sa porte lui-même) :
elle ne sait pas par quoi commencer et saute à l'étape suivante. Correction : la requête de l'étape d'arrivée porte, pour
ce tour seulement (notice d'un tour), la phrase d'arrivée du nœud, rendue comme dans le bloc « Tu passes à… ».

| Test | Ce qu'il prouve |
|---|---|
| arbitre, deux familles | conversation calquée sur le run 67 : la requête porte la phrase d'arrivée, une seule fois |
| sans première réplique | rien d'ajouté (requête identique à la base) |
| un tour seulement | la requête suivante ne la porte plus |
| rester | l'arbitre ne passe pas : aucune consigne |
| option 2, deux familles | même consigne ; sans première réplique, rien |
| option 1 avec relance | la notice du passage porte aussi la phrase d'arrivée ; sans première réplique, rien |
| agent qui prend sa porte | aucune notice, aucune consigne ajoutée |
| clavier | même consigne dans la requête de l'étape d'arrivée |
"""

from __future__ import annotations

import pytest
from pipecat.processors.aggregators.llm_context import NOT_GIVEN

from api.services.workflow import passage_sur_la_fiche as passage
from api.services.workflow.porte_parlee import PHRASE_D_ARRIVEE
from api.tests.mark.test_passages_fiables_agnostique import FAMILLES, _brancher, _requete
from api.tests.mark.test_passages_fiables_arbitre import Faux
from api.tests.mark.test_passages_fiables_avant_la_reponse import _choix, _la_personne_parle, _monter_l_arbitre
from api.tests.mark.test_passages_fiables_fiche import (
    GreffierFactice,
    _complete,
    _etape,
    _etape_option_2,
    _fin_de_reponse,
    graphe,
    monter,
)

# Conversation calquée sur le run 67 (étape d'entrée de l'entretien), sans donnée personnelle.
RUN_67 = [
    {"role": "assistant", "content": "Quand a eu lieu le dernier passage ?"},
    {"role": "user", "content": "L'an dernier, en octobre. J'ai déjà un contrat avec vous."},
]
PREMIERE = "Pour commencer, quel est votre nom de famille ?"
LIGNE = PHRASE_D_ARRIVEE.format(phrase=PREMIERE)


def _vues(requete) -> list[str]:
    """Les messages de la requête qui portent la phrase d'arrivée."""
    return [str(m.get("content")) for m in requete["messages"] if LIGNE in str(m.get("content"))]


def _avec_premiere(g, premiere: str | None):
    g.nodes["suite"].premiere_replique = premiere or ""
    return g


# --------------------------------------------------------------------------- #
# L'arbitre avant la requête
# --------------------------------------------------------------------------- #


@pytest.mark.asyncio
@pytest.mark.parametrize("famille", FAMILLES)
async def test_arbitre_la_requete_de_l_etape_d_arrivee_porte_la_premiere_replique_une_fois(famille, monkeypatch):
    harness, engine = await _monter_l_arbitre(monkeypatch, Faux(_choix("suite", 0.95)))
    try:
        engine.active_agent.workflow.nodes["suite"].premiere_replique = PREMIERE
        cerveau = await _brancher(engine, famille)
        _la_personne_parle(engine, RUN_67)
        await _requete(engine, cerveau, list(RUN_67))
        assert _etape(engine) == "suite"
        [requete] = cerveau.requetes
        assert "Tu es l'étape Suite." in requete["systeme"]
        assert len(_vues(requete)) == 1
        # Juste avant la dernière parole de la personne.
        assert LIGNE in str(requete["messages"][-2]["content"])
        assert requete["messages"][-1]["content"] == RUN_67[-1]["content"]
    finally:
        await harness.stop()


@pytest.mark.asyncio
@pytest.mark.parametrize("famille", FAMILLES)
async def test_arbitre_sans_premiere_replique_rien_n_est_ajoute(famille, monkeypatch):
    harness, engine = await _monter_l_arbitre(monkeypatch, Faux(_choix("suite", 0.95)))
    try:
        cerveau = await _brancher(engine, famille)
        _la_personne_parle(engine, RUN_67)
        await _requete(engine, cerveau, list(RUN_67))
        assert _etape(engine) == "suite"
        [requete] = cerveau.requetes
        assert requete["messages"] == RUN_67  # identique à la base
        assert engine._notice_de_passage is None
    finally:
        await harness.stop()


@pytest.mark.asyncio
async def test_la_consigne_ne_vaut_que_pour_un_tour(monkeypatch):
    harness, engine = await _monter_l_arbitre(monkeypatch, Faux(_choix("suite", 0.95)))
    try:
        engine.active_agent.workflow.nodes["suite"].premiere_replique = PREMIERE
        cerveau = await _brancher(engine, FAMILLES[0].values[0])
        _la_personne_parle(engine, RUN_67)
        await _requete(engine, cerveau, list(RUN_67))
        suite = [*RUN_67, {"role": "assistant", "content": "D'accord."}, {"role": "user", "content": "Lemaire."}]
        await _requete(engine, cerveau, suite)
        assert len(_vues(cerveau.requetes[0])) == 1
        assert _vues(cerveau.requetes[1]) == []
    finally:
        await harness.stop()


@pytest.mark.asyncio
async def test_arbitre_qui_laisse_rester_aucune_consigne(monkeypatch):
    harness, engine = await _monter_l_arbitre(monkeypatch, Faux(_choix("rester", 0.99)))
    try:
        engine.active_agent.workflow.nodes["suite"].premiere_replique = PREMIERE
        cerveau = await _brancher(engine, FAMILLES[0].values[0])
        _la_personne_parle(engine, RUN_67)
        await _requete(engine, cerveau, list(RUN_67))
        assert _etape(engine) == "etape" and cerveau.requetes[0]["messages"] == RUN_67
    finally:
        await harness.stop()


# --------------------------------------------------------------------------- #
# L'option 2 de la collecte
# --------------------------------------------------------------------------- #

MESSAGES_OPTION_2 = [
    {"role": "assistant", "content": "Quelle est la demande ?"},
    {"role": "user", "content": "une demande"},
]


@pytest.mark.asyncio
@pytest.mark.parametrize("famille", FAMILLES)
@pytest.mark.parametrize("premiere", [PREMIERE, None], ids=["avec", "sans"])
async def test_option_2_la_requete_porte_la_premiere_replique_si_elle_existe(famille, premiere):
    greffier = GreffierFactice()
    g = _avec_premiere(graphe(_etape_option_2()), premiere)
    harness = await monter(g, fiche={"nom": "Lemaire"}, greffier=greffier)
    try:
        engine = harness.engine
        cerveau = await _brancher(engine, famille)
        greffier.pendant = lambda: engine._gathered_context.update(objet="une demande")
        await _requete(engine, cerveau, list(MESSAGES_OPTION_2))
        assert _etape(engine) == "suite"
        [requete] = cerveau.requetes
        if premiere:
            assert len(_vues(requete)) == 1
        else:
            assert requete["messages"] == MESSAGES_OPTION_2
        engine.active_agent.queue_frame.assert_not_awaited()
    finally:
        await harness.stop()


# --------------------------------------------------------------------------- #
# L'option 1, avec relance
# --------------------------------------------------------------------------- #


class _Contexte:
    tools, tool_choice = NOT_GIVEN, NOT_GIVEN

    def get_messages(self):
        return [{"role": "user", "content": "Lemaire."}]


@pytest.mark.asyncio
@pytest.mark.parametrize("premiere", [PREMIERE, None], ids=["avec", "sans"])
async def test_option_1_la_notice_de_la_relance_porte_la_premiere_replique(premiere):
    harness = await monter(_avec_premiere(graphe(), premiere), fiche=_complete(), greffier=GreffierFactice())
    try:
        engine = harness.engine
        qui, _, _ = await _fin_de_reponse(engine)
        assert qui == "fiche" and _etape(engine) == "suite"
        engine.active_agent.queue_frame.assert_awaited()  # relance
        assert "Ce qui vient de se passer" in engine._notice_de_passage
        copie = passage.contexte_avec_la_notice(engine, _Contexte())
        assert copie is not None
        vus = [str(m.get("content")) for m in copie.get_messages()]
        assert sum(LIGNE in m for m in vus) == (1 if premiere else 0)
    finally:
        await harness.stop()


# --------------------------------------------------------------------------- #
# L'agent qui prend sa porte lui-même : inchangé
# --------------------------------------------------------------------------- #


@pytest.mark.asyncio
async def test_l_agent_qui_prend_sa_porte_lui_meme_n_a_aucune_notice():
    harness = await monter(_avec_premiere(graphe(), PREMIERE), greffier=GreffierFactice())
    try:
        engine = harness.engine
        assert await engine.prendre_porte_ecrite("suite", relancer=False) == "prise"
        assert _etape(engine) == "suite"
        assert getattr(engine, "_notice_de_passage", None) is None
        assert passage.contexte_avec_la_notice(engine, _Contexte()) is None
    finally:
        await harness.stop()


# --------------------------------------------------------------------------- #
# Le clavier
# --------------------------------------------------------------------------- #


@pytest.mark.asyncio
async def test_session_clavier_la_requete_de_l_etape_d_arrivee_porte_la_premiere_replique(
    db_session, async_session, test_client_factory, monkeypatch
):
    from api.tests.mark.test_clavier_porte_la_fiche import FICHE, _monter
    from api.tests.mark.test_passages_fiables_fiche import definition_clavier
    from api.tests.mark.test_passation_clavier import _dit, _session, _texte, _vide

    monkeypatch.setattr("api.services.pipecat.greffier.interroger", Faux(_choix("suite", 0.95)))
    definition = definition_clavier({"qui_decide_du_passage": "libre"})
    for noeud in definition["nodes"]:
        if noeud["id"] == "suite":
            noeud["data"]["premiere_replique"] = PREMIERE
    user, workflow = await _monter(db_session, async_session, FICHE, definition)
    modele = _dit(_texte("Pour commencer, quel est votre nom de famille ?"))
    vues: list[list[str]] = []
    origine = modele.get_chat_completions

    async def espion(context):
        vues.append([str(m.get("content")) for m in context.get_messages()])
        return await origine(context)

    modele.get_chat_completions = espion
    await _session(test_client_factory, user, workflow, [_vide(), modele], ["c'est une marque que vous ne suivez pas"])
    assert len(vues) == 1 and sum(LIGNE in m for m in vues[0]) == 1, vues
