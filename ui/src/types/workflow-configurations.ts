import type {
    AdresseEtablissement,
    AmbientNoiseConfigurationDefaults,
    CallDispositionOption as GeneratedCallDispositionOption,
    OrganizationAiModelConfigurationV2,
    WorkflowConfigurationDefaults as GeneratedWorkflowConfigurationDefaults,
} from "@/client/types.gen";

export type WorkflowConfigurationDefaults = GeneratedWorkflowConfigurationDefaults;

export type AmbientNoiseConfiguration = Omit<
    AmbientNoiseConfigurationDefaults,
    "enabled" | "volume"
> & {
    enabled: boolean;
    volume: number;
    storage_key?: string;
    storage_backend?: string;
    original_filename?: string;
};

export type TurnStopStrategy = NonNullable<GeneratedWorkflowConfigurationDefaults["turn_stop_strategy"]>;
export type TurnStartStrategy = NonNullable<GeneratedWorkflowConfigurationDefaults["turn_start_strategy"]>;
export const DEFAULT_TURN_START_MIN_WORDS = 3;
export const DEFAULT_TTS_MARKDOWN_FILTER_ENABLED = false;
// [.mark] 🔒 Every Pipecat setting this fork exposes on the agent, at the
// value the pipeline ran with BEFORE the patch.
// ⛔ They must equal the Python constants of `workflow_configurations.py`.
// The screen needs its own copy (the generated client is regenerated
// against a running backend), and two copies drift:
// `test_reglages_pipecat_tour_de_parole.py` is where the drift surfaces.
export const DEFAUTS_PIPECAT = {
    user_speech_timeout: 0.6,
    stt_ttfs_p99_latency: null,
    user_turn_stop_timeout: null,
    turn_wait_for_transcript: true,
    turn_start_use_interim: true,
    vad_confidence: 0.7,
    vad_start_secs: 0.2,
    vad_stop_secs: 0.2,
    vad_min_volume: 0.6,
    smart_turn_pre_speech_ms: 500,
    smart_turn_max_duration_secs: 8,
    audio_idle_timeout: 1,
    filter_incomplete_user_turns: false,
    incomplete_short_timeout: 5,
    incomplete_long_timeout: 10,
    audio_in_noise_filter: 'none',
    // ⚠️ The two English texts the pipeline sends today, verbatim. Translating
    // them here would be choosing a value, for every existing agent at once.
    user_idle_prompt:
        "The user has been quiet. Politely and briefly ask if they're still there in the language that the user has been speaking so far.",
    user_idle_goodbye_prompt:
        "The user has been quiet. We will be disconnecting the call now. Wish them a good day in the language that the user has been speaking so far.",
    user_idle_max_prompts: 1,
    tts_push_silence_after_stop: false,
    tts_silence_time_s: 1,
    tts_text_aggregation_mode: 'sentence',
    tts_replacements: [],
    tts_markdown_filter_enabled: false,
    // [.mark] Eteints par defaut : on les allume a la construction d'un agent
    // client, jamais avant. Aucun agent existant ne change de comportement.
    interdire_nom_appelant: false,
    interdire_civilite_appelant: false,
    mute_until_first_bot_complete: true,
    mute_during_function_call: true,
    mute_engine_callback: true,
    mute_first_speech: false,
    mute_always: false,
    // [.mark] E1 and E2 (decisions of Evan, 25/09/2026): the greeting is not
    // interruptible, 2 words when it is; hang up after 35 s of agent silence.
    accueil_interruptible: false,
    accueil_mots_minimum: 2,
    raccrochage_silence_agent_s: 35,
    conversion_nombres_transcription: false,
    // ⚠️ ON (decision D5 of 2026-09-16): acts only at steps that collect a town.
    verification_communes: true,
    // The names of the extraction variables that get the town check; a final *
    // means "starts with". Same rule as before the setting existed (2026-09-17).
    variables_commune: 'commune, commune_*, adresse*',
    // [.mark] Same kind of setting for the reference reader (fiche au fil de
    // l'eau, lot 2): the rule written in the code until then.
    variables_reference: 'reference*',
    // 🆕 The sounds (espeak-ng) are what the fork runs on today; the two
    // switches (L18 of 2026-09-17) exist to measure what they bring.
    sons_communes: true,
    verification_voies: true,
    lecture_epellation: true,
    // ⚠️ ON (L2 of 2026-09-16): an organization that filled a trade vocabulary
    // wants every agent to use it.
    lexique_metier: true,
    sons_lexique: true,
} as const;

// "provisional_vad" was retired. Definitions saved before then still carry it,
// so map it onto the option the backend now resolves such a value to, rather
// than handing the select a value it has no entry for.
function coerceTurnStartStrategy(value: string): TurnStartStrategy {
    return TURN_START_STRATEGY_OPTIONS.some(o => o.value === value)
        ? (value as TurnStartStrategy)
        : 'default';
}

export const TURN_START_STRATEGY_OPTIONS: Array<{
    value: TurnStartStrategy;
    label: string;
    description: string;
}> = [
    {
        value: 'default',
        label: 'Default',
        description: 'Use the platform default: external STT turn signals when available, otherwise local VAD.',
    },
    {
        value: 'min_words',
        label: 'Minimum words',
        description: 'Wait for a minimum number of transcribed words before interrupting bot speech.',
    },
];

export interface AnswerMessage {
    text?: string;
    recording_id?: string;
    recording_pk?: number;
}

export interface AnswerSupervisorSettings {
    listening_window_ms?: number;
    human_utterance_max_ms?: number;
    machine_utterance_cap_ms?: number;
    classify_budget_ms?: number;
    screening_wait_ms?: number;
    max_screening_rearms?: number;
    voicemail_action?: 'hangup' | 'leave_message';
    voicemail_message?: AnswerMessage;
    screening_message?: AnswerMessage;
}

export interface VoicemailDetectionConfiguration extends AnswerSupervisorSettings {
    enabled: boolean;
    use_workflow_llm: boolean;
    provider?: string;
    model?: string;
    api_key?: string;
    system_prompt?: string;  // Overrides the built-in classifier instructions
}

export const DEFAULT_VOICEMAIL_DETECTION_CONFIGURATION: VoicemailDetectionConfiguration = {
    enabled: false,
    use_workflow_llm: true,
    voicemail_action: 'hangup',
};

export interface TranscriptConfiguration {
    include_end_timestamps: boolean;
}

export interface ExternalPBXFieldMapping {
    context_path: string;
    destination_field: string;
}

export type CallDispositionOption = GeneratedCallDispositionOption;

export const DEFAULT_TRANSCRIPT_CONFIGURATION: TranscriptConfiguration = {
    include_end_timestamps: false,
};

export interface ModelOverrides {
    llm?: {
        provider?: string;
        model?: string;
        api_key?: string;
        [key: string]: unknown;
    };
    tts?: {
        provider?: string;
        model?: string;
        voice?: string;
        api_key?: string;
        [key: string]: unknown;
    };
    stt?: {
        provider?: string;
        model?: string;
        api_key?: string;
        [key: string]: unknown;
    };
    realtime?: {
        provider?: string;
        model?: string;
        voice?: string;
        api_key?: string;
        [key: string]: unknown;
    };
    is_realtime?: boolean;
}

type WorkflowConfigurationBase = Omit<
    GeneratedWorkflowConfigurationDefaults,
    | "ambient_noise_configuration"
    | "max_call_duration"
    | "max_user_idle_timeout"
    | "smart_turn_stop_secs"
    | "turn_start_strategy"
    | "turn_start_min_words"
    | "turn_stop_strategy"
    | "dictionary"
    | "context_compaction_enabled"
    | "tts_cache_enabled"
    | "call_dispositions"
    | "text_chat_inactivity_timeout_seconds"
    | "external_pbx_field_mappings"
    | "external_pbx_lead_headers"
>;

/** [.mark] One field of the agent's call record (`api/schemas/fiche_agent.py`). */
export interface ChampFiche {
    nom: string;
    type: "string" | "number" | "boolean";
    origine: "dicte" | "deduit";
    description: string;
    // Empty (null): deduced from the name, as the server does.
    lecteur: "commune" | "rue" | "date" | "lexique" | "aucun" | null;
    // [.mark] PB3: the only values the field accepts. Empty (null or absent): any.
    valeurs?: string[] | null;
}

/**
 * [.mark] A record field as the server may send it: every key but the name has
 * a default in `api/schemas/fiche_agent.py`, so the generated client types
 * them optional. Completed here with exactly those defaults, so the screen
 * always handles whole fields; a value that is there is never changed.
 */
export const completerChampsFiche = <T,>(
    champs: T,
): T | ChampFiche[] => {
    if (!Array.isArray(champs)) return champs;
    return champs.map((champ: Partial<ChampFiche> & { nom: string }) => ({
        type: "string",
        origine: "dicte",
        description: "",
        lecteur: null,
        ...champ,
    })) as ChampFiche[];
};

export type WorkflowConfigurations = WorkflowConfigurationBase & {
    ambient_noise_configuration: AmbientNoiseConfiguration;
    max_call_duration: number;  // Maximum call duration in seconds
    max_user_idle_timeout: number;  // Maximum user idle time in seconds
    smart_turn_stop_secs: number;  // Timeout in seconds for incomplete turn detection
    turn_start_strategy: TurnStartStrategy;  // Strategy for detecting start of user turn/interruption
    turn_start_min_words: number;  // Minimum transcribed words required for minimum-word interruptions
    turn_stop_strategy: TurnStopStrategy;  // Strategy for detecting end of user turn
    dictionary?: string;  // Comma-separated words for voice agent to listen for
    voicemail_detection?: VoicemailDetectionConfiguration;
    transcript_configuration: TranscriptConfiguration;
    context_compaction_enabled: boolean;  // Summarize context on node transitions to remove stale tool calls
    tts_cache_enabled: boolean;
    call_dispositions: CallDispositionOption[];  // Allowed terminal business outcomes
    text_chat_inactivity_timeout_seconds?: number;  // End inactive text chats after this many seconds
    external_pbx_field_mappings: ExternalPBXFieldMapping[];
    external_pbx_lead_headers: string[];  // Extra lead fields to capture from the inbound INVITE
    model_overrides?: ModelOverrides;  // Per-workflow model configuration overrides
    // [.mark] Opening hours in the readable French format. Empty (null): no
    // opening state is computed at call start, exactly as before.
    horaires_ouverture?: string | null;
    // [.mark] Business address for this agent. Empty (null): the organization's
    // address is used.
    adresse_etablissement?: AdresseEtablissement | null;
    // [.mark] The call record filled by the noter_information tool (fiche au
    // fil de l'eau). Off by default: the tool is not offered at all.
    fiche_au_fil_de_leau?: boolean;
    fiche_champs?: ChampFiche[];
    // [.mark] Pipecat settings this fork exposes on the agent. Every default
    // reproduces the value the pipeline hardcodes TODAY: an agent that fills in
    // nothing behaves exactly as before.
    tts_markdown_filter_enabled: boolean;  // Strip markdown before the text reaches the voice
    tts_push_silence_after_stop: boolean;  // Off until now: the duration below did nothing
    tts_silence_time_s: number;
    tts_text_aggregation_mode: 'sentence' | 'token';
    tts_replacements: string[];  // heard:spoken, matched literally
    interdire_nom_appelant: boolean;  // [.mark] ne jamais PRONONCER le nom de l'appelant
    interdire_civilite_appelant: boolean;  // [.mark] ni sa civilite
    mute_until_first_bot_complete: boolean;
    mute_during_function_call: boolean;
    mute_engine_callback: boolean;
    mute_first_speech: boolean;
    mute_always: boolean;
    accueil_interruptible: boolean;  // [.mark] E1: the caller can cut the greeting
    accueil_mots_minimum: number;  // [.mark] E1: words needed to cut it
    raccrochage_silence_agent_s: number;  // [.mark] E2: agent silence before hanging up
    conversion_nombres_transcription: boolean;  // Dictated numbers reach the model as digits
    verification_communes: boolean;  // Town the caller names checked against the list of communes
    variables_commune: string;  // Extraction variables that trigger it, comma separated, final * = starts with
    variables_reference: string;  // Same, for the reference reader (invoice, quote, order numbers)
    sons_communes: boolean;  // The pronunciation library used to recognise towns
    verification_voies: boolean;  // Street the caller names checked against the streets of their commune
    lecture_epellation: boolean;  // Letters the caller spells out, read and copied exactly
    lexique_metier: boolean;  // The organization's trade vocabulary: listened for, corrected, pronounced
    sons_lexique: boolean;  // The pronunciation library used to recognise the trade names
    user_speech_timeout: number;  // Seconds the caller may pause before the agent answers
    stt_ttfs_p99_latency: number | null;  // Empty = the value Pipecat measured for the provider
    user_turn_stop_timeout: number | null;  // Empty = 5 s, or 30 s in external-turn mode
    turn_wait_for_transcript: boolean;
    turn_start_use_interim: boolean;
    vad_confidence: number;
    vad_start_secs: number;
    vad_stop_secs: number;
    vad_min_volume: number;
    smart_turn_pre_speech_ms: number;
    smart_turn_max_duration_secs: number;
    audio_idle_timeout: number;
    filter_incomplete_user_turns: boolean;
    incomplete_short_timeout: number;
    incomplete_long_timeout: number;
    audio_in_noise_filter: 'none' | 'rnnoise';
    user_idle_prompt: string;
    user_idle_goodbye_prompt: string;
    user_idle_max_prompts: number;
    model_configuration_v2_override?: OrganizationAiModelConfigurationV2;  // Full v2 model configuration override
    [key: string]: unknown;  // Allow additional properties for future configurations
};

const FALLBACK_WORKFLOW_CONFIGURATIONS: WorkflowConfigurations = {
    ambient_noise_configuration: {
        enabled: false,
        volume: 0.3
    },
    max_call_duration: 300,
    max_user_idle_timeout: 10,  // 10 seconds
    smart_turn_stop_secs: 2,  // 2 seconds
    turn_start_strategy: 'default',  // Default to platform-chosen user turn start detection
    turn_start_min_words: DEFAULT_TURN_START_MIN_WORDS,
    turn_stop_strategy: 'transcription',  // Default to transcription-based detection
    dictionary: '',
    transcript_configuration: DEFAULT_TRANSCRIPT_CONFIGURATION,
    context_compaction_enabled: false,
    tts_cache_enabled: false,
    call_dispositions: [],
    external_pbx_field_mappings: [],
    external_pbx_lead_headers: [],
    ...DEFAUTS_PIPECAT,
    // ⛔ Re-stated mutable: DEFAUTS_PIPECAT is `as const` so its empty array
    // is readonly, and the configuration type this fallback feeds is not.
    tts_replacements: [],
};

// ⛔ Mutable: DEFAUTS_PIPECAT is `as const`, so its list default is readonly,
// and the configuration type this feeds is not.
type ReglagesPipecatResolus = {
    -readonly [K in keyof typeof DEFAUTS_PIPECAT]: K extends "tts_replacements"
        ? string[]
        // Free text: its default must not narrow the type to that one literal.
        : K extends "variables_commune" | "variables_reference"
          ? string
          : (typeof DEFAUTS_PIPECAT)[K];
};

function resoudreReglagesPipecat(
    configurations?: Partial<WorkflowConfigurations> | null,
    defaults?: WorkflowConfigurationDefaults | null,
): ReglagesPipecatResolus {
    const resolus = {} as Record<string, unknown>;
    for (const cle of Object.keys(DEFAUTS_PIPECAT)) {
        const surAgent = (configurations as Record<string, unknown> | null | undefined)?.[cle];
        const surOrganisation = (defaults as Record<string, unknown> | null | undefined)?.[cle];
        resolus[cle] =
            surAgent
            ?? surOrganisation
            ?? DEFAUTS_PIPECAT[cle as keyof ReglagesPipecatResolus];
    }
    return resolus as ReglagesPipecatResolus;
}

export function resolveWorkflowConfigurations(
    configurations?: Partial<WorkflowConfigurations> | null,
    defaults?: WorkflowConfigurationDefaults | null,
): WorkflowConfigurations {
    return {
        ...FALLBACK_WORKFLOW_CONFIGURATIONS,
        ...defaults,
        ...configurations,
        ambient_noise_configuration: {
            ...FALLBACK_WORKFLOW_CONFIGURATIONS.ambient_noise_configuration,
            ...defaults?.ambient_noise_configuration,
            ...configurations?.ambient_noise_configuration,
        },
        max_call_duration:
            configurations?.max_call_duration
            ?? defaults?.max_call_duration
            ?? FALLBACK_WORKFLOW_CONFIGURATIONS.max_call_duration,
        max_user_idle_timeout:
            configurations?.max_user_idle_timeout
            ?? defaults?.max_user_idle_timeout
            ?? FALLBACK_WORKFLOW_CONFIGURATIONS.max_user_idle_timeout,
        smart_turn_stop_secs:
            configurations?.smart_turn_stop_secs
            ?? defaults?.smart_turn_stop_secs
            ?? FALLBACK_WORKFLOW_CONFIGURATIONS.smart_turn_stop_secs,
        turn_start_strategy: coerceTurnStartStrategy(
            configurations?.turn_start_strategy
            ?? defaults?.turn_start_strategy
            ?? FALLBACK_WORKFLOW_CONFIGURATIONS.turn_start_strategy,
        ),
        turn_start_min_words:
            configurations?.turn_start_min_words
            ?? defaults?.turn_start_min_words
            ?? FALLBACK_WORKFLOW_CONFIGURATIONS.turn_start_min_words,
        turn_stop_strategy:
            configurations?.turn_stop_strategy
            ?? defaults?.turn_stop_strategy
            ?? FALLBACK_WORKFLOW_CONFIGURATIONS.turn_stop_strategy,
        dictionary:
            configurations?.dictionary
            ?? defaults?.dictionary
            ?? FALLBACK_WORKFLOW_CONFIGURATIONS.dictionary,
        context_compaction_enabled:
            configurations?.context_compaction_enabled
            ?? defaults?.context_compaction_enabled
            ?? FALLBACK_WORKFLOW_CONFIGURATIONS.context_compaction_enabled,
        tts_cache_enabled:
            configurations?.tts_cache_enabled
            ?? defaults?.tts_cache_enabled
            ?? FALLBACK_WORKFLOW_CONFIGURATIONS.tts_cache_enabled,
        call_dispositions:
            configurations?.call_dispositions
            ?? defaults?.call_dispositions
            ?? FALLBACK_WORKFLOW_CONFIGURATIONS.call_dispositions,
        text_chat_inactivity_timeout_seconds:
            configurations?.text_chat_inactivity_timeout_seconds
            ?? defaults?.text_chat_inactivity_timeout_seconds,
        external_pbx_field_mappings:
            configurations?.external_pbx_field_mappings
            ?? defaults?.external_pbx_field_mappings
            ?? FALLBACK_WORKFLOW_CONFIGURATIONS.external_pbx_field_mappings,
        external_pbx_lead_headers:
            configurations?.external_pbx_lead_headers
            // Cast until `npm run generate-client` runs against a backend
            // carrying this field; the generated defaults type predates it.
            ?? (defaults?.external_pbx_lead_headers as string[] | undefined)
            ?? FALLBACK_WORKFLOW_CONFIGURATIONS.external_pbx_lead_headers,
        // [.mark] ⛔ `??`, not a spread: a stored configuration carries explicit
        // JSON nulls for keys the client never touched, and spreading them would
        // draw an empty field where the pipeline runs a value.
        ...resoudreReglagesPipecat(configurations, defaults),
        // [.mark] Same value the spreads above chose, completed field by field.
        fiche_champs: completerChampsFiche(
            { ...defaults, ...configurations }.fiche_champs,
        ) as ChampFiche[] | undefined,
        transcript_configuration: {
            ...DEFAULT_TRANSCRIPT_CONFIGURATION,
            ...(defaults?.transcript_configuration as Partial<TranscriptConfiguration> | undefined),
            ...(configurations?.transcript_configuration as Partial<TranscriptConfiguration> | undefined),
        },
    };
}
