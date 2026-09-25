"""[.mark] Plusieurs `noter_information` dans un tour ne font JAMAIS raccrocher à tort.

Remise à niveau sur l'amont `4e6cb22b`, décision E2 d'Evan (25/09/2026) et
collision 6 de l'analyse : le moniteur d'appel de l'amont raccroche quand l'agent
doit une réponse et que rien ne s'entend pendant `raccrochage_silence_agent_s`
(35 s par défaut). Or la fiche au fil de l'eau rend des résultats d'outil avec
`run_llm=False` (chantier fiche-au-fil-de-leau) : une note ne relance pas le
modèle, seule la dernière d'un tour le fait, ou aucune quand l'agent a déjà
posé sa question.

Joué contre le VRAI moniteur, avec un délai de 0,3 s au lieu de 35 : on attend
trois fois ce délai et on vérifie que l'appel n'a pas été raccroché, puis que
le moniteur rend la main à l'appelant (il attend de nouveau sa parole).

| Cas | Le tour |
|---|---|
| question + deux notes | l'agent parle et note deux fois, les deux notes ne relancent pas |
| deux notes seules | l'agent note deux fois sans parler ; la dernière relance, l'agent parle |
"""

import asyncio

import pytest
from pipecat.frames.frames import (
    FunctionCallFromLLM,
    FunctionCallResultFrame,
    FunctionCallResultProperties,
    FunctionCallsStartedFrame,
)
from pipecat.processors.frame_processor import FrameProcessor

from api.services.pipecat.call_monitor_processor import CallMonitorProcessor

DELAI_S = 0.3


def _moniteur():
    source = FrameProcessor()
    raccroches = []
    moniteur = CallMonitorProcessor(
        response_source=lambda: source,
        on_response_timeout=raccroches.append,
        on_user_idle=None,
        conversation_enabled=lambda: True,
        response_timeout=DELAI_S,
    )
    moniteur._active = True
    moniteur._sources[source] = lambda: True
    return moniteur, source, raccroches


def _notes(*identifiants):
    return FunctionCallsStartedFrame(
        function_calls=[
            FunctionCallFromLLM(
                function_name="noter_information",
                tool_call_id=i,
                arguments={"champ": "nom", "valeur": "Dupont"},
                context=None,
            )
            for i in identifiants
        ]
    )


def _resultat(identifiant, relance: bool):
    return FunctionCallResultFrame(
        function_name="noter_information",
        tool_call_id=identifiant,
        arguments={},
        result={"statut": "noté"},
        run_llm=None,
        properties=FunctionCallResultProperties(run_llm=relance),
    )


def _parler(moniteur, source, scope):
    moniteur.on_response_started(source, scope)
    moniteur.on_output(scope)


def _fin_de_parole(moniteur, scope):
    moniteur.on_playback_finished(scope)


@pytest.mark.asyncio
async def test_question_et_deux_notes_qui_ne_relancent_pas_ne_raccrochent_pas():
    moniteur, source, raccroches = _moniteur()
    moniteur.expect_response(source)  # l'appelant vient de parler
    _parler(moniteur, source, "s1")  # « Quelle est votre commune ? »
    moniteur._watch_tool(source, _notes("n1", "n2"))
    moniteur._watch_tool(source, _resultat("n1", relance=False))
    moniteur._watch_tool(source, _resultat("n2", relance=False))
    _fin_de_parole(moniteur, "s1")

    await asyncio.sleep(3 * DELAI_S)
    assert raccroches == [], "raccroché à tort après une question et deux notes"
    assert moniteur._response_watch is None and moniteur._waiting_for_user


@pytest.mark.asyncio
async def test_deux_notes_seules_puis_la_relance_ne_raccrochent_pas():
    moniteur, source, raccroches = _moniteur()
    moniteur.expect_response(source)
    _parler(moniteur, source, "g1")  # génération faite seulement d'appels d'outil
    moniteur._watch_tool(source, _notes("n1", "n2"))
    # Ordre d'arrivée défavorable : la note qui relance termine la PREMIÈRE.
    moniteur._watch_tool(source, _resultat("n2", relance=True))
    moniteur._watch_tool(source, _resultat("n1", relance=False))
    _fin_de_parole(moniteur, "g1")
    await asyncio.sleep(DELAI_S / 3)
    _parler(moniteur, source, "s2")  # la relance fait parler l'agent
    _fin_de_parole(moniteur, "s2")

    await asyncio.sleep(3 * DELAI_S)
    assert raccroches == [], "raccroché à tort après deux notes et la relance"
    assert moniteur._response_watch is None and moniteur._waiting_for_user


@pytest.mark.asyncio
async def test_temoin_un_agent_vraiment_muet_est_bien_raccroche():
    """Le témoin : sans lui, un moniteur qui ne raccroche jamais rendrait les
    deux tests ci-dessus verts."""
    moniteur, source, raccroches = _moniteur()
    moniteur.expect_response(source)
    await asyncio.sleep(3 * DELAI_S)
    assert raccroches == [source]
