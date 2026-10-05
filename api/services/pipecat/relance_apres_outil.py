"""[.mark] La relance du modèle après un outil, même quand le résultat devance la fin de tour
(chantier langwatch-et-fenetre-du-run, lot 4, L14, L15 ; ticket Pipecat 5960).

Le défaut : avec un outil local rapide (``noter_information``, une porte), le résultat peut arriver
à l'agrégateur de l'agent AVANT le ``UserStoppedSpeakingFrame`` du même tour. ``_user_speaking`` y
est encore vrai, la relance du modèle est laissée « à la fin du tour »… qui est déjà passée, et
rien ne la reprend : l'agent se tait jusqu'à ce que l'appelant reparle. Preuve sur un vrai appel :
run 964, tour 2 (détecteur de la fenêtre du run, L6).

Le correctif est celui publié dans le ticket (https://github.com/pipecat-ai/pipecat/issues/5960),
repris tel quel dans sa logique :

1. le tour se lit dans l'agrégateur de l'appelant (``_user_turn_controller._user_turn``), et reste
   « en cours » après sa fermeture tant que ``on_user_turn_stopped`` n'a pas écrit ses mots ;
   ``_user_speaking`` vaut toujours faux, pour que les vérifications de Pipecat passent par la nôtre ;
2. une relance qui doit attendre est **due**, au lieu d'être perdue ;
3. elle part à la fermeture du tour, une fois ses mots écrits, si aucun nouveau tour n'est ouvert ;
4. toute autre demande au modèle l'annule (elle voit déjà le résultat) : jamais deux réponses ;
5. à la fin de parole de l'agent, si un tour est en cours, la relance différée attend ce tour.

⛔ Le sous-module Pipecat n'est jamais modifié : deux sous-classes, utilisées seulement quand
l'agent a l'option allumée (``relance_apres_outil``, éteinte par défaut, à l'écran), en mode
cascade (le ticket n'a pas été éprouvé en temps réel). Elles reposent sur des membres privés de
Pipecat ``49ba358f`` : un test les vérifie à chaque montée de version. À retirer quand l'amont
corrige le ticket.
"""

from __future__ import annotations

from loguru import logger

from api.schemas.workflow_configurations import WorkflowConfigurationDefaults
from pipecat.frames.frames import BotStoppedSpeakingFrame, Frame
from pipecat.processors.aggregators.llm_context import LLMContext
from pipecat.processors.aggregators.llm_response_universal import (
    LLMAssistantAggregator,
    LLMAssistantAggregatorParams,
    LLMContextAggregatorPair,
    LLMUserAggregator,
    LLMUserAggregatorParams,
)
from pipecat.processors.frame_processor import FrameDirection

CLE_INTERRUPTEUR = "relance_apres_outil"


class AgregateurAppelantRelance(LLMUserAggregator):
    """Prévient l'agrégateur de l'agent à chaque demande au modèle (règle 4).

    Y compris la réponse SPÉCULATIVE (revue du 05/10, point 9) : Pipecat la lance sur une copie du
    contexte par ``push_frame``, pas par ``push_context_frame``, et ne réinterroge pas le modèle
    quand la fin de tour la confirme. Lancée alors qu'une relance était due, elle voit déjà le
    résultat de l'outil : sa confirmation solde la relance (sinon, deux réponses). Jetée, rien ne
    change : la fin de tour normale demande au modèle et solde la relance comme d'habitude.
    """

    assistant: AgregateurAgentRelance | None = None
    _speculation_apres_resultat: bool = False

    async def push_context_frame(self, direction=FrameDirection.DOWNSTREAM):
        if self.assistant is not None:
            self.assistant.demande_au_modele()
        await super().push_context_frame(direction)

    async def _run_speculative_inference(self, speculation):
        # Seule la DERNIÈRE spéculation compte (Pipecat remplace la précédente) : elle a vu le
        # résultat si une relance était due à son départ.
        self._speculation_apres_resultat = bool(
            self.assistant is not None and self.assistant._relance_due
        )
        await super()._run_speculative_inference(speculation)

    def resultat_arrive(self) -> None:
        """Un résultat d'outil arrive : aucune spéculation déjà partie ne l'a vu."""
        self._speculation_apres_resultat = False

    async def _on_user_turn_started(self, controller, strategy, params):
        # Un tour fini sans « stopped » (interruption, fin de session) ne transmet rien.
        self._speculation_apres_resultat = False
        await super()._on_user_turn_started(controller, strategy, params)

    async def _on_user_turn_speculation_cancelled(self, controller):
        self._speculation_apres_resultat = False
        await super()._on_user_turn_speculation_cancelled(controller)

    async def _on_user_turn_stopped(self, controller, strategy, params):
        confirmee = bool(getattr(params, "confirms_speculation", False))
        if (
            confirmee
            and self._speculation_apres_resultat
            and self.assistant is not None
        ):
            self.assistant.demande_au_modele()
        self._speculation_apres_resultat = False
        await super()._on_user_turn_stopped(controller, strategy, params)


class AgregateurAgentRelance(LLMAssistantAggregator):
    """Un résultat d'outil obtient toujours sa relance du modèle, une seule fois."""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._relance_due = False
        self._tour_ecrit = True
        appelant = self._paired_user_aggregator
        appelant.assistant = self
        appelant.add_event_handler("on_user_turn_started", self._tour_ouvert)
        appelant.add_event_handler("on_user_turn_stopped", self._tour_ferme)

    # La copie tardive du tour que tient Pipecat : toujours fausse, pour que ses trois
    # vérifications « attendre l'appelant » passent par ``_tour_en_cours``.
    @property
    def _user_speaking(self) -> bool:
        return False

    @_user_speaking.setter
    def _user_speaking(self, _valeur: bool) -> None:
        pass

    def _tour_en_cours(self) -> bool:
        controleur = self._paired_user_aggregator._user_turn_controller
        return bool(controleur._user_turn) or not self._tour_ecrit

    def demande_au_modele(self) -> None:
        # Cette demande voit le résultat : la relance gardée pour la fin du tour est inutile.
        self._relance_due = False
        self._push_context_on_bot_stopped_speaking = False

    async def push_context_frame(self, direction=FrameDirection.DOWNSTREAM):
        if direction == FrameDirection.UPSTREAM:  # vers l'amont = une demande au modèle
            self.demande_au_modele()
        await super().push_context_frame(direction)

    async def _maybe_push_context_after_function_result(self):
        self._relance_due = True
        self._paired_user_aggregator.resultat_arrive()
        if self._tour_en_cours():
            logger.debug(
                f"{self}: tour de l'appelant en cours, relance après l'outil gardée"
            )
        else:
            await super()._maybe_push_context_after_function_result()

    async def process_frame(self, frame: Frame, direction: FrameDirection):
        # L'agent peut finir de parler avant que l'interruption d'un nouveau tour nous arrive.
        if isinstance(frame, BotStoppedSpeakingFrame) and self._tour_en_cours():
            self._push_context_on_bot_stopped_speaking = False
        await super().process_frame(frame, direction)

    async def _tour_ouvert(self, _agregateur, _strategie):
        self._tour_ecrit = False

    async def _tour_ferme(self, _agregateur, _strategie, _message):
        self._tour_ecrit = True
        # La réponse de Pipecat à un tour vide, si elle a tourné, a déjà soldé la relance.
        if self._relance_due and not self._tour_en_cours():
            logger.debug(
                f"{self}: tour de l'appelant fermé, relance après l'outil envoyée"
            )
            await super()._maybe_push_context_after_function_result()


def relance_allumee(run_configs: dict | None) -> bool:
    """L'interrupteur de l'agent, lu seul par le schéma (null stocké = défaut = éteint)."""
    try:
        return WorkflowConfigurationDefaults.model_validate(
            {CLE_INTERRUPTEUR: (run_configs or {}).get(CLE_INTERRUPTEUR)}
        ).relance_apres_outil
    except Exception as erreur:  # noqa: BLE001 -- l'appel doit continuer
        logger.warning(
            f"[.mark] Interrupteur de relance après outil illisible, éteint : {erreur!r}"
        )
        return False


def paire_d_agregateurs(
    context: LLMContext,
    *,
    user_params: LLMUserAggregatorParams,
    assistant_params: LLMAssistantAggregatorParams,
    relance: bool,
) -> tuple[LLMUserAggregator, LLMAssistantAggregator]:
    """La paire du mode cascade : celle de Pipecat, ou la nôtre si l'option est allumée.
    Montée comme ``LLMContextAggregatorPair`` la monte (``realtime_service_mode=False``)."""
    if not relance:
        appelant, agent = LLMContextAggregatorPair(
            context,
            user_params=user_params,
            assistant_params=assistant_params,
            realtime_service_mode=False,
        )
        return appelant, agent
    appelant = AgregateurAppelantRelance(
        context, params=user_params, _realtime_service_mode=False
    )
    agent = AgregateurAgentRelance(
        context,
        params=assistant_params,
        _realtime_service_mode=False,
        _paired_user_aggregator=appelant,
    )
    return appelant, agent
