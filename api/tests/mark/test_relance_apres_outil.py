"""[.mark] La relance du modèle après un outil (chantier langwatch-et-fenetre-du-run, lot 4, L14 ;
ticket Pipecat 5960).

Les cas du ticket, joués sur les deux agrégateurs : un résultat qui arrive pendant le tour de
l'appelant est GARDÉ, puis envoyé une seule fois quand le tour est fermé et écrit ; un résultat hors
tour part tout de suite ; une autre demande au modèle entre-temps annule la relance gardée (jamais
deux réponses) ; la fin de parole de l'agent pendant un nouveau tour ne lance rien. Et : l'option est
éteinte par défaut (paire de Pipecat), et les membres privés de Pipecat sur lesquels le correctif
repose existent encore (ce test casse à la montée de version qui les retire).
"""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest
from pipecat.frames.frames import BotStoppedSpeakingFrame
from pipecat.processors.aggregators.llm_context import LLMContext
from pipecat.processors.aggregators.llm_response_universal import (
    LLMAssistantAggregator,
    LLMAssistantAggregatorParams,
    LLMUserAggregator,
    LLMUserAggregatorParams,
)
from pipecat.processors.frame_processor import FrameDirection

from api.services.pipecat import relance_apres_outil as relance
from api.services.pipecat.relance_apres_outil import (
    AgregateurAgentRelance,
    AgregateurAppelantRelance,
    paire_d_agregateurs,
    relance_allumee,
)


def _paire(allumee=True):
    return paire_d_agregateurs(
        LLMContext(),
        user_params=LLMUserAggregatorParams(),
        assistant_params=LLMAssistantAggregatorParams(),
        relance=allumee,
    )


@pytest.fixture
def banc():
    """La paire .mark, avec les envois au modèle (ceux de Pipecat) relevés au lieu d'être faits."""
    envois_agent, envois_appelant = AsyncMock(), AsyncMock()
    with (
        patch.object(LLMAssistantAggregator, "push_context_frame", envois_agent),
        patch.object(LLMUserAggregator, "push_context_frame", envois_appelant),
    ):
        appelant, agent = _paire()
        agent.has_queued_frame = lambda _type: False
        yield appelant, agent, envois_agent, envois_appelant


def _ouvrir_le_tour(appelant):
    appelant._user_turn_controller._user_turn = True


def _fermer_le_tour(appelant):
    appelant._user_turn_controller._user_turn = False


async def test_un_resultat_pendant_le_tour_est_garde_puis_envoye_une_fois_a_sa_fermeture(
    banc,
):
    appelant, agent, envois, _ = banc
    _ouvrir_le_tour(appelant)
    await agent._tour_ouvert(appelant, None)
    await agent._maybe_push_context_after_function_result()
    envois.assert_not_awaited()  # Pipecat l'aurait perdu ici : c'est le défaut 5960

    _fermer_le_tour(appelant)  # la fin de tour arrive, ses mots pas encore écrits
    await agent._maybe_push_context_after_function_result()
    envois.assert_not_awaited()

    await agent._tour_ferme(appelant, None, None)
    envois.assert_awaited_once()
    assert envois.await_args.args[-1] == FrameDirection.UPSTREAM
    await agent._tour_ferme(appelant, None, None)
    envois.assert_awaited_once()  # jamais deux fois


async def test_un_resultat_hors_tour_part_tout_de_suite(banc):
    _appelant, agent, envois, _ = banc
    await agent._maybe_push_context_after_function_result()
    envois.assert_awaited_once()


async def test_une_autre_demande_au_modele_annule_la_relance_gardee(banc):
    appelant, agent, envois_agent, envois_appelant = banc
    _ouvrir_le_tour(appelant)
    await agent._tour_ouvert(appelant, None)
    await agent._maybe_push_context_after_function_result()
    # L'appelant finit sa phrase : SA demande au modèle voit déjà le résultat.
    await appelant.push_context_frame()
    envois_appelant.assert_awaited_once()
    _fermer_le_tour(appelant)
    await agent._tour_ferme(appelant, None, None)
    envois_agent.assert_not_awaited()


async def test_la_fin_de_parole_de_l_agent_pendant_un_nouveau_tour_ne_relance_rien(
    banc,
):
    appelant, agent, _, _ = banc
    agent._push_context_on_bot_stopped_speaking = True
    _ouvrir_le_tour(appelant)
    with patch.object(LLMAssistantAggregator, "process_frame", AsyncMock()) as suite:
        await agent.process_frame(BotStoppedSpeakingFrame(), FrameDirection.DOWNSTREAM)
    assert agent._push_context_on_bot_stopped_speaking is False
    suite.assert_awaited_once()


def test_la_copie_tardive_du_tour_est_toujours_fausse():
    _appelant, agent = _paire()
    agent._user_speaking = True
    assert agent._user_speaking is False


# --- L'option, et la paire de Pipecat par défaut -------------------------------------------------


def test_eteinte_par_defaut_et_lue_sans_jamais_casser_l_appel():
    assert relance_allumee(None) is False
    assert relance_allumee({}) is False
    assert relance_allumee({"relance_apres_outil": None}) is False
    assert relance_allumee({"relance_apres_outil": True}) is True
    assert relance_allumee({"relance_apres_outil": "pas un booléen"}) is False


def test_eteinte_la_paire_est_celle_de_pipecat():
    appelant, agent = _paire(allumee=False)
    assert type(appelant) is LLMUserAggregator
    assert type(agent) is LLMAssistantAggregator


def test_allumee_la_paire_est_la_notre_et_se_connait():
    appelant, agent = _paire(allumee=True)
    assert isinstance(appelant, AgregateurAppelantRelance)
    assert isinstance(agent, AgregateurAgentRelance)
    assert appelant.assistant is agent
    assert agent._paired_user_aggregator is appelant


# --- Garde de montée de version ------------------------------------------------------------------


def test_les_membres_prives_de_pipecat_utilises_existent_encore():
    """Le correctif lit des membres privés de Pipecat 49ba358f. Si une montée de version les
    retire ou les renomme, ce test casse AVANT qu'un appel ne se taise en silence."""
    appelant = LLMUserAggregator(LLMContext(), params=LLMUserAggregatorParams())
    agent = LLMAssistantAggregator(
        LLMContext(),
        params=LLMAssistantAggregatorParams(),
        _paired_user_aggregator=appelant,
    )
    assert isinstance(appelant._user_turn_controller._user_turn, bool)
    assert agent._paired_user_aggregator is appelant
    assert hasattr(agent, "_push_context_on_bot_stopped_speaking")
    assert hasattr(agent, "_user_speaking")
    assert callable(agent._maybe_push_context_after_function_result)
    for evenement in ("on_user_turn_started", "on_user_turn_stopped"):
        assert evenement in appelant._event_handlers
    assert relance.CLE_INTERRUPTEUR == "relance_apres_outil"


# --- La réponse spéculative (revue du 05/10, point 9) ------------------------------------------


@pytest.fixture
def speculation():
    """Les deux méthodes de Pipecat que l'agrégateur de l'appelant enveloppe, neutralisées."""
    with (
        patch.object(LLMUserAggregator, "_run_speculative_inference", AsyncMock()),
        patch.object(LLMUserAggregator, "_on_user_turn_stopped", AsyncMock()),
    ):
        yield


def _fin_de_tour(confirme: bool):
    from types import SimpleNamespace

    return SimpleNamespace(
        confirms_speculation=confirme, enable_user_speaking_frames=True
    )


async def _garder_une_relance(appelant, agent):
    _ouvrir_le_tour(appelant)
    await agent._tour_ouvert(appelant, None)
    await agent._maybe_push_context_after_function_result()


async def test_une_speculation_confirmee_apres_le_resultat_solde_la_relance(
    banc, speculation
):
    appelant, agent, envois, _ = banc
    await _garder_une_relance(appelant, agent)
    await appelant._run_speculative_inference(object())  # elle voit le résultat
    await appelant._on_user_turn_stopped(None, None, _fin_de_tour(confirme=True))
    _fermer_le_tour(appelant)
    await agent._tour_ferme(appelant, None, None)
    envois.assert_not_awaited()  # la réponse spéculative EST la réponse : pas de seconde


async def test_une_speculation_jetee_laisse_la_relance_due(banc, speculation):
    appelant, agent, envois, _ = banc
    await _garder_une_relance(appelant, agent)
    await appelant._run_speculative_inference(object())
    await appelant._on_user_turn_stopped(None, None, _fin_de_tour(confirme=False))
    _fermer_le_tour(appelant)
    await agent._tour_ferme(appelant, None, None)
    envois.assert_awaited_once()


async def test_une_speculation_lancee_avant_le_resultat_ne_solde_rien(
    banc, speculation
):
    appelant, agent, envois, _ = banc
    _ouvrir_le_tour(appelant)
    await agent._tour_ouvert(appelant, None)
    await appelant._run_speculative_inference(object())  # sans le résultat de l'outil
    await agent._maybe_push_context_after_function_result()
    await appelant._on_user_turn_stopped(None, None, _fin_de_tour(confirme=True))
    _fermer_le_tour(appelant)
    await agent._tour_ferme(appelant, None, None)
    envois.assert_awaited_once()


def test_les_membres_de_la_speculation_existent_encore():
    import dataclasses

    from pipecat.turns.user_stop.base_user_turn_stop_strategy import (
        UserTurnStoppedParams,
    )

    assert callable(LLMUserAggregator._run_speculative_inference)
    assert callable(LLMUserAggregator._on_user_turn_stopped)
    champs = {c.name for c in dataclasses.fields(UserTurnStoppedParams)}
    assert "confirms_speculation" in champs
