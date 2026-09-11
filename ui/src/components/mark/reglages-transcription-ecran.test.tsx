/**
 * [.mark] The Deepgram transcription settings, as seen on screen.
 *
 * The question this file answers, and it answers only this one:
 *
 *     Does the transcription screen actually SHOW each setting, with the right
 *     control for its type, its bounds, and the sentence that explains it?
 *
 * ⛔ .mark rule: a setting we cannot see on screen is a setting we do not
 * touch. "Declared in the schema" is not "usable on screen" — the chantier of
 * 2026-09-10 declared six fields and two of them rendered wrong. This file is
 * what makes "on screen" verifiable rather than assumed.
 *
 * The schema below is a copy of what the API serves for Deepgram, trimmed to
 * what the form reads. It is deliberately a literal and not an import: it
 * describes the CONTRACT between Python and this screen, so it must break
 * loudly if one side moves without the other. ⚠️ A copy can drift, which is
 * why `test_la_copie_du_schema_de_transcription_dit_la_meme_chose` compares
 * the two from the Python side, field by field.
 */

import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import {
    type ServiceConfigurationDefaults,
    ServiceConfigurationForm,
} from "../ServiceConfigurationForm";

vi.mock("@/context/UserConfigContext", () => ({
    useUserConfig: () => ({ userConfig: null, refreshConfig: vi.fn() }),
}));

vi.stubGlobal(
    "ResizeObserver",
    class {
        observe() { }
        unobserve() { }
        disconnect() { }
    },
);

const MODELES_FLUX = ["flux-general-en", "flux-general-multi"];
const MODELES_KEYWORDS = [
    "nova-2",
    "nova-2-general",
    "nova-2-medical",
    "nova-2-phonecall",
    "nova-2-conversationalai",
    "nova",
    "enhanced",
    "base",
];

const schemaDeepgram = {
    title: "Deepgram",
    properties: {
        provider: { type: "string", default: "deepgram" },
        api_key: { type: "string" },
        model: {
            type: "string",
            default: "nova-3-general",
            examples: ["nova-3-general", "nova-3-medical", "flux-general-en", "flux-general-multi"],
            allow_custom_input: true,
            description: "Deepgram STT model.",
        },
        language: {
            type: "string",
            default: "multi",
            examples: ["multi", "fr", "en"],
            allow_custom_input: true,
            description: "Language code. 'multi' enables Nova-3 auto-detect and omits language hints for Flux multilingual auto-detect.",
        },
        endpointing: {
            anyOf: [{ type: "integer", minimum: 0, maximum: 60000 }, { type: "null" }],
            default: 100,
            hidden_for_models: MODELES_FLUX,
            description: "Silence, in milliseconds, after which Deepgram declares the speech finished. This is the setting that decides when the agent takes the floor, so it caps the responsiveness of the whole chain: too low and the agent cuts the caller off, too high and it leaves a blank. Deepgram's own default is 10 ms; 100 ms is the value that was hardcoded before this field existed. Deepgram also accepts 'false' to switch endpointing off entirely, which this field does not offer.",
        },
        utterance_end_ms: {
            anyOf: [{ type: "integer", minimum: 1000, maximum: 5000 }, { type: "null" }],
            default: null,
            hidden_for_models: MODELES_FLUX,
            description: "Silence, in milliseconds, after which Deepgram emits an end-of-utterance event. From 1000 to 5000. WARNING: requires interim results to be on; without them Deepgram sends nothing. Left empty, no such event is requested, which is today's behaviour.",
        },
        interim_results: {
            anyOf: [{ type: "boolean" }, { type: "null" }],
            default: true,
            hidden_for_models: MODELES_FLUX,
            description: "Sends partial transcriptions as the caller speaks, instead of only the finished sentence. On today by way of the connector's own default, and required by the end-of-utterance setting above.",
        },
        keywords: {
            anyOf: [{ type: "array", items: { type: "string" } }, { type: "null" }],
            default: null,
            models: MODELES_KEYWORDS,
            description: "Words to boost, written 'word' or 'word:intensifier'. NOT supported from nova-3 onwards, where Deepgram replaced it with keyterm prompting — which is what the agent's Dictionary already feeds. Only shown when an older model is selected.",
        },
        punctuate: {
            anyOf: [{ type: "boolean" }, { type: "null" }],
            default: true,
            hidden_for_models: MODELES_FLUX,
            description: "Adds punctuation and capitalisation to the transcript. On today by way of the connector's own default. Required for dictation below to have any effect.",
        },
        smart_format: {
            anyOf: [{ type: "boolean" }, { type: "null" }],
            default: null,
            hidden_for_models: MODELES_FLUX,
            description: "Formats dates, times, phone numbers and amounts for readability. Includes the numerals setting below. Off today by way of the connector's own default.",
        },
        numerals: {
            anyOf: [{ type: "boolean" }, { type: "null" }],
            default: null,
            hidden_for_models: MODELES_FLUX,
            description: "Writes spoken numbers as digits ('twenty three' becomes '23'). Off today by way of the connector's own default.",
        },
        dictation: {
            anyOf: [{ type: "boolean" }, { type: "null" }],
            default: null,
            hidden_for_models: MODELES_FLUX,
            description: "Turns spoken punctuation commands into characters ('comma' becomes ','). WARNING: English only, and has no effect unless punctuation is on. Off today by way of the connector's own default.",
        },
        profanity_filter: {
            anyOf: [{ type: "boolean" }, { type: "null" }],
            default: false,
            hidden_for_models: MODELES_FLUX,
            description: "Replaces or removes coarse language in the transcript. Off is the value that was hardcoded before this field existed: what the caller said reaches the agent as they said it.",
        },
        redact: {
            anyOf: [{ type: "array", items: { type: "string" } }, { type: "null" }],
            default: null,
            hidden_for_models: MODELES_FLUX,
            description: "Removes sensitive information from the transcript before it reaches us. Categories such as pci, pii, phi, numbers, aggressive_numbers, or an individual entity type. WARNING: outside English, only numbers are redacted. Left empty, nothing is redacted, which is today's behaviour.",
        },
        replace: {
            anyOf: [{ type: "array", items: { type: "string" } }, { type: "null" }],
            default: null,
            hidden_for_models: MODELES_FLUX,
            description: "Replacement rules, written 'term heard:term written'. Useful for a trade word the model mishears consistently. One rule per entry; the colon separates the two halves.",
        },
        search: {
            anyOf: [{ type: "array", items: { type: "string" } }, { type: "null" }],
            default: null,
            hidden_for_models: MODELES_FLUX,
            description: "Terms Deepgram reports the position and confidence of, without changing the transcript. WARNING: nothing in the agent reads those results today, so this is an observation aid, not a behaviour.",
        },
        diarize: {
            anyOf: [{ type: "boolean" }, { type: "null" }],
            default: null,
            hidden_for_models: MODELES_FLUX,
            description: "Labels the transcript by speaker. WARNING: Deepgram marks this parameter deprecated in favour of diarize_model, which the connector does not carry; it still works and routes to the v1 diarizer. On a telephone call the agent and the caller are already on separate channels, so there is little to gain.",
        },
        eot_threshold: {
            anyOf: [{ type: "number", minimum: 0.5, maximum: 1 }, { type: "null" }],
            default: 0.7,
            models: MODELES_FLUX,
            description: "Confidence Flux needs before it declares the turn finished. Low means turns end sooner, so the agent answers faster and cuts in more often; high means it waits for a complete sentence. From 0.5 to 1. Deepgram's default is 0.7, which is also the value that was hardcoded before this field existed.",
        },
        eager_eot_threshold: {
            anyOf: [{ type: "number", minimum: 0.3, maximum: 0.9 }, { type: "null" }],
            default: 0.5,
            models: MODELES_FLUX,
            description: "Confidence at which Flux announces the turn is probably about to end, so the answer can be prepared before the caller has actually stopped. From 0.3 to 0.9, and it must stay at or below the threshold above. Deepgram leaves it off by default; 0.5 is the value that was hardcoded before this field existed.",
        },
        eot_timeout_ms: {
            anyOf: [{ type: "integer", minimum: 500, maximum: 60000 }, { type: "null" }],
            default: 3000,
            models: MODELES_FLUX,
            description: "Silence, in milliseconds, after which Flux finishes the turn whatever its confidence. From 500 to 60000. Deepgram's default is 5000; 3000 is the value that was hardcoded before this field existed.",
        },
        language_hints: {
            anyOf: [{ type: "array", items: { type: "string" } }, { type: "null" }],
            default: null,
            models: ["flux-general-multi"],
            examples: ["de", "en", "es", "fr"],
            description: "Languages to bias multilingual detection towards. Only the multilingual Flux model reads them. Left empty, the hint is derived from the language chosen above, which is what happens today; filled in, it replaces that derivation.",
        },
        min_confidence: {
            anyOf: [{ type: "number", minimum: 0, maximum: 1 }, { type: "null" }],
            default: null,
            models: MODELES_FLUX,
            description: "Below this confidence, a finished turn is DROPPED and never reaches the agent, which then hears nothing at all. WARNING: this one is not sent to Deepgram; it is a filter applied on our side to what Deepgram returns. Left empty, nothing is dropped, which is today's behaviour.",
        },
        region: {
            type: "string",
            default: "api.eu.deepgram.com",
            readonly: true,
            description: "The Deepgram region the caller's audio is processed in. Locked on Europe: processing inside the EU is a condition of the offer, not an option, so it is imposed in code and cannot be changed from here or through the API.",
        },
        mip_opt_out: {
            type: "boolean",
            default: true,
            readonly: true,
            description: "Refusal to take part in Deepgram's Model Improvement Program, so no call is used to train their models. Locked on: it is a condition of the offer, not an option. Refusing forfeits a discount, and that is accepted.",
        },
        detect_entities: {
            anyOf: [{ type: "boolean" }, { type: "null" }],
            default: null,
            hidden_for_models: MODELES_FLUX,
            description: "Marks names, dates, amounts and the like in the transcript. WARNING: nothing in the agent reads those markers today. Off by way of the connector's own default.",
        },
    },
} as unknown as ServiceConfigurationDefaults["stt"][string];

const defauts: ServiceConfigurationDefaults = {
    llm: {},
    tts: {},
    stt: { deepgram: schemaDeepgram },
    embeddings: {},
    default_providers: { stt: "deepgram" },
};

/** Field name as the screen writes it: underscores become spaces. */
function libelleDe(champ: string): string {
    return champ.replace(/_/g, " ");
}

const NOMBRES = ["endpointing", "utterance_end_ms"];
const INTERRUPTEURS = [
    "interim_results",
    "punctuate",
    "smart_format",
    "numerals",
    "dictation",
    "profanity_filter",
    "diarize",
    "detect_entities",
];
const LISTES = ["redact", "replace", "search"];

function afficher(modele = "nova-3-general", onSave = vi.fn()) {
    render(
        <ServiceConfigurationForm
            mode="global"
            onSave={onSave}
            configurationDefaults={defauts}
            initialConfig={{ stt: { provider: "deepgram", model: modele } }}
            forceRealtime={false}
        />,
    );
    return onSave;
}

/** Open the Transcriber tab, which is where these settings live.
 *
 * ⚠️ The form opens on the LLM tab, and Radix does not render the content of
 * an inactive tab. Asserting without this click would find nothing and say
 * "the field is missing" when the field is simply one click away.
 */
async function ouvrirLOngletTranscription() {
    const onglet = await waitFor(() =>
        screen.getByRole("tab", { name: /transcriber/i }),
    );
    fireEvent.mouseDown(onglet);
    fireEvent.click(onglet);
}

async function attendreLEcran(champTemoin = "endpointing") {
    await ouvrirLOngletTranscription();
    await waitFor(() =>
        expect(
            screen.queryAllByText(libelleDe(champTemoin)).some(el => el.tagName === "LABEL"),
        ).toBe(true),
    );
}

function bloc(champ: string): HTMLElement {
    const etiquette = screen
        .getAllByText(libelleDe(champ))
        .find(el => el.tagName === "LABEL");
    expect(etiquette, `no label reads "${libelleDe(champ)}" on screen`).toBeTruthy();
    return etiquette!.parentElement as HTMLElement;
}

function estAffiche(champ: string): boolean {
    return screen
        .queryAllByText(libelleDe(champ))
        .some(el => el.tagName === "LABEL");
}

describe("[.mark] the Deepgram transcription settings on screen", () => {
    it.each([...NOMBRES, ...INTERRUPTEURS, ...LISTES])(
        "shows %s, with its sentence",
        async champ => {
            afficher();
            await attendreLEcran();

            expect(estAffiche(champ)).toBe(true);
            // ⚠️ The sentence is looked up INSIDE the field's own block, not
            // across the page: two settings can open on the same words
            // ("Silence, in milliseconds, after which Deepgram..."), and a
            // page-wide search would then find two and fail for the wrong
            // reason.
            const phrase = schemaDeepgram.properties[champ].description as string;
            expect(bloc(champ).textContent).toContain(phrase);
        },
    );

    it.each(NOMBRES)("types %s as a number, bounds included", async champ => {
        afficher();
        await attendreLEcran();

        const saisie = bloc(champ).querySelector("input") as HTMLInputElement;
        expect(saisie.type).toBe("number");
        const bornes = (schemaDeepgram.properties[champ].anyOf as Record<string, unknown>[])[0];
        expect(saisie.min).toBe(String(bornes.minimum));
        expect(saisie.max).toBe(String(bornes.maximum));
    });

    it.each(INTERRUPTEURS)("shows %s as a switch", async champ => {
        afficher();
        await attendreLEcran();

        expect(bloc(champ).querySelector('[role="switch"]')).toBeTruthy();
    });

    it.each(LISTES)("shows %s as a tag field", async champ => {
        afficher();
        await attendreLEcran();

        const saisie = bloc(champ).querySelector("input") as HTMLInputElement;
        expect(saisie).toBeTruthy();
        fireEvent.change(saisie, { target: { value: "un:deux" } });
        fireEvent.keyDown(saisie, { key: "Enter", code: "Enter" });
        expect(bloc(champ).querySelector("[data-etiquette='un:deux']")).toBeTruthy();
    });

    it("starts endpointing on the 100 ms that runs today", async () => {
        afficher();
        await attendreLEcran();

        expect((bloc("endpointing").querySelector("input") as HTMLInputElement).value).toBe("100");
    });

    it("starts the profanity filter off, as it runs today", async () => {
        afficher();
        await attendreLEcran();

        expect(
            bloc("profanity_filter").querySelector('[role="switch"]')?.getAttribute("aria-checked"),
        ).toBe("false");
    });

    it("hides keywords, which nova-3 does not accept", async () => {
        // ⛔ Deepgram replaced keyword boosting with keyterm prompting from
        // nova-3 on. Showing the field there would be a setting filled in,
        // sent, and ignored — the top_k failure again.
        afficher("nova-3-general");
        await attendreLEcran();

        expect(estAffiche("keywords")).toBe(false);
    });

    it("shows keywords when an older model is selected", async () => {
        afficher("nova-2");
        await attendreLEcran("keywords");

        expect(estAffiche("keywords")).toBe(true);
        // 🔴 And the thirteen others STAY, which is the point of gating them by
        // EXCLUSION rather than by a white list of the two dropdown entries.
        // Found by the review of 2026-09-11: a white list hid thirteen settings
        // from a client pinned to an older model — `endpointing` included, the
        // very setting this chantier exists for.
        expect(estAffiche("endpointing")).toBe(true);
        expect(estAffiche("profanity_filter")).toBe(true);
        // The Flux thresholds are still out: they belong to Flux only.
        expect(estAffiche("eot_threshold")).toBe(false);
    });

    it.each(["eot_threshold", "eager_eot_threshold", "eot_timeout_ms", "min_confidence"])(
        "shows %s as a number when a Flux model is chosen",
        async champ => {
            afficher("flux-general-multi");
            await attendreLEcran("eot_threshold");

            const saisie = bloc(champ).querySelector("input") as HTMLInputElement;
            expect(saisie.type).toBe("number");
            const bornes = (schemaDeepgram.properties[champ].anyOf as Record<string, unknown>[])[0];
            expect(saisie.min).toBe(String(bornes.minimum));
            expect(saisie.max).toBe(String(bornes.maximum));
            expect(bloc(champ).textContent).toContain(
                schemaDeepgram.properties[champ].description as string,
            );
        },
    );

    it("starts the three Flux thresholds on the values that run today", async () => {
        afficher("flux-general-multi");
        await attendreLEcran("eot_threshold");

        const valeur = (champ: string) =>
            (bloc(champ).querySelector("input") as HTMLInputElement).value;
        expect(valeur("eot_threshold")).toBe("0.7");
        expect(valeur("eager_eot_threshold")).toBe("0.5");
        expect(valeur("eot_timeout_ms")).toBe("3000");
    });

    it("shows language hints on the multilingual model only", async () => {
        afficher("flux-general-multi");
        await attendreLEcran("eot_threshold");

        expect(estAffiche("language_hints")).toBe(true);
    });

    it("hides language hints on the English Flux model", async () => {
        // Deepgram only reads the hints on flux-general-multi; anywhere else
        // the connector logs a warning and drops them.
        afficher("flux-general-en");
        await attendreLEcran("eot_threshold");

        expect(estAffiche("language_hints")).toBe(false);
    });

    it("keeps the two families apart", async () => {
        // 🔴 The whole point of the model list: fourteen settings belong to
        // the classic connector, five to Flux, and neither set applies to the
        // other. Showing both at once would put twelve dead controls on
        // screen whichever model is chosen.
        afficher("flux-general-multi");
        await attendreLEcran("eot_threshold");

        for (const champ of [...NOMBRES, ...INTERRUPTEURS, ...LISTES]) {
            expect(estAffiche(champ), `${champ} is shown on a Flux model`).toBe(false);
        }
    });

    it("hides the Flux thresholds on a nova-3 model", async () => {
        afficher("nova-3-general");
        await attendreLEcran();

        for (const champ of ["eot_threshold", "eager_eot_threshold", "eot_timeout_ms", "language_hints", "min_confidence"]) {
            expect(estAffiche(champ), `${champ} is shown on nova-3`).toBe(false);
        }
    });

    it("shows the two compliance values, locked", async () => {
        afficher();
        await attendreLEcran();

        const saisie = bloc("region").querySelector("input") as HTMLInputElement;
        expect(saisie.value).toBe("api.eu.deepgram.com");
        expect(saisie.disabled).toBe(true);

        const interrupteur = bloc("mip_opt_out").querySelector('[role="switch"]');
        expect(interrupteur?.getAttribute("aria-checked")).toBe("true");
        expect(interrupteur?.hasAttribute("disabled")).toBe(true);
    });

    it("says WHY the two compliance values are locked, not just that they are", async () => {
        afficher();
        await attendreLEcran();

        // ⛔ "Locked" alone reads as a limitation. The sentence has to say it
        // is a condition of the offer, which is a decision, not a constraint.
        expect(bloc("region").textContent).toContain("condition of the offer");
        expect(bloc("mip_opt_out").textContent).toContain("condition of the offer");
    });

    it("does not post the compliance values", async () => {
        const onSave = afficher();
        await attendreLEcran();

        fireEvent.click(screen.getByRole("button", { name: /save configuration/i }));
        await waitFor(() => expect(onSave).toHaveBeenCalled());

        const envoye = onSave.mock.calls[0][0] as { stt: Record<string, unknown> };
        // The server imposes both whatever arrives, so storing a copy would
        // only create a second place where the truth could drift.
        expect("region" in envoye.stt).toBe(false);
        expect("mip_opt_out" in envoye.stt).toBe(false);
    });

    it("does not offer the agent's Dictionary a second time", async () => {
        // ⛔ `keyterm` is fed by the agent's Dictionary and overwritten on
        // every call. A field here would be filled in, saved, and ignored.
        afficher();
        await attendreLEcran();

        expect(estAffiche("keyterm")).toBe(false);
    });

    it("sends nothing for the settings left untouched", async () => {
        const onSave = afficher();
        await attendreLEcran();

        fireEvent.click(screen.getByRole("button", { name: /save configuration/i }));
        await waitFor(() => expect(onSave).toHaveBeenCalled());

        const envoye = onSave.mock.calls[0][0] as { stt: Record<string, unknown> };
        // ⛔ The four settings that carry a real default are expected to be
        // posted: they are what runs today, written as a field instead of a
        // literal.
        const AVEC_DEFAUT = ["profanity_filter", "interim_results", "punctuate"];
        for (const champ of [...INTERRUPTEURS, ...LISTES, "utterance_end_ms"]) {
            if (AVEC_DEFAUT.includes(champ)) continue;
            expect(
                champ in envoye.stt,
                `${champ} was posted although it was left untouched`,
            ).toBe(false);
        }
        expect(envoye.stt.endpointing).toBe(100);
        expect(envoye.stt.profanity_filter).toBe(false);
        expect(envoye.stt.interim_results).toBe(true);
        expect(envoye.stt.punctuate).toBe(true);
    });
});
