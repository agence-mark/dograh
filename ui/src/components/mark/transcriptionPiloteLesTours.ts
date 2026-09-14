/**
 * [.mark] Does the transcription service decide the turn boundaries itself?
 *
 * Why the screen needs to know
 * ---------------------------
 * When it does (Deepgram Flux, Cartesia ink-2), the pipeline does not build
 * the turn strategies at all: it follows the signals the provider sends, and
 * every turn-taking setting is inert.
 *
 * ⛔ Realtime mode is NOT this case, and an earlier version of this file said
 * it was. Since the patch of 14/09 the voice detector and the pause DO apply
 * to a realtime call -- `_create_realtime_user_turn_config` builds the
 * detector from the agent's settings -- so hiding the whole section there
 * would hide settings that work. (The check was also dead: `is_realtime` is
 * not a root key of the configuration. Both found by the review of 14/09.)
 *
 * ⚠️ But "everything in that section works in realtime" is NOT true either,
 * and saying so plainly matters more than the convenient half of the
 * sentence. FIVE settings are shown to a realtime agent and do nothing:
 * `turn_wait_for_transcript` (forced to false in the pipeline),
 * `turn_start_use_interim` (the realtime start strategy takes no such
 * parameter), the two `smart_turn_*` (no turn analyser is built), and
 * `stt_ttfs_p99_latency` (no transcription service at all). This is not a
 * regression -- they were already shown, the dead check saw to that -- and it
 * costs .mark nothing today, our chain being Deepgram + Mistral + Voxtral
 * rather than realtime. The honest fix is per-setting masking, which belongs
 * to its own patch. Raised by the counter-review of 14/09; question n° 131.
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
    const stt = transcriptionEffective(entrees);
    if (!stt?.provider || !stt.model) return false;
    const modeles = MODELES_QUI_PILOTENT_LES_TOURS[stt.provider];
    return Boolean(modeles?.includes(stt.model));
};
