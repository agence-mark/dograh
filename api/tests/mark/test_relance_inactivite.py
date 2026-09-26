"""[.mark] Non-regression test for the idle prompts.

The questions this file answers:

    Does an agent that fills in nothing send the very same two instructions,
    after the same number of prompts, and hang up at the same moment as
    before -- and does an agent that fills them in actually get its own texts
    and its own count?

Why it exists
-------------
A caller who went quiet was answered by two instructions written into
``pipecat_engine_callbacks.py``, both in English, with exactly one prompt
before the hang-up. Nothing on any screen said so, and a French-speaking
client could change neither.

⚠️ What this file does NOT prove: that the model obeys the instruction, or
that it answers in French. Both instructions already ask it to answer in the
caller's language; whether it does is heard on a call, not asserted here.
"""

import pytest

from api.schemas.workflow_configurations import (
    DEFAULT_USER_IDLE_GOODBYE_PROMPT,
    DEFAULT_USER_IDLE_MAX_PROMPTS,
    DEFAULT_USER_IDLE_PROMPT,
    WorkflowConfigurationDefaults,
)
from api.services.pipecat.call_monitor_processor import CallMonitorProcessor
from api.services.workflow.pipecat_engine_callbacks import handle_user_idle


class _AgregateurFactice:
    """Collects the frames the handler pushes, in order."""

    def __init__(self):
        self.consignes = []

    async def push_frame(self, frame):
        for message in frame.messages:
            self.consignes.append(message["content"])


class _MoteurFactice:
    """Since upstream 4e6cb22b the call monitor counts the silences and hands
    each one to ``handle_user_idle`` with its number; the agent's settings are
    those given to ``PipecatEngine.regler_relances`` at call setup."""

    def __init__(self, run_configs=None):
        self.raccroche = None
        self.reglages_relances = dict(run_configs or {})

    async def end_call_with_reason(self, reason):
        self.raccroche = reason


async def _jouer(run_configs, silences: int):
    """Play `silences` consecutive idle events and report what came out."""
    moteur = _MoteurFactice(run_configs)
    agregateur = _AgregateurFactice()
    for tentative in range(1, silences + 1):
        await handle_user_idle(moteur, agregateur, tentative)
    return agregateur.consignes, moteur


# --------------------------------------------------------------------------- #
# 1. An agent that fills in nothing behaves exactly as before
# --------------------------------------------------------------------------- #


@pytest.mark.asyncio
async def test_sans_reglage_les_deux_consignes_sont_celles_daujourdhui():
    consignes, moteur = await _jouer(None, silences=2)
    assert consignes == [
        DEFAULT_USER_IDLE_PROMPT,
        DEFAULT_USER_IDLE_GOODBYE_PROMPT,
    ]
    assert moteur.raccroche is not None


@pytest.mark.asyncio
async def test_sans_reglage_le_raccrochage_arrive_au_deuxieme_silence():
    """⛔ Not at the third, not at the first. That is today's behaviour."""
    _, moteur = await _jouer(None, silences=1)
    assert moteur.raccroche is None


def test_les_textes_par_defaut_sont_ceux_ecrits_dans_le_pipeline():
    """The two English texts, copied verbatim into the schema.

    ⛔ Written out here as literals: comparing the constant to itself would
    prove nothing. This is what catches a "small rewording" of the defaults,
    which would change the behaviour of every existing agent at once.
    """
    configuration = WorkflowConfigurationDefaults()
    assert configuration.user_idle_prompt == (
        "The user has been quiet. Politely and briefly ask if they're still "
        "there in the language that the user has been speaking so far."
    )
    assert configuration.user_idle_goodbye_prompt == (
        "The user has been quiet. We will be disconnecting the call now. Wish "
        "them a good day in the language that the user has been speaking so far."
    )
    assert configuration.user_idle_max_prompts == DEFAULT_USER_IDLE_MAX_PROMPTS == 1


# --------------------------------------------------------------------------- #
# 2. A setting that is filled in is the one that plays
# --------------------------------------------------------------------------- #


@pytest.mark.asyncio
async def test_les_textes_saisis_arrivent_au_modele():
    consignes, _ = await _jouer(
        {
            "user_idle_prompt": "Demande poliment si la personne est toujours la.",
            "user_idle_goodbye_prompt": "Souhaite une bonne journee et raccroche.",
        },
        silences=2,
    )
    assert consignes == [
        "Demande poliment si la personne est toujours la.",
        "Souhaite une bonne journee et raccroche.",
    ]


@pytest.mark.asyncio
async def test_deux_relances_avant_lau_revoir():
    consignes, moteur = await _jouer({"user_idle_max_prompts": 2}, silences=2)
    assert consignes == [DEFAULT_USER_IDLE_PROMPT, DEFAULT_USER_IDLE_PROMPT]
    assert moteur.raccroche is None

    consignes, moteur = await _jouer({"user_idle_max_prompts": 2}, silences=3)
    assert consignes[-1] == DEFAULT_USER_IDLE_GOODBYE_PROMPT
    assert moteur.raccroche is not None


@pytest.mark.asyncio
async def test_zero_relance_raccroche_des_le_premier_silence():
    """⛔ 0 is a value, not "unset".

    Reading it with `or` would silently turn it back into 1, and an agent set
    to hang up straight away would keep prompting -- with nothing to say so.
    """
    consignes, moteur = await _jouer({"user_idle_max_prompts": 0}, silences=1)
    assert consignes == [DEFAULT_USER_IDLE_GOODBYE_PROMPT]
    assert moteur.raccroche is not None


@pytest.mark.asyncio
async def test_un_null_enregistre_ne_devient_pas_un_texte_vide():
    """An untouched key is stored as an explicit JSON null."""
    consignes, _ = await _jouer(
        {
            "user_idle_prompt": None,
            "user_idle_goodbye_prompt": None,
            "user_idle_max_prompts": None,
        },
        silences=2,
    )
    assert consignes == [DEFAULT_USER_IDLE_PROMPT, DEFAULT_USER_IDLE_GOODBYE_PROMPT]


def test_le_compteur_repart_quand_la_personne_reparle():
    """The count now lives in upstream's call monitor: when the caller speaks
    again it starts over, so the next silence is prompted again rather than
    answered with the goodbye."""
    moniteur = CallMonitorProcessor(
        response_source=lambda: None,
        on_response_timeout=lambda _source: None,
        on_user_idle=None,
        conversation_enabled=lambda: True,
    )
    moniteur._retry_count = 1
    moniteur._user_started()
    assert moniteur._retry_count == 0


def test_la_configuration_de_l_agent_est_donnee_au_moteur_a_l_appel():
    """Without ``regler_relances`` at call setup, the three settings on screen
    would have no effect (collision 4 of the 25/09 analysis)."""
    import inspect

    from api.services.pipecat import run_pipeline

    assert "engine.regler_relances(run_configs)" in inspect.getsource(run_pipeline)


# The matching guard -- "does the pipeline actually hand the configuration
# over" -- lives in test_transmission_de_la_configuration.py, which asserts it
# for every collection point at once rather than lot by lot.
