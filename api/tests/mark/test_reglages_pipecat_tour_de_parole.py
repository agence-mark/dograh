"""[.mark] Non-regression test for the turn-taking settings.

The question this file answers, and only this one:

    Do the turn-taking settings an agent fills in reach the objects the
    pipeline actually builds -- and does an agent that fills in nothing build
    the very same objects it built before this patch, parameter for parameter?

⛔ Read that scope literally. Nothing here says 0.6 s is a good value, or that
1.5 s would be better. That is the A/B benches' job, in the browser and on the
phone. This file proves only that the screen and the pipeline describe each
other.

Why it exists
-------------
Turn taking decides whether the agent talks over the caller or leaves a
silence, and every value governing it was a literal nobody had chosen:
``SpeechTimeoutUserTurnStopStrategy()`` built with no argument at all (so
Pipecat's 0.6 s), ``VADParams(stop_secs=0.2)`` written out TWICE in two
different code paths, Smart Turn on its 500 ms / 8 s defaults, and the
aggregator's ``audio_idle_timeout`` of 1 s.

What "unchanged" means here
---------------------------
🔑 The expected values below are LITERALS, measured from the code as it stood
before this patch. Deriving them from the constants the patch introduces would
make the assertion tautological: the constants are what moves.

⚠️ One assertion is on the SOURCE of ``run_pipeline.py``. It is the only way
to state "no code path builds its own detector any more" -- and the detector
being built in two places, one of them easy to miss, is exactly how this kind
of setting ends up applying to half the calls.
"""

import inspect
import re
from types import SimpleNamespace

import pytest
from pipecat.audio.turn.smart_turn import base_smart_turn
from pipecat.audio.vad import vad_analyzer
from pipecat.processors.aggregators.llm_response_universal import (
    LLMUserAggregatorParams,
)
from pipecat.turns.user_start.transcription_user_turn_start_strategy import (
    TranscriptionUserTurnStartStrategy,
)
from pipecat.turns.user_start.vad_user_turn_start_strategy import (
    VADUserTurnStartStrategy,
)
from pipecat.turns.user_stop.external_user_turn_stop_strategy import (
    ExternalUserTurnStopStrategy,
)
from pipecat.turns.user_stop.speech_timeout_user_turn_stop_strategy import (
    SpeechTimeoutUserTurnStopStrategy,
)
from pipecat.turns.user_stop.turn_analyzer_user_turn_stop_strategy import (
    TurnAnalyzerUserTurnStopStrategy,
)
from pipecat.turns.user_turn_completion_mixin import UserTurnCompletionConfig

from api.schemas.workflow_configurations import WorkflowConfigurationDefaults
from api.services.pipecat import run_pipeline
from api.services.pipecat.reglages_tour_de_parole import (
    appliquer_latence_de_transcription,
    collecter_reglages_tour_de_parole,
)

# ⛔ The values that ran BEFORE this patch, read off the code of 2026-09-14.
# Written as literals on purpose -- see the module docstring.
USER_SPEECH_TIMEOUT_AVANT = 0.6
VAD_AVANT = {
    "confidence": 0.7,
    "start_secs": 0.2,
    "stop_secs": 0.2,
    "min_volume": 0.6,
}
SMART_TURN_AVANT = {"pre_speech_ms": 500, "max_duration_secs": 8}
AUDIO_IDLE_TIMEOUT_AVANT = 1.0
USER_TURN_STOP_TIMEOUT_AVANT = 5.0


def _arret(run_configs=None, uses_external_turns=False, turn_stop_strategy=None):
    run_configs = dict(run_configs or {})
    if turn_stop_strategy:
        run_configs["turn_stop_strategy"] = turn_stop_strategy
    return run_pipeline._create_non_realtime_user_turn_stop_strategies(
        run_configs,
        uses_external_turns=uses_external_turns,
        reglages=collecter_reglages_tour_de_parole(run_configs),
    )


def _depart(run_configs=None, uses_external_turns=False):
    run_configs = dict(run_configs or {})
    return run_pipeline._create_non_realtime_user_turn_start_strategies(
        run_configs,
        uses_external_turns=uses_external_turns,
        reglages=collecter_reglages_tour_de_parole(run_configs),
    )


def _detecteur(run_configs=None):
    return collecter_reglages_tour_de_parole(run_configs).parametres_detecteur()


# --------------------------------------------------------------------------- #
# 1. An agent that fills in nothing builds exactly what it built before
# --------------------------------------------------------------------------- #


def test_sans_reglage_la_strategie_darret_est_celle_daujourdhui():
    (strategie,) = _arret()
    assert isinstance(strategie, SpeechTimeoutUserTurnStopStrategy)
    assert strategie._user_speech_timeout == USER_SPEECH_TIMEOUT_AVANT
    assert strategie._wait_for_transcript is True


def test_sans_reglage_le_detecteur_est_celui_daujourdhui():
    params = _detecteur()
    assert params.model_dump() == VAD_AVANT


def test_sans_reglage_smart_turn_est_celui_daujourdhui():
    (strategie,) = _arret(turn_stop_strategy="turn_analyzer")
    assert isinstance(strategie, TurnAnalyzerUserTurnStopStrategy)
    params = strategie._turn_analyzer._params
    assert params.pre_speech_ms == SMART_TURN_AVANT["pre_speech_ms"]
    assert params.max_duration_secs == SMART_TURN_AVANT["max_duration_secs"]
    # Already exposed before this patch, and unchanged by it.
    assert params.stop_secs == 2.0


def _agregateur(run_configs=None):
    """The parameters the pipeline hands to the user aggregator."""
    return run_pipeline._construire_parametres_agregateur_utilisateur(
        user_turn_strategies=None,
        user_mute_strategies=[],
        user_turn_stop_timeout=USER_TURN_STOP_TIMEOUT_AVANT,
        max_user_idle_timeout=10.0,
        user_vad_analyzer=None,
        reglages=collecter_reglages_tour_de_parole(run_configs),
    )


def test_sans_reglage_lagregateur_est_celui_daujourdhui():
    params = _agregateur()
    defauts = LLMUserAggregatorParams()
    assert params.audio_idle_timeout == AUDIO_IDLE_TIMEOUT_AVANT
    assert params.audio_idle_timeout == defauts.audio_idle_timeout
    assert params.filter_incomplete_user_turns is False
    assert params.user_turn_completion_config is None


def test_les_reglages_de_lagregateur_arrivent():
    params = _agregateur(
        {
            "audio_idle_timeout": 2.5,
            "filter_incomplete_user_turns": True,
            "incomplete_short_timeout": 3,
        }
    )
    assert params.audio_idle_timeout == 2.5
    assert params.filter_incomplete_user_turns is True
    assert params.user_turn_completion_config.incomplete_short_timeout == 3


def test_sans_reglage_les_strategies_de_depart_sont_celles_daujourdhui():
    transcription, vad = _depart()
    assert isinstance(transcription, TranscriptionUserTurnStartStrategy)
    assert isinstance(vad, VADUserTurnStartStrategy)
    assert transcription._use_interim is True


def test_sans_reglage_le_plafond_dattente_est_celui_daujourdhui():
    assert (
        run_pipeline._resolve_user_turn_stop_timeout({}, uses_external_turns=False)
        == USER_TURN_STOP_TIMEOUT_AVANT
    )


def test_le_plafond_dattente_garde_ses_DEUX_defauts():
    """🚨 The blocking defect of 2026-09-14, found by the independent review.

    This setting has TWO defaults, not one: 5 s normally, and 30 s when the
    transcription service drives the turns itself. Declaring it with 5 as a
    default meant the screen materialised 5 into the stored configuration on
    the first save -- so opening a Flux agent's dialog to change its VOICE cut
    its transcript ceiling from 30 s to 5 s, from a section the screen hides
    from exactly those agents.

    ⛔ The pipeline therefore tests "filled in", not "present": since the
    screen materialises the whole configuration, the key exists on every agent
    ever saved.
    """
    assert (
        run_pipeline._resolve_user_turn_stop_timeout({}, uses_external_turns=True)
        == 30.0
    )
    # A key stored as null (never filled in) must behave like an absent key.
    assert (
        run_pipeline._resolve_user_turn_stop_timeout(
            {"user_turn_stop_timeout": None}, uses_external_turns=True
        )
        == 30.0
    )
    assert (
        run_pipeline._resolve_user_turn_stop_timeout(
            {"user_turn_stop_timeout": None}, uses_external_turns=False
        )
        == USER_TURN_STOP_TIMEOUT_AVANT
    )
    # And a value genuinely filled in still wins, in both modes.
    assert (
        run_pipeline._resolve_user_turn_stop_timeout(
            {"user_turn_stop_timeout": 12}, uses_external_turns=True
        )
        == 12
    )


def test_le_schema_laisse_le_plafond_dattente_VIDE():
    """⛔ Empty, because there is no single number that is right in both modes."""
    assert WorkflowConfigurationDefaults().user_turn_stop_timeout is None


# --------------------------------------------------------------------------- #
# 2. A setting that is filled in reaches the object that is built
# --------------------------------------------------------------------------- #


def test_le_delai_de_silence_arrive_dans_la_strategie():
    (strategie,) = _arret({"user_speech_timeout": 1.5})
    assert strategie._user_speech_timeout == 1.5


def test_lattente_de_transcription_arrive_dans_les_deux_strategies():
    (silence,) = _arret({"turn_wait_for_transcript": False})
    assert silence._wait_for_transcript is False
    (smart,) = _arret(
        {"turn_wait_for_transcript": False}, turn_stop_strategy="turn_analyzer"
    )
    assert smart._wait_for_transcript is False


@pytest.mark.parametrize(
    "cle,attendu",
    [
        ("vad_confidence", 0.4),
        ("vad_start_secs", 0.9),
        ("vad_stop_secs", 0.8),
        ("vad_min_volume", 0.1),
    ],
)
def test_chaque_reglage_du_detecteur_arrive(cle, attendu):
    params = _detecteur({cle: attendu})
    assert getattr(params, cle.removeprefix("vad_")) == attendu


def test_les_reglages_smart_turn_arrivent():
    (strategie,) = _arret(
        {"smart_turn_pre_speech_ms": 250, "smart_turn_max_duration_secs": 12},
        turn_stop_strategy="turn_analyzer",
    )
    params = strategie._turn_analyzer._params
    assert params.pre_speech_ms == 250
    assert params.max_duration_secs == 12


def test_les_resultats_intermediaires_arrivent_dans_les_strategies_de_depart():
    transcription, _ = _depart({"turn_start_use_interim": False})
    assert transcription._use_interim is False

    (min_words,) = _depart(
        {"turn_start_use_interim": False, "turn_start_strategy": "min_words"}
    )
    assert min_words._use_interim is False

    # [.mark] Montee du 2026-09-16 (D9) : `provisional_vad` a ete mis a la
    # retraite par l'amont, ce cas est donc REECRIT et non supprime.
    # 🔑 Ce qu'il garde maintenant vaut mieux que ce qu'il gardait avant : une
    # definition d'agent enregistree AVANT la retraite porte encore cette
    # valeur en base, l'amont la ramene sur les strategies par defaut -- et
    # notre reglage `turn_start_use_interim` doit survivre a cette retombee.
    # ⛔ Sans cette assertion, un agent ancien repartirait en silence sur le
    # defaut de Pipecat pour les resultats intermediaires.
    transcription_retombee, _ = _depart(
        {"turn_start_use_interim": False, "turn_start_strategy": "provisional_vad"}
    )
    assert transcription_retombee._use_interim is False


def test_la_fin_de_tour_par_le_modele_sallume_avec_ses_delais():
    reglages = collecter_reglages_tour_de_parole(
        {
            "filter_incomplete_user_turns": True,
            "incomplete_short_timeout": 3,
            "incomplete_long_timeout": 7,
        }
    )
    configuration = reglages.configuration_de_fin_de_tour()
    assert isinstance(configuration, UserTurnCompletionConfig)
    assert configuration.incomplete_short_timeout == 3
    assert configuration.incomplete_long_timeout == 7


def test_les_delais_de_fin_de_tour_ne_sont_pas_construits_si_le_reglage_est_eteint():
    reglages = collecter_reglages_tour_de_parole(
        {"filter_incomplete_user_turns": False, "incomplete_short_timeout": 3}
    )
    assert reglages.configuration_de_fin_de_tour() is None


def test_le_plafond_dattente_rempli_arrive():
    assert (
        run_pipeline._resolve_user_turn_stop_timeout(
            {"user_turn_stop_timeout": 12}, uses_external_turns=False
        )
        == 12
    )


# --------------------------------------------------------------------------- #
# 3. A null stored on the configuration is "not filled in", never a value
# --------------------------------------------------------------------------- #


def test_un_null_enregistre_ne_devient_pas_une_valeur():
    """Stored configurations carry explicit JSON nulls for untouched keys.

    ⛔ Reading them literally would hand ``None`` to Pipecat where a number is
    expected, and the call would fail mid-conversation rather than here.
    """
    reglages = collecter_reglages_tour_de_parole(
        {"user_speech_timeout": None, "vad_stop_secs": None, "audio_idle_timeout": None}
    )
    assert reglages.user_speech_timeout == USER_SPEECH_TIMEOUT_AVANT
    assert reglages.vad_stop_secs == VAD_AVANT["stop_secs"]
    assert reglages.audio_idle_timeout == AUDIO_IDLE_TIMEOUT_AVANT


# --------------------------------------------------------------------------- #
# 4. Where these settings have no effect, nothing is built
# --------------------------------------------------------------------------- #


def test_une_transcription_qui_pilote_les_tours_ignore_la_section():
    """Flux and Cartesia ink-2 define the turn boundary themselves."""
    (depart,) = _depart({"user_speech_timeout": 1.5}, uses_external_turns=True)
    (arret,) = _arret({"user_speech_timeout": 1.5}, uses_external_turns=True)
    assert isinstance(arret, ExternalUserTurnStopStrategy)
    assert not isinstance(depart, TranscriptionUserTurnStartStrategy)


def test_la_latence_de_transcription_nest_pas_posee_sur_un_service_qui_nen_a_pas():
    """⛔ Writing a value there would claim a wait that never happens."""
    service = SimpleNamespace(supports_ttfs=False, _ttfs_p99_latency=None)
    appliquer_latence_de_transcription(service, 0.9)
    assert service._ttfs_p99_latency is None


def test_la_latence_de_transcription_arrive_sur_un_service_qui_en_a_une():
    service = SimpleNamespace(supports_ttfs=True, _ttfs_p99_latency=0.35)
    appliquer_latence_de_transcription(service, 0.9)
    assert service._ttfs_p99_latency == 0.9


def test_la_latence_laissee_vide_ne_touche_a_rien():
    """Empty means "the value Pipecat measured for this provider"."""
    service = SimpleNamespace(supports_ttfs=True, _ttfs_p99_latency=0.35)
    appliquer_latence_de_transcription(service, None)
    assert service._ttfs_p99_latency == 0.35


# --------------------------------------------------------------------------- #
# 5. The link with Pipecat, so an upgrade is decided and not absorbed
# --------------------------------------------------------------------------- #


def test_nos_constantes_egalent_les_defauts_de_pipecat():
    """🔑 Goes RED the day a Pipecat upgrade moves one of these defaults.

    That is the point: the value then changes because someone decided it,
    not because a version bump carried it in unnoticed.
    """
    configuration = WorkflowConfigurationDefaults()
    assert configuration.vad_confidence == vad_analyzer.VAD_CONFIDENCE
    assert configuration.vad_start_secs == vad_analyzer.VAD_START_SECS
    assert configuration.vad_stop_secs == vad_analyzer.VAD_STOP_SECS
    assert configuration.vad_min_volume == vad_analyzer.VAD_MIN_VOLUME
    assert configuration.smart_turn_pre_speech_ms == base_smart_turn.PRE_SPEECH_MS
    assert (
        configuration.smart_turn_max_duration_secs
        == base_smart_turn.MAX_DURATION_SECONDS
    )
    defauts_agregateur = LLMUserAggregatorParams()
    assert configuration.audio_idle_timeout == defauts_agregateur.audio_idle_timeout
    assert (
        configuration.filter_incomplete_user_turns
        == defauts_agregateur.filter_incomplete_user_turns
    )
    # ⛔ Not compared to the aggregator's default: ours is deliberately empty,
    # because this setting has two defaults and the pipeline picks between
    # them. The constant that reproduces Pipecat's is asserted instead.
    assert run_pipeline.DEFAULT_USER_TURN_STOP_TIMEOUT == (
        defauts_agregateur.user_turn_stop_timeout
    )
    completion = UserTurnCompletionConfig()
    assert configuration.incomplete_short_timeout == completion.incomplete_short_timeout
    assert configuration.incomplete_long_timeout == completion.incomplete_long_timeout
    # ⛔ Pipecat's own signature, not a constant: this one is a default
    # argument of the strategy, and that is where a bump would move it.
    signature = inspect.signature(SpeechTimeoutUserTurnStopStrategy.__init__)
    assert (
        configuration.user_speech_timeout
        == signature.parameters["user_speech_timeout"].default
    )
    assert (
        configuration.turn_wait_for_transcript
        == signature.parameters["wait_for_transcript"].default
    )


# --------------------------------------------------------------------------- #
# 6. No code path builds its own values any more
# --------------------------------------------------------------------------- #


def test_le_pipeline_ne_construit_plus_de_detecteur_en_dur():
    """⛔ On the source text, deliberately.

    The detector is built in two places, one of them in the realtime path
    where it is easy to miss. A runtime assertion can only speak for the path
    it exercises; this one speaks for both.
    """
    source = inspect.getsource(run_pipeline)
    assert "VADParams(stop_secs=0.2)" not in source, (
        "A code path builds the voice detector with a hardcoded 0.2 s again. "
        "Both paths must take their parameters from "
        "ReglagesTourDeParole.parametres_detecteur()."
    )
    assert "SpeechTimeoutUserTurnStopStrategy()" not in source, (
        "The silence strategy is built with no argument again, which silently "
        "restores Pipecat's 0.6 s whatever the agent configured."
    )
    # ⚠️ Tolerant to spacing: an exact-literal assertion is a net that a
    # formatter takes down without a sound. Raised by the review of 14/09.
    assert not re.search(r"VADParams\s*\(\s*stop_secs\s*=", source), (
        "A code path builds the voice detector with a literal stop_secs again."
    )


# --------------------------------------------------------------------------- #
# 7. The screen's defaults and Python's are the same numbers
# --------------------------------------------------------------------------- #


def test_les_defauts_de_lecran_egalent_ceux_du_schema():
    """🔑 The screen carries its own copy of these defaults, and has to.

    The generated client is regenerated against a running backend, which is
    not something a test can do here. So the values live twice -- and two
    copies drift. This test is where the drift surfaces: the screen would
    otherwise draw 0.6 s next to a pipeline running 0.8 s, and the client
    would believe the field showed what the call used.
    """
    import json
    import re
    from pathlib import Path

    fichier = (
        Path(__file__).resolve().parents[3]
        / "ui"
        / "src"
        / "types"
        / "workflow-configurations.ts"
    )
    texte = fichier.read_text(encoding="utf-8")
    bloc = re.search(
        r"export const DEFAUTS_PIPECAT = \{(.*?)\} as const;", texte, re.DOTALL
    )
    assert bloc, "DEFAUTS_PIPECAT disappeared from the screen's types."

    # ⛔ Multi-line values too: the two idle prompts are long enough that the
    # formatter puts them on their own line, and a line-by-line parser would
    # silently skip exactly the settings hardest to keep in step.
    # ⛔ And commas INSIDE a quoted value: `variables_commune` is a list of names
    # written as one string (2026-09-17). Without the quoted alternative its
    # line would not match, and only the count below would say so.
    ecran = {}
    for cle, brut in re.findall(
        r"^ {4}([a-z_0-9]+):((?:'[^'\n]*'|[^,\n]|\n {8,})+),$",
        bloc.group(1),
        re.MULTILINE,
    ):
        brut = " ".join(brut.split())
        # TypeScript writes strings with single quotes; JSON wants double.
        if brut.startswith("'") and brut.endswith("'"):
            brut = '"' + brut[1:-1].replace('"', '\\"') + '"'
        ecran[cle] = json.loads(brut)

    schema = WorkflowConfigurationDefaults()
    for cle, valeur_ecran in ecran.items():
        valeur_schema = getattr(schema, cle)
        assert valeur_ecran == valeur_schema, (
            f"'{cle}': the screen shows {valeur_ecran!r} and the pipeline runs "
            f"{valeur_schema!r}. One of the two copies moved without the other."
        )
    # 32 until 2026-09-17, then 35: the trade vocabulary and the two sound
    # switches (plan lexique-metier, L2 and L18). Then 37 on 2026-09-22: the
    # two switches that forbid saying the caller's name and title.
    assert len(ecran) == 37, (
        f"The screen declares {len(ecran)} Pipecat defaults, expected 37. "
        f"A setting added on one side only renders and is then dropped."
    )


def test_la_fin_de_tour_par_le_modele_existe_encore_chez_pipecat():
    """⚠️ Deprecated upstream since Pipecat 1.2.0, removed in 2.0.0.

    Exposed anyway -- off by default, and an A/B may want to try it -- but the
    day it disappears, this test goes red rather than letting a screen offer a
    setting the pipeline silently ignores. It takes `incomplete_short_timeout`
    and `incomplete_long_timeout` with it. Raised by the review of 14/09.
    """
    defauts = LLMUserAggregatorParams()
    assert hasattr(defauts, "filter_incomplete_user_turns"), (
        "Pipecat dropped `filter_incomplete_user_turns`. Three settings on the "
        "agent screen no longer do anything: remove them, and say so in the "
        "release notes rather than leaving dead switches."
    )
