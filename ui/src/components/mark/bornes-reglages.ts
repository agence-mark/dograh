/**
 * [.mark] The bounds the server enforces, mirrored on the screen.
 *
 * Why this file exists
 * --------------------
 * Every numeric Pipecat setting is bounded in
 * `api/schemas/workflow_configurations.py`. The screen enforced none of them.
 * One spinner arrow too many put a field out of range, the save returned 422,
 * and `handleSave` logged to the console without a toast: no message, no
 * success, "Unsaved changes" still showing. And because the payload carries the
 * WHOLE configuration, that one field also blocked the three other blocks of
 * the card.
 *
 * It stayed harmless only as long as the screen was unreachable. This chantier
 * makes it reachable. On a fork whose lesson of the day is "a setting nobody
 * can see does not exist", a save that fails without saying so is the same
 * family of defect.
 *
 * Why a table rather than `min`/`max` typed into each field
 * --------------------------------------------------------
 * A bound copied by hand into a JSX attribute goes stale the day the schema
 * moves, and it goes stale in silence. `bornes-reglages.test.ts` READS the
 * Python schema and asserts every line below matches it, so a bound that drifts
 * breaks a test instead of breaking a client's save.
 *
 * And why `min`/`max` attributes are not enough on their own: HTML bounds are
 * inclusive, while several of these settings are strictly greater than zero
 * (`gt=0`). The attributes are the hint; `messageHorsBornes` is the check.
 *
 * Three kinds of bound live here, and all three are mirrored: numeric ranges
 * (`BORNES`), text lengths (`LONGUEURS_MAX`) and list sizes
 * (`NOMBRE_MAX_ELEMENTS`). Only the first was there on the first pass. The
 * second came from review -- the two idle-prompt instructions are capped at
 * 2000 characters server-side and nothing said so. The third came from the
 * test written for the second: Pydantic spells both "max_length", but on
 * `list[str]` it counts ITEMS, not characters, and the pronunciation list is
 * capped at 200 entries. Same word, different bound; mixing them would have
 * put `maxLength=200` on a field where it means something else entirely.
 */

export interface Borne {
    /** The lower bound itself. */
    min: number;
    /** True for `gt` (strictly greater), false for `ge` (greater or equal). */
    minStrict: boolean;
    /** The upper bound, always inclusive (`le`) in this schema. */
    max: number;
}

/**
 * One line per numeric setting our sections show, copied from
 * `api/schemas/workflow_configurations.py` and asserted against it.
 */
export const BORNES: Record<string, Borne> = {
    // Turn taking
    user_speech_timeout: { min: 0, minStrict: true, max: 10 },
    stt_ttfs_p99_latency: { min: 0, minStrict: true, max: 10 },
    user_turn_stop_timeout: { min: 0, minStrict: true, max: 60 },
    vad_confidence: { min: 0, minStrict: false, max: 1 },
    vad_start_secs: { min: 0, minStrict: true, max: 5 },
    vad_stop_secs: { min: 0, minStrict: true, max: 5 },
    vad_min_volume: { min: 0, minStrict: false, max: 1 },
    smart_turn_pre_speech_ms: { min: 0, minStrict: false, max: 5000 },
    smart_turn_max_duration_secs: { min: 0, minStrict: true, max: 60 },
    audio_idle_timeout: { min: 0, minStrict: false, max: 30 },
    incomplete_short_timeout: { min: 0, minStrict: true, max: 60 },
    incomplete_long_timeout: { min: 0, minStrict: true, max: 120 },
    // Voice
    tts_silence_time_s: { min: 0, minStrict: false, max: 10 },
    // Idle prompts
    user_idle_max_prompts: { min: 0, minStrict: false, max: 10 },
};

/**
 * The `max_length` the schema puts on our text settings.
 *
 * Unlike the numeric ranges, a text field CAN be bounded by the browser alone
 * (`maxLength` simply stops the typing), so there is no message to show -- but
 * the value still has to be mirrored, and still has to be checked against the
 * schema.
 */
export const LONGUEURS_MAX: Record<string, number> = {
    user_idle_prompt: 2000,
    user_idle_goodbye_prompt: 2000,
    variables_commune: 500,
    variables_reference: 500,
};

/**
 * The most entries a list setting accepts, from the same `max_length` keyword
 * applied to a `list[...]` field -- where Pydantic counts ITEMS.
 */
export const NOMBRE_MAX_ELEMENTS: Record<string, number> = {
    tts_replacements: 200,
};

/** The `maxLength` attribute for a TEXT setting, or nothing when unbounded. */
export const attributDeLongueur = (cle: string): { maxLength?: number } => {
    const longueur = LONGUEURS_MAX[cle];
    return longueur === undefined ? {} : { maxLength: longueur };
};

/**
 * The message to show under a field, or `null` when the value is acceptable.
 *
 * `null` and `undefined` are acceptable on purpose: two of these settings are
 * legitimately empty (`stt_ttfs_p99_latency`, `user_turn_stop_timeout`), and an
 * empty field must not read as an error.
 */
export const messageHorsBornes = (
    cle: string,
    valeur: number | null | undefined,
): string | null => {
    const borne = BORNES[cle];
    if (!borne || valeur === null || valeur === undefined) return null;
    if (Number.isNaN(valeur)) return "Enter a number.";

    const tropBas = borne.minStrict ? valeur <= borne.min : valeur < borne.min;
    if (tropBas) {
        return borne.minStrict
            ? `Must be greater than ${borne.min} (and at most ${borne.max}).`
            : `Must be at least ${borne.min} (and at most ${borne.max}).`;
    }
    if (valeur > borne.max) {
        return `Must be at most ${borne.max}.`;
    }
    return null;
};

/** The HTML attributes for a bounded field. Hint only — the check is above. */
export const attributsDeBorne = (cle: string): { min?: number; max?: number } => {
    const borne = BORNES[cle];
    if (!borne) return {};
    return { min: borne.min, max: borne.max };
};

/**
 * Every out-of-bounds message for a whole block of settings, keyed by setting.
 * Empty object = the block can be saved.
 */
export const messagesHorsBornes = (
    reglages: Record<string, unknown>,
): Record<string, string> => {
    const messages: Record<string, string> = {};
    for (const cle of Object.keys(BORNES)) {
        if (!(cle in reglages)) continue;
        const valeur = reglages[cle];
        if (typeof valeur !== "number" && valeur !== null && valeur !== undefined) continue;
        const message = messageHorsBornes(cle, valeur as number | null | undefined);
        if (message) messages[cle] = message;
    }
    return messages;
};

// [.mark] SABOTAGE VOLONTAIRE (preuve D3, branche jetable) : erreur de type.
export const _sabotageType: number = "pas un nombre";
