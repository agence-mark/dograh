/**
 * [.mark] The shape of a run's analysis, as `GET /workflow/{id}/runs/{run}/analyse` returns it
 * (`api/services/analyse_run/analyse.py`, chantier langwatch-et-fenetre-du-run, lot 1).
 *
 * Every block carries a status: "ok", "not_captured" (the run holds no such data: the screen
 * says so, never "zero") or "unavailable" (the block failed on the server: the screen says so,
 * never an empty card).
 */

export type Statut = "ok" | "not_captured" | "unavailable";

export type Bloc = { status: Statut; reason?: string };

export type NatureDePasse = "reply" | "note" | "transition" | "tool" | "tool_or_transition";

export type TourDeLatence = {
    turn: number | null;
    step: string;
    measured: boolean;
    not_measured_reason: string | null;
    end_of_turn_wait_secs: number | null;
    transcription_secs: number | null;
    passes: { secs: number | null; after: NatureDePasse }[];
    voice_secs: number | null;
    silence_secs: number | null;
    slow: boolean;
    step_change: boolean;
};

export type Latence = Bloc & {
    turns?: TourDeLatence[];
    perceived?: {
        status: Statut;
        count?: number;
        median_secs?: number | null;
        worst_secs?: number | null;
        pairs?: { caller_end_secs: number; agent_start_secs: number; silence_secs: number }[];
    };
    stats?: {
        measured_turns: number;
        total_turns: number;
        median_silence_secs: number | null;
        worst_silence_secs: number | null;
        worst_turn: number | null;
        share_under_threshold: number | null;
        threshold_secs: number;
        median_passes: number | null;
    };
};

export type Resume = Bloc & {
    agent_id?: number;
    definition_id?: number | null;
    channel?: string;
    duration_secs?: number | null;
    disposition?: string | null;
    cost?: Bloc & {
        currency?: string;
        total?: number;
        partial?: boolean;
        rate_dates?: string[];
        unpriced?: { component: string; model: string }[];
    };
    version?: {
        status?: Statut;
        app_version?: string;
        commit?: string | null;
        definition_id?: number | null;
        version_number?: number | null;
        definition_status?: string | null;
    };
    incident_count?: number;
};

type Usage = { service: string; model: string | null; [cle: string]: unknown };

export type Fournisseurs = Bloc & {
    transcription?: { provider?: string; model?: string; usage: (Usage & { seconds?: number })[] };
    model?: {
        provider?: string;
        model?: string;
        note_taking_mode?: string | null;
        transitions_in_reply?: boolean;
        usage: (Usage & { prompt_tokens?: number; cached_tokens?: number; completion_tokens?: number })[];
    };
    voice?: { provider?: string; model?: string; usage: (Usage & { characters?: number })[] };
    call_duration_secs?: number | null;
    model_requests?: {
        status?: Statut;
        refused?: number;
        retries?: number;
        lost_secs?: number;
        by_status?: Record<string, number>;
    };
    connections?: { status?: Statut } & Record<string, { disconnections: number; errors: number } | Statut | undefined>;
};

export type ElementDeModule = {
    module: string;
    caller_turn: number | null;
    step: string | null;
    heard: string | null;
    result: string | null;
    kind: string | null;
    status: string | null;
    by_sound: boolean | null;
    proposals: string[];
};

export type Modules = Bloc & { items?: ElementDeModule[]; modules?: string[] };

export type ChampDeFiche = {
    name: string;
    value: unknown;
    empty: boolean;
    declared: boolean;
    sure: boolean | null;
    source: string | null;
    written_at_caller_turn: number | null;
    history: { caller_turn: number | null; status: string | null; reason: string | null; source: string | null }[];
};

export type Fiche = Bloc & {
    fields?: ChampDeFiche[];
    refusals?: { field: string | null; status: string | null; reason: string | null }[];
};

export type Parcours = Bloc & {
    steps?: string[];
    transitions?: { turn: number | null; from: string | null; to: string | null }[];
    tools?: {
        turn: number | null;
        step: string | null;
        name: string | null;
        kind: NatureDePasse;
        result: unknown;
        finished: boolean;
        duration_secs: number | null;
    }[];
    disposition?: string | null;
    tags?: string[];
};

export type LigneDeConversation = {
    turn: number | null;
    speaker: "caller" | "agent";
    text: string | null;
    start_secs: number | null;
    end_secs: number | null;
};

export type MarqueDeConversation = {
    turn: number | null;
    kind: "caller_interrupted" | "idle_reminder" | "idle_hang_up";
    at_secs: number | null;
};

export type Conversation = Bloc & { lines?: LigneDeConversation[]; marks?: MarqueDeConversation[] };

export type Incident = {
    turn: number | null;
    kind: string;
    fatal: boolean;
    processor: string | null;
    detail: unknown;
};

export type Incidents = Bloc & { items?: Incident[] };

export type AnalyseDuRun = {
    version: number;
    run_id: number;
    summary: Resume;
    latency: Latence;
    providers: Fournisseurs;
    reading_modules: Modules;
    record: Fiche;
    path: Parcours;
    conversation: Conversation;
    incidents: Incidents;
};
