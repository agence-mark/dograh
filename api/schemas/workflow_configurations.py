from typing import Annotated, Literal

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    StringConstraints,
    field_validator,
    model_validator,
)

from api.constants import (
    MAX_TEXT_CHAT_INACTIVITY_TIMEOUT_SECONDS,
    MIN_TEXT_CHAT_INACTIVITY_TIMEOUT_SECONDS,
    TEXT_CHAT_INACTIVITY_TIMEOUT_SECONDS,
)

DEFAULT_MAX_CALL_DURATION_SECONDS = 300
# Hard ceiling on configurable call duration. Must stay <= the concurrency
# rate limiter's stale_call_timeout (20 min): a call running past that has
# its slot purged as stale and the org concurrency limit under-counts.
MAX_CALL_DURATION_SECONDS = 1200
DEFAULT_MAX_USER_IDLE_TIMEOUT_SECONDS = 10.0
DEFAULT_SMART_TURN_STOP_SECS = 2.0
DEFAULT_TURN_START_STRATEGY = "default"
DEFAULT_TURN_START_MIN_WORDS = 3
DEFAULT_PROVISIONAL_VAD_PAUSE_SECS = 1.5
DEFAULT_TURN_STOP_STRATEGY = "transcription"
DEFAULT_CONTEXT_COMPACTION_ENABLED = False

# [.mark] Pipecat settings this fork exposes on the agent.
#
# 🔒 Every default below reproduces the value hardcoded in the pipeline TODAY.
# An agent that fills in nothing is built exactly as it was before this patch.
# The A/B benches choose the values; a later patch moves the defaults.
#
# ⛔ The markdown filter is not installed today, so its default is OFF -- even
# though asterisks read aloud are the very reason it is exposed. Turning it on
# for everyone would be choosing a value, which is not this patch's job: it is
# turned on per agent, starting with the bench agent.
DEFAULT_TTS_MARKDOWN_FILTER_ENABLED = False

# --- Turn taking -----------------------------------------------------------
#
# 🔑 These constants are the SINGLE source of the values the pipeline runs
# with: `run_pipeline.py` reads them, and carries no literal of its own any
# more. Before this patch each of them was a literal in the pipeline, or a
# Pipecat default nobody had ever looked at.
#
# ⚠️ Their values are Pipecat's current defaults, copied here on purpose
# rather than imported. `test_reglages_pipecat_tour_de_parole.py` compares the
# two, so the day a Pipecat upgrade moves a default the test goes red and the
# change gets decided rather than absorbed in silence.
DEFAULT_USER_SPEECH_TIMEOUT = 0.6
DEFAULT_TURN_WAIT_FOR_TRANSCRIPT = True
DEFAULT_TURN_START_USE_INTERIM = True
DEFAULT_VAD_CONFIDENCE = 0.7
DEFAULT_VAD_START_SECS = 0.2
DEFAULT_VAD_STOP_SECS = 0.2
DEFAULT_VAD_MIN_VOLUME = 0.6
DEFAULT_SMART_TURN_PRE_SPEECH_MS = 500.0
DEFAULT_SMART_TURN_MAX_DURATION_SECS = 8.0
DEFAULT_AUDIO_IDLE_TIMEOUT = 1.0
DEFAULT_FILTER_INCOMPLETE_USER_TURNS = False
DEFAULT_INCOMPLETE_SHORT_TIMEOUT = 5.0
DEFAULT_INCOMPLETE_LONG_TIMEOUT = 10.0
# 🔒 No filter, which is today's behaviour. RNNoise is installed but off:
# a noise filter can get in the transcription's way as easily as it helps,
# and that is judged on a real phone line.
DEFAULT_AUDIO_IN_NOISE_FILTER = "none"

# --- Idle prompts ----------------------------------------------------------
#
# ⚠️ These two texts are the ones the pipeline sends TODAY, in English, copied
# verbatim. They are INSTRUCTIONS handed to the model, not sentences spoken as
# written: the model answers in the caller's language.
DEFAULT_USER_IDLE_PROMPT = (
    "The user has been quiet. Politely and briefly ask if they're still there "
    "in the language that the user has been speaking so far."
)
DEFAULT_USER_IDLE_GOODBYE_PROMPT = (
    "The user has been quiet. We will be disconnecting the call now. Wish them "
    "a good day in the language that the user has been speaking so far."
)
# One prompt, then the goodbye and the hang-up: today's behaviour.
DEFAULT_USER_IDLE_MAX_PROMPTS = 1

# --- Voice ------------------------------------------------------------------
#
# 🚨 Measured on 2026-09-14, and it changes what this lot could expose:
# ``silence_time_s=1.0`` is passed on sixteen of the seventeen voice branches
# and has NO EFFECT AT ALL. Pipecat only pushes that silence when
# ``push_silence_after_stop`` is True, and nothing in Dograh -- or in Pipecat
# itself -- ever sets it. So the duration alone would be a setting that does
# nothing: worse than no setting, because someone would raise it, hear no
# change, and stop trusting the screen.
#
# 🔒 The switch is therefore exposed WITH the duration, and it is OFF by
# default -- which is exactly today's behaviour, since the silence is not
# pushed today either.
DEFAULT_TTS_PUSH_SILENCE_AFTER_STOP = False
DEFAULT_TTS_SILENCE_TIME_S = 1.0
DEFAULT_TTS_TEXT_AGGREGATION_MODE = "sentence"

# --- Muting the caller's microphone -----------------------------------
#
# The three that run today, and the two Pipecat offers that Dograh never
# built. 🔒 Defaults reproduce today exactly: three on, two off.
DEFAULT_MUTE_UNTIL_FIRST_BOT_COMPLETE = True
DEFAULT_MUTE_DURING_FUNCTION_CALL = True
DEFAULT_MUTE_ENGINE_CALLBACK = True
DEFAULT_MUTE_FIRST_SPEECH = False
DEFAULT_MUTE_ALWAYS = False
MAX_CALL_DISPOSITIONS = 50
MAX_CALL_DISPOSITION_CODE_LENGTH = 64
MAX_CALL_DISPOSITION_DESCRIPTION_LENGTH = 1_000
MAX_CALL_DISPOSITION_DESCRIPTIONS_TOTAL_LENGTH = 4_000


class CallDispositionOption(BaseModel):
    """One business outcome the terminal classifier may select."""

    code: str = Field(
        min_length=1,
        max_length=MAX_CALL_DISPOSITION_CODE_LENGTH,
        pattern=r"^[A-Za-z][A-Za-z0-9_-]*$",
        description="Stable code recorded when this outcome is selected.",
    )
    description: str = Field(
        min_length=1,
        max_length=MAX_CALL_DISPOSITION_DESCRIPTION_LENGTH,
        description="Business criteria for selecting this disposition.",
    )

    @field_validator("code", "description", mode="before")
    @classmethod
    def strip_text(cls, value: object) -> object:
        return value.strip() if isinstance(value, str) else value


DEFAULT_CALL_DISPOSITION_OPTIONS: tuple[CallDispositionOption, ...] = (
    CallDispositionOption(
        code="qualified",
        description="The call achieved the workflow's primary goal.",
    ),
    CallDispositionOption(
        code="not_interested",
        description="The person clearly declined the offer or said they are not interested.",
    ),
    CallDispositionOption(
        code="wrong_number",
        description="The call reached the wrong person or an incorrect phone number.",
    ),
    CallDispositionOption(
        code="voicemail_detected",
        description="The call reached voicemail or an answering machine instead of a person.",
    ),
    CallDispositionOption(
        code="do_not_call",
        description="The person explicitly asked not to be contacted again.",
    ),
    CallDispositionOption(
        code="callback_requested",
        description="The person asked to be contacted again at a later time.",
    ),
)


def get_default_call_disposition_options() -> list[CallDispositionOption]:
    """Return fresh copies of the built-in terminal outcome catalog."""
    return [option.model_copy(deep=True) for option in DEFAULT_CALL_DISPOSITION_OPTIONS]


class ExternalPBXFieldMapping(BaseModel):
    """Map one gathered-context value to a provider-native field."""

    context_path: str = Field(min_length=1, max_length=255)
    destination_field: str = Field(pattern=r"^[A-Za-z][A-Za-z0-9_]{0,63}$")

    @field_validator("context_path", mode="before")
    @classmethod
    def strip_context_path(cls, value: object) -> object:
        return value.strip() if isinstance(value, str) else value

    @field_validator("destination_field", mode="before")
    @classmethod
    def strip_destination_field(cls, value: object) -> object:
        return value.strip() if isinstance(value, str) else value


# Extra lead fields to capture from the inbound INVITE, named without the
# provider's header prefix (``first_name`` -> ``X-VICIDIAL-first_name``). Each
# entry costs one ARI round trip during call setup, so the set is configured
# explicitly per workflow rather than enumerated off the INVITE.
MAX_EXTERNAL_PBX_LEAD_HEADERS = 50

ExternalPBXLeadHeader = Annotated[
    str, StringConstraints(pattern=r"^[A-Za-z][A-Za-z0-9_]{0,63}$")
]


class AmbientNoiseConfigurationDefaults(BaseModel):
    model_config = ConfigDict(extra="allow")

    enabled: bool = False
    volume: float = 0.3


class WorkflowConfigurationDefaults(BaseModel):
    model_config = ConfigDict(extra="allow")

    @model_validator(mode="before")
    @classmethod
    def _treat_null_as_unset(cls, data):
        # Stored configs (and older clients) carry explicit JSON nulls for
        # keys the user never configured; dropping them lets the field
        # defaults apply instead of failing validation.
        if isinstance(data, dict):
            return {k: v for k, v in data.items() if v is not None}
        return data

    ambient_noise_configuration: AmbientNoiseConfigurationDefaults = Field(
        default_factory=AmbientNoiseConfigurationDefaults
    )
    max_call_duration: int = Field(
        default=DEFAULT_MAX_CALL_DURATION_SECONDS,
        gt=0,
        le=MAX_CALL_DURATION_SECONDS,
    )
    max_user_idle_timeout: float = DEFAULT_MAX_USER_IDLE_TIMEOUT_SECONDS
    smart_turn_stop_secs: float = DEFAULT_SMART_TURN_STOP_SECS
    turn_start_strategy: Literal["default", "min_words", "provisional_vad"] = (
        DEFAULT_TURN_START_STRATEGY
    )
    turn_start_min_words: int = DEFAULT_TURN_START_MIN_WORDS
    provisional_vad_pause_secs: float = DEFAULT_PROVISIONAL_VAD_PAUSE_SECS
    turn_stop_strategy: Literal["transcription", "turn_analyzer"] = (
        DEFAULT_TURN_STOP_STRATEGY
    )
    dictionary: str = ""
    context_compaction_enabled: bool = DEFAULT_CONTEXT_COMPACTION_ENABLED
    # --- Turn taking. Every default reproduces today's behaviour. ---
    #
    # ⚠️ These settings have no effect when the transcription service drives
    # the turns itself (Deepgram Flux, Cartesia ink-2) or in realtime mode:
    # the pipeline does not build these strategies at all. The screen hides
    # the whole section in that case rather than showing values that play no
    # part.
    user_speech_timeout: float = Field(
        default=DEFAULT_USER_SPEECH_TIMEOUT,
        gt=0,
        le=10,
        description=(
            "Seconds the caller may pause before the agent takes the floor. "
            "The single setting that most decides whether the agent cuts "
            "people off or leaves a silence. Pipecat has never had a screen "
            "for it: 0.6 s is its own default, chosen by nobody here."
        ),
    )
    stt_ttfs_p99_latency: float | None = Field(
        default=None,
        gt=0,
        le=10,
        description=(
            "Seconds the pipeline allows the transcription to deliver its "
            "final text after the caller stops. Empty means the value Pipecat "
            "measured for the provider (0.35 s for Deepgram). ⚠️ That "
            "measurement was taken with a voice detector set to 0.2 s: change "
            "the detector below without this, and the end of turn is wrong."
        ),
    )
    user_turn_stop_timeout: float = Field(
        default=5.0,
        gt=0,
        le=60,
        description=(
            "Hard ceiling on the wait for a transcript before the turn ends "
            "anyway. Read by the pipeline since before this patch, but it was "
            "on no schema and no screen."
        ),
    )
    turn_wait_for_transcript: bool = Field(
        default=DEFAULT_TURN_WAIT_FOR_TRANSCRIPT,
        description=(
            "Require at least one transcript before ending the caller's turn. "
            "Turn it off and the agent answers on silence alone, faster but "
            "on nothing that was understood."
        ),
    )
    turn_start_use_interim: bool = Field(
        default=DEFAULT_TURN_START_USE_INTERIM,
        description=(
            "Let partial transcripts, not just final ones, confirm that the "
            "caller has started speaking."
        ),
    )
    # ⚠️ Silero's own bounds: confidence and min_volume are normalised 0-1.
    # ⛔ The two durations carry no bound at the source; the wide range below
    # is ours and is flagged as such in the description rather than passed off
    # as Pipecat's.
    vad_confidence: float = Field(
        default=DEFAULT_VAD_CONFIDENCE,
        ge=0,
        le=1,
        description=(
            "How sure the voice detector must be that it is hearing speech. "
            "Higher misses quiet speech; lower takes background noise for a "
            "caller."
        ),
    )
    vad_start_secs: float = Field(
        default=DEFAULT_VAD_START_SECS,
        gt=0,
        le=5,
        description=(
            "Seconds of sound before the detector calls it speech. Range is "
            "ours: Pipecat sets no bound."
        ),
    )
    vad_stop_secs: float = Field(
        default=DEFAULT_VAD_STOP_SECS,
        gt=0,
        le=5,
        description=(
            "Seconds of silence before the detector calls the speech over. "
            "⚠️ Tied to the transcription latency above, which was measured "
            "at 0.2 s. Range is ours: Pipecat sets no bound."
        ),
    )
    vad_min_volume: float = Field(
        default=DEFAULT_VAD_MIN_VOLUME,
        ge=0,
        le=1,
        description="Volume below which sound is not considered speech.",
    )
    smart_turn_pre_speech_ms: float = Field(
        default=DEFAULT_SMART_TURN_PRE_SPEECH_MS,
        ge=0,
        le=5000,
        description=(
            "Milliseconds of audio kept before the caller starts speaking, "
            "for the Smart Turn model. Only used when end of turn is set to "
            "Smart Turn."
        ),
    )
    smart_turn_max_duration_secs: float = Field(
        default=DEFAULT_SMART_TURN_MAX_DURATION_SECS,
        gt=0,
        le=60,
        description=(
            "Longest audio segment the Smart Turn model examines. Only used "
            "when end of turn is set to Smart Turn."
        ),
    )
    audio_idle_timeout: float = Field(
        default=DEFAULT_AUDIO_IDLE_TIMEOUT,
        ge=0,
        le=30,
        description=(
            "Seconds without any audio at all before the caller is considered "
            "to have stopped speaking, for instance if they mute their "
            "microphone mid-sentence. 0 disables it."
        ),
    )
    filter_incomplete_user_turns: bool = Field(
        default=DEFAULT_FILTER_INCOMPLETE_USER_TURNS,
        description=(
            "Ask the model itself whether the caller has finished their "
            "sentence. ⚠️ Off by default: it costs one extra model call per "
            "turn, and it has not been checked against Mistral. Its follow-up "
            "prompts are in English in Pipecat and are not exposed yet."
        ),
    )
    incomplete_short_timeout: float = Field(
        default=DEFAULT_INCOMPLETE_SHORT_TIMEOUT,
        gt=0,
        le=60,
        description=(
            "Seconds before prompting when the model judged the caller was "
            "cut off mid-sentence. Only used when the setting above is on."
        ),
    )
    incomplete_long_timeout: float = Field(
        default=DEFAULT_INCOMPLETE_LONG_TIMEOUT,
        gt=0,
        le=120,
        description=(
            "Seconds before prompting when the model judged the caller asked "
            "for time to think. Only used when the setting above is on."
        ),
    )
    user_idle_prompt: str = Field(
        default=DEFAULT_USER_IDLE_PROMPT,
        max_length=2000,
        description=(
            "What the agent is told to do when the caller goes quiet. ⚠️ An "
            "instruction given to the model, not a sentence spoken word for "
            "word: the model answers in the caller's language."
        ),
    )
    user_idle_goodbye_prompt: str = Field(
        default=DEFAULT_USER_IDLE_GOODBYE_PROMPT,
        max_length=2000,
        description=(
            "What the agent is told to do on the last prompt, just before the "
            "call is hung up. Same thing: an instruction, not a script."
        ),
    )
    user_idle_max_prompts: int = Field(
        default=DEFAULT_USER_IDLE_MAX_PROMPTS,
        ge=0,
        le=10,
        description=(
            "How many times the agent checks whether the caller is still "
            "there before saying goodbye and hanging up. 0 hangs up on the "
            "first silence, with the goodbye."
        ),
    )
    audio_in_noise_filter: Literal["none", "rnnoise"] = Field(
        default=DEFAULT_AUDIO_IN_NOISE_FILTER,
        description=(
            "Clean the caller's audio before it is transcribed. RNNoise is "
            "free and runs locally. ⚠️ A noise filter can just as easily get "
            "in the transcription's way: it is judged on a real phone line, "
            "not on a browser call."
        ),
    )
    mute_until_first_bot_complete: bool = Field(
        default=DEFAULT_MUTE_UNTIL_FIRST_BOT_COMPLETE,
        description=(
            "Keep the caller from interrupting the agent's opening sentence. "
            "On until now, and this is the one that keeps a greeting from "
            "being cut in half by a hello."
        ),
    )
    mute_during_function_call: bool = Field(
        default=DEFAULT_MUTE_DURING_FUNCTION_CALL,
        description=(
            "Keep the caller from interrupting while the agent is running a "
            "tool, such as a transfer or a lookup."
        ),
    )
    mute_engine_callback: bool = Field(
        default=DEFAULT_MUTE_ENGINE_CALLBACK,
        description=(
            "Follow the workflow's own rule about which nodes may be "
            "interrupted. ⚠️ Turning it off ignores every 'do not interrupt' "
            "set on a node, and does it silently."
        ),
    )
    mute_first_speech: bool = Field(
        default=DEFAULT_MUTE_FIRST_SPEECH,
        description=(
            "Keep the caller from interrupting during the agent's very first "
            "utterance. Narrower than the first setting above, and never used "
            "until now."
        ),
    )
    mute_always: bool = Field(
        default=DEFAULT_MUTE_ALWAYS,
        description=(
            "The caller can never interrupt the agent at all. ⚠️ On a phone "
            "call this is usually the wrong answer: someone who has to wait "
            "out a whole answer hangs up."
        ),
    )
    tts_push_silence_after_stop: bool = Field(
        default=DEFAULT_TTS_PUSH_SILENCE_AFTER_STOP,
        description=(
            "Add a moment of silence after the agent finishes speaking. Off "
            "today, which is why the duration below currently changes "
            "nothing. Useful where a phone line clips the last syllable."
        ),
    )
    tts_silence_time_s: float = Field(
        default=DEFAULT_TTS_SILENCE_TIME_S,
        ge=0,
        le=10,
        description=(
            "How long that silence lasts. ⚠️ Only used when the switch above "
            "is on."
        ),
    )
    tts_text_aggregation_mode: Literal["sentence", "token"] = Field(
        default=DEFAULT_TTS_TEXT_AGGREGATION_MODE,
        description=(
            "Send the text to the voice sentence by sentence, or word by word "
            "as the model writes it. Word by word answers sooner, but it can "
            "degrade the voice depending on the provider: judge it by ear."
        ),
    )
    tts_replacements: list[str] = Field(
        default_factory=list,
        max_length=200,
        description=(
            "Words the voice mispronounces, written as heard:spoken -- for "
            "instance SAV:S. A. V. Matched literally, not as a pattern, and "
            "applied to the text sent to the voice only: the conversation "
            "history keeps the original."
        ),
    )
    tts_markdown_filter_enabled: bool = Field(
        default=DEFAULT_TTS_MARKDOWN_FILTER_ENABLED,
        description=(
            "Strip markdown formatting before the text reaches the voice. "
            "Without it, a model that answers with **bold** has the asterisks "
            "read out loud. Does not touch parentheses: a stage direction like "
            "(one moment) is still spoken, and stays a matter for the prompt."
        ),
    )
    call_dispositions: list[CallDispositionOption] = Field(
        default_factory=list,
        max_length=MAX_CALL_DISPOSITIONS,
        description=(
            "Allowed business outcomes for terminal call classification. Each "
            "entry defines the exact stored code and the criteria for selecting it."
        ),
    )
    text_chat_inactivity_timeout_seconds: int = Field(
        default=TEXT_CHAT_INACTIVITY_TIMEOUT_SECONDS,
        ge=MIN_TEXT_CHAT_INACTIVITY_TIMEOUT_SECONDS,
        le=MAX_TEXT_CHAT_INACTIVITY_TIMEOUT_SECONDS,
    )
    external_pbx_field_mappings: list[ExternalPBXFieldMapping] = Field(
        default_factory=list,
        max_length=100,
    )
    external_pbx_lead_headers: list[ExternalPBXLeadHeader] = Field(
        default_factory=list,
        max_length=MAX_EXTERNAL_PBX_LEAD_HEADERS,
    )

    @field_validator("call_dispositions")
    @classmethod
    def validate_call_dispositions(
        cls, value: list[CallDispositionOption]
    ) -> list[CallDispositionOption]:
        seen: set[str] = set()
        for option in value:
            normalized_code = option.code.casefold()
            if normalized_code in seen:
                raise ValueError("call disposition codes must be unique")
            seen.add(normalized_code)

        total_description_length = sum(len(option.description) for option in value)
        if total_description_length > MAX_CALL_DISPOSITION_DESCRIPTIONS_TOTAL_LENGTH:
            raise ValueError(
                "call disposition descriptions must total at most "
                f"{MAX_CALL_DISPOSITION_DESCRIPTIONS_TOTAL_LENGTH} characters"
            )
        return value

    @field_validator("external_pbx_lead_headers", mode="before")
    @classmethod
    def strip_lead_headers(cls, value: object) -> object:
        """Trim and de-duplicate while preserving the configured order."""
        if not isinstance(value, list):
            return value
        cleaned: list[str] = []
        for item in value:
            name = item.strip() if isinstance(item, str) else item
            if name and name not in cleaned:
                cleaned.append(name)
        return cleaned


class TextChatInactivityTimeoutConstraints(BaseModel):
    """Backend-owned timeout metadata consumed by generated API clients."""

    default_seconds: int = TEXT_CHAT_INACTIVITY_TIMEOUT_SECONDS
    minimum_seconds: int = MIN_TEXT_CHAT_INACTIVITY_TIMEOUT_SECONDS
    maximum_seconds: int = MAX_TEXT_CHAT_INACTIVITY_TIMEOUT_SECONDS


def get_default_workflow_configurations() -> WorkflowConfigurationDefaults:
    return WorkflowConfigurationDefaults()
