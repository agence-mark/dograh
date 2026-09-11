/**
 * [.mark] A setting the chosen model does not accept, hidden from the screen.
 *
 * The question this file answers, and it answers only this one:
 *
 *     Does a field declared for one model disappear when another model is
 *     chosen — and does hiding it leave the value it holds alone?
 *
 * Why it exists
 * -------------
 * The Deepgram settings split in two: fourteen belong to the classic
 * connector, five belong to Flux, and they are two different services behind
 * one provider entry. Without this, the screen would show the five Flux
 * thresholds while `nova-3` is selected, and the fourteen classic settings
 * while Flux is selected.
 *
 * ⛔ A setting shown, filled in, sent, and ignored by the model is exactly what
 * we ruled out for `top_k`. `model_options` already existed and filters the
 * VALUES of a dropdown; it cannot hide a field.
 *
 * 🔑 Hiding is not erasing. A client on `nova-3` keeps whatever the Flux
 * fields hold, so switching back to Flux does not silently reset three
 * thresholds. That is asserted below, because the opposite would be invisible.
 *
 * ⛔ This file RENDERS the component with each model in turn.
 */

import { render, screen, waitFor } from "@testing-library/react";
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

// A synthetic provider with two models that accept different settings. ⛔ Not
// a copy of Deepgram: the rule belongs to the form.
const schemaTemoin = {
    title: "Témoin",
    properties: {
        provider: { type: "string", default: "temoin" },
        api_key: { type: "string" },
        model: {
            type: "string",
            default: "modele_a",
            examples: ["modele_a", "modele_b"],
            description: "Modèle.",
        },
        reglage_partout: {
            anyOf: [{ type: "integer" }, { type: "null" }],
            default: null,
            description: "Accepted by every model, so declared without a list.",
        },
        reglage_de_a: {
            anyOf: [{ type: "integer" }, { type: "null" }],
            default: null,
            models: ["modele_a"],
            description: "Only model A accepts this one.",
        },
        reglage_de_b: {
            type: "number",
            default: 0.7,
            models: ["modele_b"],
            description: "Only model B accepts this one.",
        },
    },
} as unknown as ServiceConfigurationDefaults["llm"][string];

const defauts: ServiceConfigurationDefaults = {
    llm: { temoin: schemaTemoin },
    tts: {},
    stt: {},
    embeddings: {},
    default_providers: { llm: "temoin" },
};

function afficher(modele: string, onSave = vi.fn()) {
    render(
        <ServiceConfigurationForm
            mode="global"
            onSave={onSave}
            configurationDefaults={defauts}
            initialConfig={{ llm: { provider: "temoin", model: modele } }}
            forceRealtime={false}
        />,
    );
    return onSave;
}

function estAffiche(libelle: string): boolean {
    return screen.queryAllByText(libelle).some(el => el.tagName === "LABEL");
}

async function attendreLeFormulaire() {
    await waitFor(() => expect(estAffiche("reglage partout")).toBe(true));
}

describe("[.mark] hiding a setting the chosen model does not accept", () => {
    it("shows only model A's setting when model A is chosen", async () => {
        afficher("modele_a");
        await attendreLeFormulaire();

        expect(estAffiche("reglage de a")).toBe(true);
        expect(estAffiche("reglage de b")).toBe(false);
    });

    it("shows only model B's setting when model B is chosen", async () => {
        afficher("modele_b");
        await attendreLeFormulaire();

        expect(estAffiche("reglage de b")).toBe(true);
        expect(estAffiche("reglage de a")).toBe(false);
    });

    it("keeps showing a setting declared without a model list", async () => {
        // ⛔ Absent means "every model", so no existing field anywhere in the
        // product changes behaviour because of this patch.
        afficher("modele_b");
        await attendreLeFormulaire();

        expect(estAffiche("reglage partout")).toBe(true);
    });

    it("hides the field without dropping the value it holds", async () => {
        // 🔑 Hiding is a screen decision, not a data decision. A client on
        // model A keeps model B's threshold, so switching back does not
        // silently reset it. The factory reads it only on the path where it
        // applies, so carrying it costs nothing.
        const onSave = afficher("modele_a");
        await attendreLeFormulaire();

        const { fireEvent } = await import("@testing-library/react");
        fireEvent.click(screen.getByRole("button", { name: /save configuration/i }));
        await waitFor(() => expect(onSave).toHaveBeenCalled());

        const envoye = onSave.mock.calls[0][0] as { llm: Record<string, unknown> };
        expect(envoye.llm.reglage_de_b).toBe(0.7);
    });
});
