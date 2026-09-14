"""[.mark] Non-regression test for muting the caller's microphone.

The questions this file answers:

    Does an agent that fills in nothing get the exact same three strategies,
    in the same order, as before this patch -- and does each switch add or
    remove precisely the strategy it names?

What it settles in a real call: the greeting cut in half by a "hello", and
the transfer interrupted halfway through.

⛔ Read the scope literally. Nothing here says the three that run today are
the right three. That is heard on a call.

Why the ORDER is asserted, not just the membership
--------------------------------------------------
Pipecat walks the list and the first strategy that answers "mute" wins. Two
lists with the same strategies in a different order are not the same
behaviour, and a set comparison would call them equal.
"""

import pytest

from api.schemas.workflow_configurations import WorkflowConfigurationDefaults
from api.services.pipecat.reglages_tour_de_parole import (
    collecter_strategies_de_coupure,
)
from pipecat.turns.user_mute.always_user_mute_strategy import AlwaysUserMuteStrategy
from pipecat.turns.user_mute.callback_user_mute_strategy import CallbackUserMuteStrategy
from pipecat.turns.user_mute.first_speech_user_mute_strategy import (
    FirstSpeechUserMuteStrategy,
)
from pipecat.turns.user_mute.function_call_user_mute_strategy import (
    FunctionCallUserMuteStrategy,
)
from pipecat.turns.user_mute.mute_until_first_bot_complete_user_mute_strategy import (
    MuteUntilFirstBotCompleteUserMuteStrategy,
)

# ⛔ The literal list the pipeline built before this patch, in its order.
COUPURES_AVANT = [
    MuteUntilFirstBotCompleteUserMuteStrategy,
    FunctionCallUserMuteStrategy,
    CallbackUserMuteStrategy,
]


async def _rappel(*args, **kwargs):
    return False


def _strategies(run_configs=None):
    return [
        type(s)
        for s in collecter_strategies_de_coupure(
            run_configs, should_mute_callback=_rappel
        )
    ]


# --------------------------------------------------------------------------- #
# 1. An agent that fills in nothing gets exactly today's list
# --------------------------------------------------------------------------- #


def test_sans_reglage_les_trois_strategies_daujourdhui_dans_lordre():
    assert _strategies() == COUPURES_AVANT


def test_les_defauts_declares_sont_trois_allumes_et_deux_eteints():
    configuration = WorkflowConfigurationDefaults()
    assert configuration.mute_until_first_bot_complete is True
    assert configuration.mute_during_function_call is True
    assert configuration.mute_engine_callback is True
    assert configuration.mute_first_speech is False
    assert configuration.mute_always is False


def test_un_null_enregistre_ne_coupe_pas_une_strategie():
    assert (
        _strategies(
            {
                "mute_until_first_bot_complete": None,
                "mute_during_function_call": None,
                "mute_engine_callback": None,
            }
        )
        == COUPURES_AVANT
    )


# --------------------------------------------------------------------------- #
# 2. Each switch adds or removes exactly what it names
# --------------------------------------------------------------------------- #


@pytest.mark.parametrize(
    "reglage,classe",
    [
        ("mute_until_first_bot_complete", MuteUntilFirstBotCompleteUserMuteStrategy),
        ("mute_during_function_call", FunctionCallUserMuteStrategy),
        ("mute_engine_callback", CallbackUserMuteStrategy),
    ],
)
def test_eteindre_un_reglage_retire_sa_strategie_et_seulement_elle(reglage, classe):
    obtenues = _strategies({reglage: False})
    assert classe not in obtenues
    assert obtenues == [c for c in COUPURES_AVANT if c is not classe]


@pytest.mark.parametrize(
    "reglage,classe",
    [
        ("mute_first_speech", FirstSpeechUserMuteStrategy),
        ("mute_always", AlwaysUserMuteStrategy),
    ],
)
def test_allumer_un_reglage_inutilise_ajoute_sa_strategie(reglage, classe):
    obtenues = _strategies({reglage: True})
    assert obtenues == COUPURES_AVANT + [classe]


def test_tout_eteindre_laisse_une_liste_vide():
    """An agent that can always be interrupted, whatever it is saying."""
    assert (
        _strategies(
            {
                "mute_until_first_bot_complete": False,
                "mute_during_function_call": False,
                "mute_engine_callback": False,
            }
        )
        == []
    )


def test_la_regle_du_workflow_est_bien_celle_qui_est_branchee():
    """⛔ The callback strategy must carry the ENGINE's rule, not a stand-in.

    Built with the wrong callback, every "do not interrupt" set on a node
    would be ignored while the switch still read as on.
    """
    temoin = object()
    strategies = collecter_strategies_de_coupure(None, should_mute_callback=temoin)
    rappel = next(
        s for s in strategies if isinstance(s, CallbackUserMuteStrategy)
    )._should_mute_callback
    assert rappel is temoin
