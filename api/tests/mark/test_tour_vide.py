"""[.mark] Lot 3 de cloture-code-avant-migration (22/10/2026) : le tour vide de Pipecat 1.12.

Pipecat 1.12 relance par défaut un tour de l'appelant qui a coupé l'agent sans qu'un mot soit
transcrit (``EmptyUserTurnConfig``, message ``developer`` en anglais, le modèle fait répéter).
Chez nous le réglage ``relance_tour_vide`` est **éteint par défaut** : un agent qui n'allume rien se
comporte comme avant la montée (R1).

Ce que ces tests prouvent, par les vrais chemins :
- les paramètres de l'agrégateur de l'appel (``_construire_parametres_agregateur_utilisateur``) ne
  portent aucune relance quand le réglage est éteint, dans les deux paires (celle de Pipecat et
  celle de la relance après outil) ;
- allumé, un tour vide après une interruption relance le modèle **une fois**, pas deux de suite ;
- le message ``developer`` part tel quel en API Responses et devient ``user`` chez Mistral (qui
  refuse ce rôle), dans la requête réellement envoyée.
"""

from __future__ import annotations

import pytest
from pipecat.frames.frames import (
    BotStartedSpeakingFrame,
    Frame,
    LLMContextFrame,
    LLMFullResponseStartFrame,
    LLMRunFrame,
    TTSTextFrame,
    VADUserStartedSpeakingFrame,
    VADUserStoppedSpeakingFrame,
)
from pipecat.pipeline.pipeline import Pipeline
from pipecat.processors.aggregators.llm_context import LLMContext
from pipecat.processors.aggregators.llm_response_universal import (
    LLMAssistantAggregatorParams,
    LLMUserAggregatorParams,
)
from pipecat.processors.frame_processor import FrameDirection, FrameProcessor
from pipecat.tests.utils import SleepFrame, run_test
from pipecat.turns.empty_user_turn import EmptyUserTurnConfig
from pipecat.turns.user_start import (
    TranscriptionUserTurnStartStrategy,
    VADUserTurnStartStrategy,
)
from pipecat.turns.user_stop import SpeechTimeoutUserTurnStopStrategy
from pipecat.turns.user_turn_strategies import UserTurnStrategies
from pipecat.utils.text.base_text_aggregator import AggregationType

from api.services.pipecat.reglages_tour_de_parole import (
    collecter_reglages_tour_de_parole,
)
from api.services.pipecat.relance_apres_outil import paire_d_agregateurs
from api.services.pipecat.run_pipeline import (
    _construire_parametres_agregateur_utilisateur,
)

DELAI_FIN_DE_TOUR = 0.2


class _Compteur(FrameProcessor):
    """Compte les demandes au modèle que l'agrégateur de l'appelant pousse."""

    def __init__(self):
        super().__init__()
        self.demandes = 0

    async def process_frame(self, frame: Frame, direction: FrameDirection):
        await super().process_frame(frame, direction)
        if isinstance(frame, LLMContextFrame) and direction == FrameDirection.DOWNSTREAM:
            self.demandes += 1
        await self.push_frame(frame, direction)


def _parametres(run_configs: dict) -> LLMUserAggregatorParams:
    """Les paramètres que le pipeline de l'appel construit pour cet agent."""
    return _construire_parametres_agregateur_utilisateur(
        user_turn_strategies=UserTurnStrategies(
            start=[VADUserTurnStartStrategy(), TranscriptionUserTurnStartStrategy()],
            stop=[SpeechTimeoutUserTurnStopStrategy(user_speech_timeout=0.1)],
        ),
        should_interrupt=None,
        user_mute_strategies=[],
        user_turn_stop_timeout=DELAI_FIN_DE_TOUR,
        user_vad_analyzer=None,
        reglages=collecter_reglages_tour_de_parole(run_configs),
    )


def _l_agent_parle() -> list[Frame]:
    return [
        LLMRunFrame(),
        SleepFrame(),
        LLMFullResponseStartFrame(),
        BotStartedSpeakingFrame(),
        TTSTextFrame("Quelle est", aggregated_by=AggregationType.WORD),
        SleepFrame(),
    ]


def _tour_vide() -> list[Frame]:
    """De la voix, aucun mot transcrit, le tour fermé par le délai de fin de tour."""
    return [
        VADUserStartedSpeakingFrame(),
        VADUserStoppedSpeakingFrame(),
        SleepFrame(sleep=DELAI_FIN_DE_TOUR + 0.2),
    ]


async def _jouer(run_configs: dict, relance_apres_outil: bool, cadres: list[Frame]):
    contexte = LLMContext()
    appelant, agent = paire_d_agregateurs(
        contexte,
        user_params=_parametres(run_configs),
        assistant_params=LLMAssistantAggregatorParams(),
        relance=relance_apres_outil,
    )
    compteur = _Compteur()
    await run_test(Pipeline([appelant, compteur, agent]), frames_to_send=cadres)
    developpeur = [m for m in contexte.get_messages() if m.get("role") == "developer"]
    return developpeur, compteur.demandes


def test_pipecat_relance_par_defaut_et_nous_non():
    """La sentinelle de la montée : la paire de Pipecat relance si on ne lui dit rien ; nos
    paramètres, eux, ne portent aucune relance tant que le réglage est éteint."""
    assert isinstance(LLMUserAggregatorParams().empty_user_turn, EmptyUserTurnConfig)
    assert _parametres({}).empty_user_turn is None
    assert _parametres({"relance_tour_vide": None}).empty_user_turn is None
    assert _parametres({"relance_tour_vide": False}).empty_user_turn is None
    assert isinstance(_parametres({"relance_tour_vide": True}).empty_user_turn, EmptyUserTurnConfig)


@pytest.mark.asyncio
@pytest.mark.parametrize("relance_apres_outil", [False, True])
async def test_eteint_un_tour_vide_ne_relance_jamais(relance_apres_outil):
    developpeur, demandes = await _jouer({}, relance_apres_outil, [*_l_agent_parle(), *_tour_vide()])
    assert developpeur == []
    assert demandes == 1  # la seule demande est celle de la réplique de l'agent


@pytest.mark.asyncio
@pytest.mark.parametrize("relance_apres_outil", [False, True])
async def test_allume_un_tour_vide_relance_une_fois_pas_deux(relance_apres_outil):
    developpeur, demandes = await _jouer(
        {"relance_tour_vide": True},
        relance_apres_outil,
        [*_l_agent_parle(), *_tour_vide(), *_tour_vide()],
    )
    assert len(developpeur) == 1
    assert demandes == 2


def _contexte_avec_un_tour_vide() -> LLMContext:
    return LLMContext(
        messages=[
            {"role": "assistant", "content": "Quelle est votre adresse ?"},
            {"role": "developer", "content": EmptyUserTurnConfig().interrupted_prompt},
        ]
    )


def _requete_de(service, contexte: LLMContext) -> dict:
    """La requête que le service construit pour ce contexte, par son propre chemin (celui de
    ``get_chat_completions`` : adaptateur, conversion du rôle selon le fournisseur, paramètres)."""
    from pipecat.utils.types import assert_given

    invocation = service.get_llm_adapter().get_llm_invocation_params(
        contexte,
        system_instruction=assert_given(service._settings.system_instruction),
        convert_developer_to_user=not service.supports_developer_role,
    )
    return service.build_chat_completion_params(invocation)


def test_chez_mistral_le_message_developer_part_en_user():
    from types import SimpleNamespace

    from api.services.configuration.registry import MistralLLMConfiguration
    from api.services.pipecat.service_factory import create_llm_service

    service = create_llm_service(
        SimpleNamespace(llm=MistralLLMConfiguration(api_key="cle-de-test", model="mistral-small-latest"))
    )
    roles = [m["role"] for m in _requete_de(service, _contexte_avec_un_tour_vide())["messages"]]
    assert "developer" not in roles
    assert roles[-1] == "user"


def test_en_api_responses_le_message_developer_part_tel_quel():
    from api.services.pipecat.service_factory import create_llm_service
    from api.tests.mark.test_fournisseur_responses import _config

    service = create_llm_service(_config("responses"))
    invocation = service.get_llm_adapter().get_llm_invocation_params(_contexte_avec_un_tour_vide())
    entrees = service.build_chat_completion_params(invocation)["input"]
    assert {"role": "developer", "content": EmptyUserTurnConfig().interrupted_prompt} in entrees
