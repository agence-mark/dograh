"""[.mark] RA-B, R4 (a) : une condition sur la fiche FERME la porte au modèle (audit 01 A2, 🔴 2).

Ces tests passent par le VRAI moteur (banc fendu de ``test_agent_transfer.py``, comme les passages sur la fiche) : on
retrouve la fonction de porte que le moteur a posée sur le cerveau et on l'appelle comme le fait le modèle.
"""

from unittest.mock import AsyncMock, MagicMock

import pytest

from api.services.workflow import passage_sur_la_fiche as passage
from api.tests.mark.test_passages_fiables_fiche import graphe, monter
from pipecat.services.llm_service import FunctionCallParams

pytestmark = pytest.mark.asyncio


async def _appeler_la_porte(engine, nom: str) -> dict:
    """Ce que fait le modèle : appeler la fonction de la porte ``nom``. Rend le résultat qu'il reçoit."""
    entree = engine.active_agent.llm._functions[nom]
    retour = AsyncMock()
    await entree.handler(
        FunctionCallParams(
            function_name=nom, tool_call_id="t1", arguments={}, llm=MagicMock(), context=MagicMock(), pipeline_worker=MagicMock(), result_callback=retour
        )
    )
    retour.assert_awaited_once()
    return retour.await_args.args[0]


async def test_une_condition_fausse_ferme_la_porte_au_modele():
    # Étape réglée « la fiche décide » ; la porte « Refus » exige objet = refusé ; la fiche dit autre chose.
    harness = await monter(graphe(), fiche={"nom": "Lemaire", "objet": "une demande"})
    try:
        engine = harness.engine
        resultat = await _appeler_la_porte(engine, "refus")
        assert engine.active_agent.current_node.id == "etape", "la porte fermée ne doit pas être prise"
        assert resultat["status"] != "done"
        assert resultat["status"] == "closed"
        trace = engine._gathered_context[passage.CLE_PASSAGES]
        assert trace[-1]["resultat"] == "fermee" and trace[-1]["porte"] == "refus"
    finally:
        await harness.stop()


async def test_une_condition_vraie_laisse_la_porte_ouverte_au_modele():
    harness = await monter(graphe(), fiche={"nom": "Lemaire", "objet": "refusé"})
    try:
        engine = harness.engine
        resultat = await _appeler_la_porte(engine, "refus")
        assert engine.active_agent.current_node.id == "refus"
        assert resultat["status"] == "done"
    finally:
        await harness.stop()


async def test_etape_en_mode_agent_aucune_condition_lue():
    # Comportement d'avant, à l'octet : sur une étape ``agent`` la condition ne ferme rien.
    harness = await monter(graphe({"qui_decide_du_passage": "agent", "champs_etape": "nom,objet"}), fiche={})
    try:
        engine = harness.engine
        resultat = await _appeler_la_porte(engine, "refus")
        assert engine.active_agent.current_node.id == "refus"
        assert resultat["status"] == "done"
    finally:
        await harness.stop()


async def test_porte_sans_condition_jamais_fermee_meme_fiche_incomplete():
    # La porte « Suite » (implicite en collecte) reste au modèle : seule une condition ÉCRITE ferme.
    harness = await monter(graphe(), fiche={})
    try:
        engine = harness.engine
        resultat = await _appeler_la_porte(engine, "suite")
        assert engine.active_agent.current_node.id == "suite"
        assert resultat["status"] == "done"
    finally:
        await harness.stop()


async def test_la_porte_ecrite_dans_la_reponse_est_fermee_aussi():
    # Le chemin « porte écrite » (post-scriptum) obéit à la même condition que l'appel de fonction.
    harness = await monter(graphe(), fiche={"nom": "Lemaire", "objet": "une demande"})
    try:
        engine = harness.engine
        etat = await engine.prendre_porte_ecrite("refus")
        assert etat == "fermee"
        assert engine.active_agent.current_node.id == "etape"
    finally:
        await harness.stop()
