"""[.mark] The turn-taking settings an agent can configure, collected once.

Why this module exists
----------------------
Turn taking is what decides whether the agent cuts the caller off or leaves a
silence, and before this patch every value that governs it was a literal in
``run_pipeline.py`` or a Pipecat default nobody had ever looked at: the caller
was given 0.6 s to pause, the voice detector was built as
``VADParams(stop_secs=0.2)`` in two different places, and Smart Turn ran on
500 ms of pre-speech and an 8 s ceiling. None of it was chosen.

🔑 ONE collection point, read once per run, rather than a dozen
``run_configs.get(...)`` scattered through a 1200-line pipeline. The same
reason as the voice filters: a setting wired where it happens to be needed
applies in the places whoever wired it thought of, and silently nowhere else
-- and the voice detector really is built in two places.

🔒 Every default reproduces the value the pipeline ran with before this patch.
An agent that fills in nothing builds the same objects, parameter for
parameter. The A/B benches choose the values; a later patch moves the
defaults.

⚠️ These settings play no part when the transcription service drives the turns
itself (Deepgram Flux, Cartesia ink-2) or in realtime mode: the pipeline does
not build these strategies at all. The screen hides the section in that case
rather than showing values that do nothing -- a setting displayed in a state
that is not its own is worse than a setting not displayed.
"""

from dataclasses import dataclass

from api.schemas.workflow_configurations import (
    DEFAULT_AUDIO_IDLE_TIMEOUT,
    DEFAULT_FILTER_INCOMPLETE_USER_TURNS,
    DEFAULT_INCOMPLETE_LONG_TIMEOUT,
    DEFAULT_INCOMPLETE_SHORT_TIMEOUT,
    DEFAULT_SMART_TURN_MAX_DURATION_SECS,
    DEFAULT_SMART_TURN_PRE_SPEECH_MS,
    DEFAULT_TURN_START_USE_INTERIM,
    DEFAULT_TURN_WAIT_FOR_TRANSCRIPT,
    DEFAULT_USER_SPEECH_TIMEOUT,
    DEFAULT_VAD_CONFIDENCE,
    DEFAULT_VAD_MIN_VOLUME,
    DEFAULT_VAD_START_SECS,
    DEFAULT_VAD_STOP_SECS,
)
from loguru import logger

from pipecat.audio.vad.vad_analyzer import VADParams
from pipecat.turns.user_turn_completion_mixin import UserTurnCompletionConfig


@dataclass(frozen=True)
class ReglagesTourDeParole:
    """The turn-taking settings of one agent, resolved against the defaults."""

    user_speech_timeout: float
    stt_ttfs_p99_latency: float | None
    wait_for_transcript: bool
    use_interim: bool
    vad_confidence: float
    vad_start_secs: float
    vad_stop_secs: float
    vad_min_volume: float
    smart_turn_pre_speech_ms: float
    smart_turn_max_duration_secs: float
    audio_idle_timeout: float
    filter_incomplete_user_turns: bool
    incomplete_short_timeout: float
    incomplete_long_timeout: float

    def parametres_detecteur(self) -> VADParams:
        """The voice detector parameters, for BOTH places it is built."""
        return VADParams(
            confidence=self.vad_confidence,
            start_secs=self.vad_start_secs,
            stop_secs=self.vad_stop_secs,
            min_volume=self.vad_min_volume,
        )

    def configuration_de_fin_de_tour(self) -> UserTurnCompletionConfig | None:
        """The model-judged end of turn config, or None when it is off.

        ⛔ None, not a config with the feature disabled inside it: Pipecat
        reads the config only when ``filter_incomplete_user_turns`` is on, and
        handing one over while the switch is off would suggest a behaviour
        that never runs.

        ⚠️ The follow-up prompts Pipecat sends are in English and are NOT
        exposed here. The switch is off by default; if a bench keeps it, the
        prompts join the idle-prompt lot in a later patch.
        """
        if not self.filter_incomplete_user_turns:
            return None
        return UserTurnCompletionConfig(
            incomplete_short_timeout=self.incomplete_short_timeout,
            incomplete_long_timeout=self.incomplete_long_timeout,
        )


def _nombre(run_configs: dict, cle: str, defaut: float) -> float:
    valeur = run_configs.get(cle)
    return defaut if valeur is None else float(valeur)


def _booleen(run_configs: dict, cle: str, defaut: bool) -> bool:
    valeur = run_configs.get(cle)
    return defaut if valeur is None else bool(valeur)


def collecter_reglages_tour_de_parole(
    run_configs: dict | None,
) -> ReglagesTourDeParole:
    """Read an agent's turn-taking settings, falling back to today's values.

    ⛔ ``None`` is treated as "not filled in", not as a value. Stored
    configurations carry explicit JSON nulls for keys the client never
    touched, so reading them literally would hand ``None`` to Pipecat where a
    number is expected -- and the failure would surface mid-call, not here.
    """
    run_configs = run_configs or {}
    latence = run_configs.get("stt_ttfs_p99_latency")
    return ReglagesTourDeParole(
        user_speech_timeout=_nombre(
            run_configs, "user_speech_timeout", DEFAULT_USER_SPEECH_TIMEOUT
        ),
        # ⛔ Stays None when unset: None means "use the value Pipecat measured
        # for this provider", which is not a number we can name here.
        stt_ttfs_p99_latency=None if latence is None else float(latence),
        wait_for_transcript=_booleen(
            run_configs, "turn_wait_for_transcript", DEFAULT_TURN_WAIT_FOR_TRANSCRIPT
        ),
        use_interim=_booleen(
            run_configs, "turn_start_use_interim", DEFAULT_TURN_START_USE_INTERIM
        ),
        vad_confidence=_nombre(run_configs, "vad_confidence", DEFAULT_VAD_CONFIDENCE),
        vad_start_secs=_nombre(run_configs, "vad_start_secs", DEFAULT_VAD_START_SECS),
        vad_stop_secs=_nombre(run_configs, "vad_stop_secs", DEFAULT_VAD_STOP_SECS),
        vad_min_volume=_nombre(run_configs, "vad_min_volume", DEFAULT_VAD_MIN_VOLUME),
        smart_turn_pre_speech_ms=_nombre(
            run_configs, "smart_turn_pre_speech_ms", DEFAULT_SMART_TURN_PRE_SPEECH_MS
        ),
        smart_turn_max_duration_secs=_nombre(
            run_configs,
            "smart_turn_max_duration_secs",
            DEFAULT_SMART_TURN_MAX_DURATION_SECS,
        ),
        audio_idle_timeout=_nombre(
            run_configs, "audio_idle_timeout", DEFAULT_AUDIO_IDLE_TIMEOUT
        ),
        filter_incomplete_user_turns=_booleen(
            run_configs,
            "filter_incomplete_user_turns",
            DEFAULT_FILTER_INCOMPLETE_USER_TURNS,
        ),
        incomplete_short_timeout=_nombre(
            run_configs, "incomplete_short_timeout", DEFAULT_INCOMPLETE_SHORT_TIMEOUT
        ),
        incomplete_long_timeout=_nombre(
            run_configs, "incomplete_long_timeout", DEFAULT_INCOMPLETE_LONG_TIMEOUT
        ),
    )


def appliquer_latence_de_transcription(service_stt, latence: float | None):
    """Apply the agent's transcription-latency setting to the STT service.

    Why here, and after construction rather than through the constructor:
    ``ttfs_p99_latency`` is a ``STTService`` argument, and the factory has
    roughly twenty provider branches. Threading one more keyword through all
    of them is the branch-by-branch shape this patch exists to remove -- and
    the branch added next month would get none of it.

    ⛔ Left alone when the agent filled in nothing: the value Pipecat measured
    for that provider (0.35 s for Deepgram) is the behaviour of today, and
    there is no number we could write here that would reproduce it for every
    provider at once.

    ⛔ Left alone, with a line in the log, when the service does not have a
    meaningful latency of its own (Deepgram Flux, Cartesia ink-2): the server
    decides the turn boundary there, Pipecat reports 0, and writing a value
    would claim a wait that never happens. The screen hides the whole section
    in that case, so this is a second net, not the first one.
    """
    if latence is None or service_stt is None:
        return service_stt
    if not getattr(service_stt, "supports_ttfs", False):
        logger.info(
            "[.mark] stt_ttfs_p99_latency ignored: this transcription service "
            "defines the turn boundary itself, so the pipeline waits for no "
            "extra latency after speech stops."
        )
        return service_stt
    service_stt._ttfs_p99_latency = latence
    return service_stt
