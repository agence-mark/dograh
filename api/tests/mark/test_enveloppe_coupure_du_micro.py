"""[.mark] Non-regression test for the compatibility wrapper on mute strategies.

The question this file answers, and it answers only this one:

    Does `_create_user_mute_strategies` still return EXACTLY what the upstream
    function it replaces returned -- same strategies, same order, same length?

Why it exists
-------------
Upstream builds its mute strategies from a fixed list of three. This fork builds
them from the agent's five settings (`collecter_strategies_de_coupure`), and keeps
`_create_user_mute_strategies` only as a three-line wrapper, because two upstream
test files import it BY NAME. Removing it made them fail at COLLECTION -- about
sixteen tests stopped running altogether, and those were the very tests that
caught a `NameError` our own 523 tests never saw.

🔑 The wrapper's fidelity rests on two schema defaults being False
(`DEFAULT_MUTE_FIRST_SPEECH`, `DEFAULT_MUTE_ALWAYS`). Nothing asserted that.
⛔ And upstream's own test only checks element [0]. So the day a screen setting
flips either default to True, the wrapper would return four or five strategies
where upstream's contract promises three, their test would stay green, and the
divergence would pass in silence.

That is the whole point of this file: the invariant asserted in BOTH directions
and COUNTED, which is the rule this fork applies everywhere else.
"""

from types import SimpleNamespace

from pipecat.turns.user_mute import (
    CallbackUserMuteStrategy,
    FirstSpeechUserMuteStrategy,
    FunctionCallUserMuteStrategy,
    MuteUntilFirstBotCompleteUserMuteStrategy,
)

from api.schemas.workflow_configurations import (
    DEFAULT_MUTE_ALWAYS,
    DEFAULT_MUTE_FIRST_SPEECH,
)
from api.services.pipecat.run_pipeline import _create_user_mute_strategies

# The contract of the upstream function this wrapper stands in for, written as a
# literal. ⛔ Not derived from the code that produces it: a list compared with
# itself always agrees.
CONTRAT_SANS_SUPERVISION = [
    MuteUntilFirstBotCompleteUserMuteStrategy,
    FunctionCallUserMuteStrategy,
    CallbackUserMuteStrategy,
]
CONTRAT_AVEC_SUPERVISION = [
    FirstSpeechUserMuteStrategy,
    FunctionCallUserMuteStrategy,
    CallbackUserMuteStrategy,
]


def _moteur():
    """A stand-in engine carrying only what the wrapper reads from it."""
    return SimpleNamespace(should_mute_user=lambda *a, **k: False)


def test_sans_supervision_la_liste_est_celle_de_lamont():
    moteur = _moteur()
    strategies = _create_user_mute_strategies(moteur, None)

    # ⛔ The ORDER is the assertion, not the membership: Pipecat walks the list
    # and the first strategy answering "mute" wins, so two lists holding the same
    # strategies in a different order do not behave the same.
    assert [type(s) for s in strategies] == CONTRAT_SANS_SUPERVISION
    assert len(strategies) == 3


def test_avec_supervision_la_premiere_devient_first_speech():
    moteur = _moteur()
    strategies = _create_user_mute_strategies(moteur, SimpleNamespace())

    assert [type(s) for s in strategies] == CONTRAT_AVEC_SUPERVISION
    assert len(strategies) == 3


def test_le_rappel_de_coupure_du_moteur_est_bien_celui_transmis():
    """🔑 Asserted on IDENTITY, not on the type.

    ⛔ `mute_engine_callback` off ignores every "do not interrupt" set on a
    workflow node, silently. A strategy built with someone else's callback would
    be the same defect wearing the right class name.
    """
    moteur = _moteur()
    (_, _, rappel) = _create_user_mute_strategies(moteur, None)

    assert isinstance(rappel, CallbackUserMuteStrategy)
    assert rappel._should_mute_callback is moteur.should_mute_user


def test_les_deux_defauts_sur_lesquels_la_fidelite_repose():
    """⛔ The two schema defaults the wrapper's fidelity depends on.

    🔑 This is the test that turns a silent divergence into a red one. If either
    default becomes True, the wrapper returns four or five strategies where the
    upstream contract promises three -- and upstream's own test, which only looks
    at element [0], would stay green.

    Going red here is not a bug to silence: it means the upstream contract and
    our settings have genuinely parted ways, and the wrapper has to be told which
    one it serves.
    """
    assert DEFAULT_MUTE_FIRST_SPEECH is False
    assert DEFAULT_MUTE_ALWAYS is False
