/**
 * [.mark] Does the transcription service decide the turn boundaries itself?
 *
 * Why the screen needs to know
 * ---------------------------
 * When it does (Deepgram Flux, Cartesia ink-2) — or in realtime mode — the
 * pipeline does not build the turn strategies at all: it follows the signals
 * the provider sends. Every turn-taking setting is then inert.
 *
 * 🚨 A setting shown in a state that is not its own is worse than a setting
 * not shown: someone would raise the pause to 1.5 s, hear no difference, and
 * conclude the whole section does nothing. So the section is hidden, with the
 * sentence that says why.
 *
 * ⚠️ The resolution order below mirrors the server's, in
 * `api/services/configuration/ai_model_configuration.py`: a full v2 override
 * on the agent wins outright; otherwise the organization's configuration
 * applies, with the agent's per-service overrides on top. Getting this order
 * wrong would hide the section for an agent that does use these settings, or
 * show it for one that does not.
 */

// Deepgram's turn-based models, as `api/services/configuration/options/deepgram.py`
// lists them. Kept as a literal on purpose: it describes the CONTRACT with the
// backend and must break loudly if one side moves without the other.
export const MODELES_QUI_PILOTENT_LES_TOURS: Record<string, readonly string[]> = {
    deepgram: ["flux-general-en", "flux-general-multi"],
    cartesia: ["ink-2"],
};

interface ConfigurationTranscription {
    provider?: string;
    model?: string;
}

export interface EntreesDeResolution {
    /** The organization's configuration, from `useOrgConfig().userConfig`. */
    organisation?: { stt?: ConfigurationTranscription | null } | null;
    /** The agent's own configuration, where its overrides live. */
    agent?: {
        model_configuration_v2_override?: unknown;
        model_overrides?: { stt?: ConfigurationTranscription | null } | null;
        [key: string]: unknown;
    } | null;
    /** True when the agent runs a realtime model, which owns its own turns. */
    estTempsReel?: boolean;
}

const lireStt = (valeur: unknown): ConfigurationTranscription | null => {
    if (!valeur || typeof valeur !== "object") return null;
    const stt = (valeur as { stt?: unknown }).stt;
    if (!stt || typeof stt !== "object") return null;
    const { provider, model } = stt as ConfigurationTranscription;
    return { provider, model };
};

/** The transcription service an agent actually runs with. */
export const transcriptionEffective = ({
    organisation,
    agent,
}: EntreesDeResolution): ConfigurationTranscription | null => {
    // ⛔ A full v2 override replaces the organization's configuration outright,
    // it is not merged into it — same as the server.
    const v2 = lireStt(agent?.model_configuration_v2_override);
    if (v2) return v2;

    const surcharge = lireStt(agent?.model_overrides);
    const base = lireStt(organisation);
    if (!surcharge && !base) return null;
    return {
        provider: surcharge?.provider ?? base?.provider,
        model: surcharge?.model ?? base?.model,
    };
};

/** True when the turn-taking settings play no part in this agent's calls. */
export const transcriptionPiloteLesTours = (entrees: EntreesDeResolution): boolean => {
    if (entrees.estTempsReel) return true;
    const stt = transcriptionEffective(entrees);
    if (!stt?.provider || !stt.model) return false;
    const modeles = MODELES_QUI_PILOTENT_LES_TOURS[stt.provider];
    return Boolean(modeles?.includes(stt.model));
};
