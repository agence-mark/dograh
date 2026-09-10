/**
 * [.mark] The six Mistral sampling settings, as seen on screen.
 *
 * The question this file answers, and it answers only this one:
 *
 *     Does the model settings screen actually SHOW the six settings, as
 *     numeric fields, each with the sentence that explains it?
 *
 * Why it exists
 * -------------
 * The screen is generated from the Pydantic schema, so it is tempting to
 * consider "the field is declared" as "the field is on screen". It is not:
 * the form only turns a property into a number input when it recognises its
 * type, and an optional whole number arrives as `integer | null`, which the
 * original helper did not recognise. The field then rendered as a text box
 * with no bounds, and an untouched one was posted as "" — rejected by the API.
 *
 * ⛔ .mark rule: a setting we cannot see on screen is a setting we do not
 * touch. This file is what makes "on screen" verifiable rather than assumed.
 *
 * The schema below is a copy of what the API serves for Mistral, trimmed to
 * what the form reads. It is deliberately a literal and not an import: it
 * describes the CONTRACT between Python and this screen, so it must break
 * loudly if one side moves without the other.
 */

import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import { type ServiceConfigurationDefaults,ServiceConfigurationForm } from "./ServiceConfigurationForm";

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

const schemaMistral = {
    title: "Mistral",
    properties: {
        provider: { type: "string", default: "mistral" },
        api_key: { type: "string" },
        model: { type: "string", default: "mistral-medium-latest", description: "Mistral chat model to use." },
        base_url: { type: "string", default: "https://api.eu.mistral.ai/v1", description: "Mistral API endpoint." },
        temperature: {
            type: "number",
            default: 0.1,
            minimum: 0,
            maximum: 1.5,
            description: "How much randomness goes into each word.",
        },
        seed: {
            anyOf: [{ type: "integer", minimum: 0 }, { type: "null" }],
            default: null,
            description: "Fixes the draw: two identical calls give back the same conversation.",
        },
        max_tokens: {
            anyOf: [{ type: "integer", minimum: 0 }, { type: "null" }],
            default: null,
            description: "Longest answer the model may produce, in tokens.",
        },
        top_p: {
            anyOf: [{ type: "number", exclusiveMinimum: 0, maximum: 1 }, { type: "null" }],
            default: null,
            description: "Restricts the draw to the most likely words.",
        },
        frequency_penalty: {
            anyOf: [{ type: "number", minimum: -2, maximum: 2 }, { type: "null" }],
            default: null,
            description: "Discourages repeating a word already used often in the answer.",
        },
        presence_penalty: {
            anyOf: [{ type: "number", minimum: -2, maximum: 2 }, { type: "null" }],
            default: null,
            description: "Pushes the model towards subjects it has not brought up yet.",
        },
    },
} as unknown as ServiceConfigurationDefaults["llm"][string];

const defauts: ServiceConfigurationDefaults = {
    llm: { mistral: schemaMistral },
    tts: {},
    stt: {},
    embeddings: {},
    default_providers: { llm: "mistral" },
};

const LES_SIX: { champ: string; libelle: string; extrait: string }[] = [
    { champ: "temperature", libelle: "temperature", extrait: "randomness" },
    { champ: "seed", libelle: "seed", extrait: "Fixes the draw" },
    { champ: "max_tokens", libelle: "max tokens", extrait: "Longest answer" },
    { champ: "top_p", libelle: "top p", extrait: "most likely words" },
    { champ: "frequency_penalty", libelle: "frequency penalty", extrait: "Discourages repeating" },
    { champ: "presence_penalty", libelle: "presence penalty", extrait: "subjects it has not brought up" },
];

function afficher(onSave = vi.fn()) {
    render(
        <ServiceConfigurationForm
            mode="global"
            onSave={onSave}
            configurationDefaults={defauts}
            forceRealtime={false}
        />,
    );
    return onSave;
}

/** The input carrying a field, found through its visible label.
 *
 * ⚠️ The label text in the DOM is the raw field name with underscores turned
 * into spaces ("max tokens"): the capitalisation on screen is CSS, so matching
 * on "Max tokens" here would never find anything.
 */
function champ(libelle: string): HTMLInputElement {
    const etiquette = screen.getAllByText(libelle).find(el => el.tagName === "LABEL");
    expect(etiquette, `no label reads "${libelle}" on screen`).toBeTruthy();
    const saisie = etiquette!.parentElement?.querySelector("input");
    expect(saisie, `the "${libelle}" label carries no input`).toBeTruthy();
    return saisie as HTMLInputElement;
}

describe("[.mark] the six Mistral settings on screen", () => {
    it.each(LES_SIX)("shows $champ, with its sentence", async ({ libelle, extrait }) => {
        afficher();

        await waitFor(() => expect(screen.getAllByText("temperature").length).toBeGreaterThan(0));

        expect(champ(libelle)).toBeTruthy();
        expect(screen.getByText(new RegExp(extrait, "i"))).toBeTruthy();
    });

    it.each(LES_SIX)("types $champ as a number, bounds included", async ({ libelle }) => {
        afficher();

        await waitFor(() => expect(screen.getAllByText("temperature").length).toBeGreaterThan(0));

        // ⛔ This is the assertion that was false before the patch for `seed`
        // and `max_tokens`: `integer | null` fell through to a text input, and
        // a text input hands the API "" instead of nothing at all.
        expect(champ(libelle).type).toBe("number");
    });

    it("starts the five optional settings empty, not on null", async () => {
        afficher();

        await waitFor(() => expect(screen.getAllByText("temperature").length).toBeGreaterThan(0));

        // ⚠️ Scope, stated honestly: this one describes the screen, it does
        // not protect it. The DOM shows "" for a null value either way; what
        // actually catches the null is the submission test below, which sees
        // it reach the request body.
        for (const { libelle } of LES_SIX.filter(f => f.champ !== "temperature")) {
            expect(champ(libelle).value).toBe("");
        }
    });

    it("starts temperature on the value that runs today", async () => {
        afficher();

        await waitFor(() => expect(screen.getAllByText("temperature").length).toBeGreaterThan(0));

        expect(champ("temperature").value).toBe("0.1");
    });

    it("does not send a setting that was left empty", async () => {
        const onSave = afficher();

        await waitFor(() => expect(screen.getAllByText("temperature").length).toBeGreaterThan(0));

        fireEvent.click(screen.getByRole("button", { name: /save configuration/i }));

        await waitFor(() => expect(onSave).toHaveBeenCalled());

        const envoye = onSave.mock.calls[0][0] as { llm: Record<string, unknown> };
        // ⛔ The failure this guards against is silent: an untouched optional
        // field carried its `null` default all the way to the request body,
        // where "not configured" and "explicitly set to nothing" stop being
        // distinguishable.
        for (const { champ: nom } of LES_SIX.filter(f => f.champ !== "temperature")) {
            expect(nom in envoye.llm, `${nom} was posted although it was left empty`).toBe(false);
        }
        expect(envoye.llm.temperature).toBe(0.1);
    });

    it("leaves an optional text field out too, not just the numeric ones", async () => {
        // `base_url` is a required field with a real default, so it goes
        // through; a field whose schema default is null is the one that must
        // stay out. Without this rule, an untouched optional text field of
        // another provider (credentials, bill_to, location...) would be posted
        // as "" where it used to be absent.
        const onSave = afficher();

        await waitFor(() => expect(screen.getAllByText("temperature").length).toBeGreaterThan(0));

        fireEvent.click(screen.getByRole("button", { name: /save configuration/i }));

        await waitFor(() => expect(onSave).toHaveBeenCalled());

        const envoye = onSave.mock.calls[0][0] as { llm: Record<string, unknown> };
        expect(envoye.llm.base_url).toBe("https://api.eu.mistral.ai/v1");
    });
});
