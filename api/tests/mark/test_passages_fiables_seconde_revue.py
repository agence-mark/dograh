"""[.mark] passages-fiables : les corrections de la seconde revue `revue-archi-secu` (rouge avant, vert après).

| Test | Ce qu'il prouve |
|---|---|
| 1 une porte par parole | première réponse de l'étape d'arrivée = outil seul, puis relance qui parle : aucune seconde porte |
| 2 attente cumulée | option 2 puis arbitre lents : l'attente totale reste dans le délai de l'étape |
| 3 anticipée | une requête anticipée traverse `preparer_la_requete` sans rien attendre, sans changer d'étape |
| 4 tri | filtre par statut, borne de lecture atteinte : pas de suite promise, recherche dite tronquée |
| 5 relance de silence | la consigne de relance (et l'au revoir) n'est jamais une parole : ni arbitre, ni passage |
| 6 interruption | annulée pendant l'attente de l'arbitre : annulation propagée, aucun passage, rien d'appliqué plus tard |
"""

from __future__ import annotations

import asyncio
import time

import pytest
from pipecat.frames.frames import LLMContextFrame
from pipecat.processors.aggregators.llm_context import LLMContext

from api.services.groupe.passations import ConsigneDuCode, est_la_note_de_passation
from api.services.pipecat.avant_la_requete import preparer_la_requete
from api.services.workflow import decideur_de_fin_de_tour as decideur
from api.services.workflow import passage_sur_la_fiche as passage
from api.services.workflow.arbitre import ArbitreDuPassage
from api.tests.mark.test_passages_fiables_agnostique import FAMILLES, _brancher, _requete
from api.tests.mark.test_passages_fiables_arbitre import Faux
from api.tests.mark.test_passages_fiables_avant_la_reponse import (
    E5,
    _choix,
    _la_personne_parle,
    _lignes,
    _monter_l_arbitre,
)
from api.tests.mark.test_passages_fiables_fiche import GreffierFactice, _etape, _etape_option_2


def _graphe_suite_complete():
    from api.services.workflow.dto import ReactFlowDTO
    from api.services.workflow.workflow_graph import WorkflowGraph
    from api.tests.mark.test_passages_fiables_fiche import _arete, _noeud

    return WorkflowGraph(
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


# --------------------------------------------------------------------------- #
# 1. Une seule porte par parole, même quand la première réponse n'est qu'un appel d'outil
# --------------------------------------------------------------------------- #


@pytest.mark.asyncio
async def test_1_outil_seul_puis_relance_qui_parle_aucune_seconde_porte(monkeypatch):
    from api.tests.mark.test_passages_fiables_fiche import monter

    monkeypatch.setattr("api.services.pipecat.greffier.interroger", Faux(_choix("suite", 0.99)))
    harness = await monter(_graphe_suite_complete(), fiche={"nom": "Lemaire"}, greffier=GreffierFactice())
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
        # Première réponse de l'étape d'arrivée : un appel d'outil, sans phrase. Aucune porte.
        assert await decideur.decider(engine, "", engine.etat_pour_le_filet(), jeton) is None
        # La relance sur le résultat de l'outil parle : la fiche (suite complète) ne prend pas une seconde porte.
        assert await decideur.decider(engine, "Voilà, c'est noté.", engine.etat_pour_le_filet(), jeton) is None
        assert _etape(engine) == "suite"
    finally:
        await harness.stop()


# --------------------------------------------------------------------------- #
# 2. L'attente totale tient dans le délai de l'étape
# --------------------------------------------------------------------------- #


class GreffierLent:
    """Le greffier met ``duree`` à rattraper la parole et n'écrit rien : l'option 2 ne trouve aucune porte."""

    def __init__(self, duree):
        self.duree, self.appels = duree, []

    async def rattraper(self, delai):
        self.appels.append(delai)
        await asyncio.sleep(min(self.duree, delai))
        return True


@pytest.mark.asyncio
async def test_2_option_2_puis_arbitre_lents_attente_totale_dans_le_delai(monkeypatch):
    etape = _etape_option_2(delai_du_passage=0.5, arbitre=True)
    faux = Faux(_choix("suite", 0.99), retard=2.0)
    harness, engine = await _monter_l_arbitre(monkeypatch, faux, etape, fiche={"nom": "Lemaire"})
    try:
        engine.greffier = GreffierLent(0.35)
        cerveau = await _brancher(engine, FAMILLES[0].values[0])
        _la_personne_parle(engine, E5)
        debut = time.monotonic()
        await _requete(engine, cerveau, list(E5))
        total = time.monotonic() - debut
        assert engine.greffier.appels, "l'option 2 devait attendre le greffier"
        assert total < 0.5 + 0.25, f"attente cumulée : {total:.2f} s pour un délai de 0,5 s"
        assert _etape(engine) == "etape"
    finally:
        await harness.stop()


# --------------------------------------------------------------------------- #
# 3. Une requête anticipée traverse `preparer_la_requete` sans rien attendre ni changer d'étape
# --------------------------------------------------------------------------- #


@pytest.mark.asyncio
async def test_3_une_requete_anticipee_ne_change_jamais_d_etape(monkeypatch):
    faux = Faux(_choix("suite", 0.99))
    harness, engine = await _monter_l_arbitre(monkeypatch, faux, _etape_option_2(arbitre=True), fiche={"nom": "Lemaire"})
    try:
        greffier = GreffierFactice()
        greffier.pendant = lambda: engine._gathered_context.update(objet="une demande")
        engine.greffier = greffier
        await _brancher(engine, FAMILLES[0].values[0])
        _la_personne_parle(engine, E5)
        trame = LLMContextFrame(LLMContext(messages=list(E5)), speculation=True)
        rendue = await preparer_la_requete(engine, engine.active_agent.llm, trame)
        assert rendue is trame
        assert _etape(engine) == "etape" and greffier.appels == []
        assert passage.CLE_PASSAGES not in engine._gathered_context and _lignes(engine) == []
        # La même requête, non anticipée : elle, elle passe (preuve que l'anticipée a bien été laissée telle quelle).
        reelle = LLMContextFrame(LLMContext(messages=list(E5)))
        await preparer_la_requete(engine, engine.active_agent.llm, reelle)
        assert _etape(engine) == "suite"
    finally:
        await harness.stop()


# --------------------------------------------------------------------------- #
# 4. Tri : la borne de lecture atteinte
# --------------------------------------------------------------------------- #


@pytest.mark.asyncio
async def test_4_borne_de_lecture_atteinte_pas_de_suite_promise(db_session, async_session, test_client_factory, monkeypatch):
    from api.tests.mark.test_passages_fiables_signalements_et_alertes import FICHE, _monter, _run

    monkeypatch.setattr("api.routes.tri.MAX_PAGES_DE_RUNS_LUES", 1)
    user, workflow = await _monter(db_session, async_session, dict(FICHE))
    avec = {"signalements": [{"source": "agent", "motif": "m", "categorie": "autre"}]}
    await _run(db_session, async_session, user, workflow, avec, annotations={"tri": {"agent:0": {"statut": "résolu"}}})
    for _ in range(55):  # plus récents que le « résolu » : la borne (1 page de 50 runs) ne l'atteint jamais
        await _run(db_session, async_session, user, workflow, avec)
    async with test_client_factory(user) as client:
        page = (await client.get("/api/v1/tri", params={"statut": "résolu"})).json()
    assert page["lignes"] == []
    assert page["a_une_suite"] is False
    assert page["recherche_tronquee"] is True


# --------------------------------------------------------------------------- #
# 5. La relance de silence par le modèle n'est pas une parole
# --------------------------------------------------------------------------- #


@pytest.mark.asyncio
async def test_5_les_consignes_de_silence_sont_marquees_du_code():
    from api.services.workflow.pipecat_engine_callbacks import handle_user_idle
    from api.tests.mark.test_relance_inactivite import _MoteurFactice

    messages = []

    class Agregateur:
        async def push_frame(self, frame):
            messages.extend(frame.messages)

    moteur = _MoteurFactice({})
    for tentative in (1, 2):
        await handle_user_idle(moteur, Agregateur(), tentative)
    assert len(messages) == 2
    assert all(isinstance(m["content"], ConsigneDuCode) and est_la_note_de_passation(m) for m in messages)
    assert all(m["role"] == "user" for m in messages)  # même message envoyé au fournisseur qu'avant


@pytest.mark.asyncio
async def test_5_la_consigne_de_silence_ne_lance_pas_l_arbitre_et_n_est_pas_une_parole(monkeypatch):
    faux = Faux(_choix("suite", 0.99))
    harness, engine = await _monter_l_arbitre(monkeypatch, faux)
    try:
        consigne = {"role": "user", "content": ConsigneDuCode("The user has been quiet. Ask if they are still there.")}
        engine.context.add_message(dict(consigne))
        await asyncio.sleep(0.1)
        assert faux.requetes == [] and _lignes(engine) == []
        assert passage._derniere_parole_de_la_personne(LLMContext(messages=[E5[0], consigne])) is False
        # Une vraie parole reste une parole (la distinction ne casse pas le cas courant).
        assert passage._derniere_parole_de_la_personne(LLMContext(messages=list(E5))) is True
        # Et la requête qui suit la consigne ne passe aucune porte.
        cerveau = await _brancher(engine, FAMILLES[0].values[0])
        await _requete(engine, cerveau, [*E5, {"role": "assistant", "content": "Oui ?"}, consigne])
        assert _etape(engine) == "etape" and faux.requetes == []
    finally:
        await harness.stop()


# --------------------------------------------------------------------------- #
# 6. Une interruption pendant l'attente de l'arbitre
# --------------------------------------------------------------------------- #


@pytest.mark.asyncio
async def test_6_interruption_pendant_l_attente_de_l_arbitre_rien_n_est_applique(monkeypatch):
    faux = Faux(_choix("suite", 0.99), retard=0.5)
    harness, engine = await _monter_l_arbitre(monkeypatch, faux)
    try:
        _la_personne_parle(engine, E5)
        await asyncio.sleep(0.05)  # la demande de l'arbitre est partie
        trame = LLMContextFrame(LLMContext(messages=list(E5)))
        tache = asyncio.ensure_future(preparer_la_requete(engine, engine.active_agent.llm, trame))
        await asyncio.sleep(0.1)  # elle attend l'arbitre
        assert not tache.done()
        tache.cancel()
        with pytest.raises(asyncio.CancelledError):
            await tache
        await asyncio.sleep(0.8)  # la décision arrive après coup : rien ne doit s'appliquer
        assert _etape(engine) == "etape"
        assert passage.CLE_PASSAGES not in engine._gathered_context
        assert all(ligne.get("resultat") != "prise" for ligne in _lignes(engine))
        engine.active_agent.queue_frame.assert_not_awaited()
    finally:
        await harness.stop()
