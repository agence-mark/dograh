"""[.mark] Le moteur prend la porte écrite (plan porte-parlee, lot 4).

Plan `Labo-agent-vocal/plans/porte-parlee/`, D6, D7, D8/D16. Joué sur le vrai ``PipecatEngine`` :
seules la voix (``queue_text_message``), la relance (``queue_frame``) et le raccrochage
(``end_call_with_reason``) sont observées.

| Test | Ce qu'il prouve |
|---|---|
| porte connue | l'étape change, la requête d'après porte le prompt et les portes de l'étape d'arrivée |
| porte inconnue | rien ne change, rien n'est dit, jamais d'exception |
| le code ne choisit pas | une porte d'une AUTRE étape n'est jamais prise |
| transition | écrite et pas encore dite : jouée ; déjà dite par le processeur : jamais deux fois |
| étape de fin | D7 : aucune relance, raccrochage quand la phrase en cours a été jouée |
| relance | une porte seule fait reparler le modèle dans la nouvelle étape |
| panne | une erreur pendant le changement d'étape rend « echec », l'appel continue |
"""

import asyncio
from unittest.mock import AsyncMock

import pytest
from pipecat.frames.frames import LLMRunFrame

from api.services.pipecat.speech_playback import PlaybackOutcome
from api.services.workflow.fiche_au_fil_de_leau import (
    CLE_MODE,
    CLE_PORTES_DANS_LA_REPONSE,
    MODE_POST_SCRIPTUM,
    ReglagesFiche,
)
from api.services.workflow.pipecat_engine import PipecatEngine
from api.tests.mark.test_fiche_montree import _contexte, _mistral
from api.tests.mark.test_outil_noter import CONFIG_ALLUMEE
from api.tests.mark.test_porte_parlee_consigne import _definition, _graphe


async def _moteur(etape: str = "start", definition: dict | None = None):
    graphe = _graphe(definition)
    engine = PipecatEngine(
        llm=_mistral(),
        context=_contexte(),
        workflow=graphe,
        call_context_vars={"magasin": "Le Comptoir"},
        workflow_run_id=1,
        fiche=ReglagesFiche.depuis(
            {
                **CONFIG_ALLUMEE,
                CLE_MODE: MODE_POST_SCRIPTUM,
                CLE_PORTES_DANS_LA_REPONSE: True,
            }
        ),
    )
    agent = engine.active_agent
    await engine._prepare_node(agent, graphe.nodes[etape], apply_settings=False)
    agent.current_node = graphe.nodes[etape]
    engine.queue_text_message = AsyncMock(return_value=True)
    engine.end_call_with_reason = AsyncMock()
    agent.queue_frame = AsyncMock()
    return engine


@pytest.mark.asyncio
async def test_une_porte_connue_change_d_etape_et_la_requete_suit():
    engine = await _moteur("start")
    etat = await engine.prendre_porte_ecrite("vers_etape")
    assert etat == "prise"
    agent = engine.active_agent
    assert agent.current_node.id == "etape"
    # Le prompt de la requête d'après est celui de l'étape d'arrivée, avec ses portes.
    assert "Tu poses la question." in agent.system_prompt
    assert "- vers_fin → étape End : Quand c'est fini." in agent.system_prompt
    assert "- vers_etape →" not in agent.system_prompt
    agent.queue_frame.assert_not_awaited()
    engine.queue_text_message.assert_not_awaited()
    engine.end_call_with_reason.assert_not_awaited()


@pytest.mark.asyncio
async def test_une_porte_inconnue_ne_change_rien():
    engine = await _moteur("start")
    assert await engine.prendre_porte_ecrite("porte_inventee") == "inconnue"
    assert engine.active_agent.current_node.id == "start"


@pytest.mark.asyncio
async def test_une_porte_d_une_autre_etape_n_est_jamais_prise():
    """« vers_fin » existe dans le graphe, mais pas à l'accueil : le code ne choisit pas."""
    engine = await _moteur("start")
    assert await engine.prendre_porte_ecrite("vers_fin") == "inconnue"
    assert engine.active_agent.current_node.id == "start"


def _avec_transition(texte: str) -> dict:
    definition = _definition()
    for arete in definition["edges"]:
        if arete["id"] == "start-etape":
            arete["data"]["transition_speech"] = texte
    return definition


@pytest.mark.asyncio
async def test_la_transition_ecrite_est_dite_une_seule_fois():
    definition = _avec_transition("Un petit instant.")
    engine = await _moteur("start", definition)
    assert engine.phrase_de_transition_ecrite("vers_etape") == "Un petit instant."
    await engine.prendre_porte_ecrite("vers_etape", transition_dite=False)
    engine.queue_text_message.assert_awaited_once_with(
        "Un petit instant.", mute_user=True
    )

    engine = await _moteur("start", definition)
    await engine.prendre_porte_ecrite("vers_etape", transition_dite=True)
    engine.queue_text_message.assert_not_awaited()


@pytest.mark.asyncio
async def test_vers_une_etape_de_fin_la_phrase_dite_clot_puis_raccroche():
    engine = await _moteur("etape")
    reponse = "reponse-en-cours"
    etat = await engine.prendre_porte_ecrite("vers_fin", reponse=reponse)
    assert etat == "prise"
    assert engine.active_agent.current_node.is_end
    # Aucune relance : la phrase dite EST la phrase de fin (D7).
    engine.active_agent.queue_frame.assert_not_awaited()
    await asyncio.sleep(0.05)
    engine.end_call_with_reason.assert_not_awaited()
    # La réponse en cours finit d'être jouée : on raccroche.
    engine.speech_playback.pending[reponse].finish(PlaybackOutcome.PLAYED)
    await asyncio.sleep(0.05)
    engine.end_call_with_reason.assert_awaited_once()


@pytest.mark.asyncio
async def test_une_porte_seule_fait_reparler_le_modele_dans_la_nouvelle_etape():
    engine = await _moteur("start")
    await engine.prendre_porte_ecrite("vers_etape", relancer=True)
    assert engine.active_agent.current_node.id == "etape"
    (appel,) = engine.active_agent.queue_frame.await_args_list
    assert isinstance(appel.args[0], LLMRunFrame)


@pytest.mark.asyncio
async def test_une_panne_pendant_le_changement_rend_echec_sans_lever():
    engine = await _moteur("start")
    engine.set_node = AsyncMock(side_effect=RuntimeError("panne"))
    assert await engine.prendre_porte_ecrite("vers_etape") == "echec"


@pytest.mark.asyncio
async def test_hors_etape_ou_depuis_une_fin_rien():
    definition = _definition()
    engine = await _moteur("end", definition)
    assert await engine.prendre_porte_ecrite("vers_fin") == "inconnue"
