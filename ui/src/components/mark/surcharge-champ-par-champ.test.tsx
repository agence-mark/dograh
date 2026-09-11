/**
 * [.mark] A per-service override that overrides ONE field, not the whole block.
 *
 * The question this file answers, and it answers only this one:
 *
 *     When an agent overrides one setting of a service, does the screen send
 *     only that setting — or the entire service block?
 *
 * Why it exists
 * -------------
 * The whole point of the per-service override is that the agent keeps
 * inheriting from its client. Sending the complete block defeats it in
 * miniature: an agent that changes `endpointing` would also freeze the model,
 * the language and the seventeen other settings at their value of the day, and
 * would stop following its client from that moment on. Nothing on screen would
 * say so.
 *
 * 🔑 The server already merges field by field when the provider is unchanged
 * (`resolve_effective_config`), so sending LESS makes the agent inherit MORE.
 * The fix is entirely on this side.
 *
 * ⛔ And when the provider DOES change, the server rebuilds the section from
 * the override alone — so there the whole block has to go, or the agent would
 * end up with a Deepgram configuration missing everything but one field.
 */

import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import {
    type ServiceConfigurationDefaults,
    ServiceConfigurationForm,
} from "../ServiceConfigurationForm";

// The client's configuration, which the agent inherits from.
const configurationDuClient = {
    stt: {
        provider: "deepgram",
        model: "nova-3-general",
        language: "fr",
        endpointing: 100,
        profanity_filter: false,
    },
};

vi.mock("@/context/UserConfigContext", () => ({
    useUserConfig: () => ({ userConfig: configurationDuClient, refreshConfig: vi.fn() }),
}));

vi.stubGlobal(
    "ResizeObserver",
    class {
        observe() { }
        unobserve() { }
        disconnect() { }
    },
);

const schemaDeepgram = {
    title: "Deepgram",
    properties: {
        provider: { type: "string", default: "deepgram" },
        api_key: { type: "string" },
        model: {
            type: "string",
            default: "nova-3-general",
            examples: ["nova-3-general", "nova-3-medical"],
            description: "Deepgram STT model.",
        },
        language: {
            type: "string",
            default: "multi",
            examples: ["multi", "fr", "en"],
            description: "Language code.",
        },
        endpointing: {
            anyOf: [{ type: "integer", minimum: 0, maximum: 60000 }, { type: "null" }],
            default: 100,
            description: "Silence before the agent takes the floor.",
        },
        profanity_filter: {
            anyOf: [{ type: "boolean" }, { type: "null" }],
            default: false,
            description: "Filters coarse language.",
        },
    },
} as unknown as ServiceConfigurationDefaults["stt"][string];

const schemaTemoin = {
    title: "Témoin",
    properties: {
        provider: { type: "string", default: "temoin" },
        api_key: { type: "string" },
        model: { type: "string", default: "modele-temoin", description: "Modèle." },
    },
} as unknown as ServiceConfigurationDefaults["stt"][string];

const defauts: ServiceConfigurationDefaults = {
    llm: {},
    tts: {},
    stt: { deepgram: schemaDeepgram, temoin: schemaTemoin },
    embeddings: {},
    default_providers: { stt: "deepgram" },
};

function afficher(onSave = vi.fn()) {
    render(
        <ServiceConfigurationForm
            mode="override"
            currentOverrides={{ stt: { provider: "deepgram" } }}
            onSave={onSave}
            configurationDefaults={defauts}
            submitLabel="Save Per-Service Override"
            forceRealtime={false}
        />,
    );
    return onSave;
}

async function ouvrirLOngletTranscription() {
    const onglet = await waitFor(() =>
        screen.getByRole("tab", { name: /transcriber/i }),
    );
    fireEvent.mouseDown(onglet);
    fireEvent.click(onglet);
    await waitFor(() =>
        expect(
            screen.queryAllByText("endpointing").some(el => el.tagName === "LABEL"),
        ).toBe(true),
    );
}

function bloc(champ: string): HTMLElement {
    const etiquette = screen
        .getAllByText(champ.replace(/_/g, " "))
        .find(el => el.tagName === "LABEL");
    expect(etiquette, `no label reads "${champ}" on screen`).toBeTruthy();
    return etiquette!.parentElement as HTMLElement;
}

async function enregistrer(onSave: ReturnType<typeof vi.fn>) {
    fireEvent.click(
        screen.getByRole("button", { name: /save per-service override/i }),
    );
    await waitFor(() => expect(onSave).toHaveBeenCalled());
    const envoye = onSave.mock.calls[0][0] as {
        model_overrides?: Record<string, Record<string, unknown>>;
    };
    return envoye.model_overrides?.stt ?? {};
}

describe("[.mark] a per-service override sends only what it changes", () => {
    it("sends only the changed field, plus the provider", async () => {
        const onSave = afficher();
        await ouvrirLOngletTranscription();

        const saisie = bloc("endpointing").querySelector("input") as HTMLInputElement;
        fireEvent.change(saisie, { target: { value: "450" } });

        const surcharge = await enregistrer(onSave);

        expect(surcharge.endpointing).toBe(450);
        // ⛔ The provider stays: the server compares it to decide between
        // merging field by field and rebuilding the whole section.
        expect(surcharge.provider).toBe("deepgram");
        // 🔑 And nothing else. Sending `model` here would freeze the client's
        // model onto this agent for good.
        expect(Object.keys(surcharge).sort()).toEqual(["endpointing", "provider"]);
    });

    it("sends nothing but the provider when nothing was changed", async () => {
        const onSave = afficher();
        await ouvrirLOngletTranscription();

        const surcharge = await enregistrer(onSave);

        expect(Object.keys(surcharge)).toEqual(["provider"]);
    });

    it("sends a field set back to the client's own value as unchanged", async () => {
        // Typing 100 into a field the client already has at 100 is not a
        // change: freezing it would be the same defect with an extra step.
        const onSave = afficher();
        await ouvrirLOngletTranscription();

        const saisie = bloc("endpointing").querySelector("input") as HTMLInputElement;
        fireEvent.change(saisie, { target: { value: "450" } });
        fireEvent.change(saisie, { target: { value: "100" } });

        const surcharge = await enregistrer(onSave);

        expect(Object.keys(surcharge)).toEqual(["provider"]);
    });

    it("sends a switched boolean even when it lands back on the client's value", async () => {
        const onSave = afficher();
        await ouvrirLOngletTranscription();

        const interrupteur = bloc("profanity_filter").querySelector(
            '[role="switch"]',
        ) as HTMLElement;
        fireEvent.click(interrupteur);

        const surcharge = await enregistrer(onSave);

        expect(surcharge.profanity_filter).toBe(true);
        expect(Object.keys(surcharge).sort()).toEqual(["profanity_filter", "provider"]);
    });

    it("sends the whole block when the provider itself changes", async () => {
        // ⛔ Here the server rebuilds the section from the override alone, so
        // sending one field would leave the agent with a configuration that
        // has nothing else in it.
        const onSave = vi.fn();
        render(
            <ServiceConfigurationForm
                mode="override"
                currentOverrides={{ stt: { provider: "temoin" } }}
                onSave={onSave}
                configurationDefaults={defauts}
                submitLabel="Save Per-Service Override"
                forceRealtime={false}
            />,
        );

        const onglet = await waitFor(() =>
            screen.getByRole("tab", { name: /transcriber/i }),
        );
        fireEvent.mouseDown(onglet);
        fireEvent.click(onglet);
        await waitFor(() =>
            expect(
                screen.queryAllByText("model").some(el => el.tagName === "LABEL"),
            ).toBe(true),
        );

        const surcharge = await enregistrer(onSave);

        expect(surcharge.provider).toBe("temoin");
        // The whole block, not one field: with a different provider the server
        // rebuilds the section from the override alone, so anything left out
        // is simply gone.
        expect(Object.keys(surcharge)).toContain("model");
    });
});
