/**
 * [.mark] A boolean setting, as seen on screen.
 *
 * The question this file answers, and it answers only this one:
 *
 *     When the schema declares a boolean, does the generated form show a
 *     switch — and does an untouched optional one stay out of what is posted?
 *
 * Why it exists
 * -------------
 * The generated form knows `number`, `integer`, dropdowns, text and multiline.
 * A boolean falls through to the final branch and renders as a FREE TEXT BOX:
 * the client types "true" by hand, or types "vrai", or types nothing, and the
 * API receives a string where it expects a boolean.
 *
 * Seven of the fourteen Deepgram transcription settings are booleans, so the
 * screen cannot show them honestly until this is fixed.
 *
 * 🔑 None of this is specific to Deepgram. `return_timestamps` on HuggingFace
 * is already in that state upstream, in production — which is why this is a
 * natural candidate for the contribution going back upstream.
 *
 * ⛔ This file RENDERS the component. It does not read the schema and conclude.
 * "Declared" is not "usable": the proof is a rendered switch, never a property
 * found in a JSON schema.
 *
 * The schemas below are literals, not imports: they describe the CONTRACT
 * between Python and this screen, so they must break loudly if one side moves
 * without the other.
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

// A synthetic provider carrying the three cases a boolean arrives in. ⛔ Not a
// copy of Deepgram: this rule belongs to the form, not to one provider, and
// pinning it to Deepgram would let it rot the day Deepgram's schema changes.
const schemaTemoin = {
    title: "Témoin",
    properties: {
        provider: { type: "string", default: "temoin" },
        api_key: { type: "string" },
        model: { type: "string", default: "modele-temoin", description: "Modèle." },
        // 1. Required boolean, with a default that runs today.
        filtre_actif: {
            type: "boolean",
            default: false,
            description: "A required boolean, off by default.",
        },
        // 2. Optional boolean: Pydantic writes `bool | None` as an anyOf.
        ponctuation: {
            anyOf: [{ type: "boolean" }, { type: "null" }],
            default: null,
            description: "An optional boolean, not set by default.",
        },
        // 3. Required boolean that starts on.
        resultats_intermediaires: {
            type: "boolean",
            default: true,
            description: "A required boolean, on by default.",
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

async function attendreLeFormulaire() {
    await waitFor(() =>
        expect(screen.getAllByText("filtre actif").length).toBeGreaterThan(0),
    );
}

/** The control carrying a field, found through its visible label.
 *
 * ⚠️ The label text in the DOM is the raw field name with underscores turned
 * into spaces ("filtre actif"): the capitalisation on screen is CSS, so
 * matching on "Filtre actif" here would never find anything.
 */
function bloc(libelle: string): HTMLElement {
    const etiquette = screen
        .getAllByText(libelle)
        .find(el => el.tagName === "LABEL");
    expect(etiquette, `no label reads "${libelle}" on screen`).toBeTruthy();
    return etiquette!.parentElement as HTMLElement;
}

function interrupteur(libelle: string): HTMLElement {
    const controle = bloc(libelle).querySelector('[role="switch"]');
    expect(
        controle,
        `the "${libelle}" label carries no switch — a boolean rendered as ` +
        `something else is a boolean the client types by hand`,
    ).toBeTruthy();
    return controle as HTMLElement;
}

describe("[.mark] a boolean setting on screen", () => {
    it.each([
        ["filtre actif"],
        ["ponctuation"],
        ["resultats intermediaires"],
    ])("shows %s as a switch, not a text box", async libelle => {
        afficher();
        await attendreLeFormulaire();

        expect(interrupteur(libelle)).toBeTruthy();
        // ⛔ The assertion that is false before the patch: the field renders
        // as `input type=text`, and the client is asked to type a boolean.
        expect(bloc(libelle).querySelector("input[type='text']")).toBeNull();
    });

    it("keeps its sentence next to the switch", async () => {
        afficher();
        await attendreLeFormulaire();

        expect(screen.getByText(/A required boolean, off by default/i)).toBeTruthy();
        expect(screen.getByText(/An optional boolean, not set by default/i)).toBeTruthy();
    });

    it("starts each switch on the value that runs today", async () => {
        afficher();
        await attendreLeFormulaire();

        expect(interrupteur("filtre actif").getAttribute("aria-checked")).toBe("false");
        expect(interrupteur("resultats intermediaires").getAttribute("aria-checked")).toBe("true");
        // An optional boolean is "not set", which reads as off.
        expect(interrupteur("ponctuation").getAttribute("aria-checked")).toBe("false");
    });

    it("posts a real boolean, not the string that a text box would give", async () => {
        const onSave = afficher();
        await attendreLeFormulaire();

        fireEvent.click(interrupteur("filtre actif"));

        fireEvent.click(screen.getByRole("button", { name: /save configuration/i }));
        await waitFor(() => expect(onSave).toHaveBeenCalled());

        const envoye = onSave.mock.calls[0][0] as { llm: Record<string, unknown> };
        expect(envoye.llm.filtre_actif).toBe(true);
        expect(envoye.llm.resultats_intermediaires).toBe(true);
    });

    it("does not post an optional boolean that was never touched", async () => {
        const onSave = afficher();
        await attendreLeFormulaire();

        fireEvent.click(screen.getByRole("button", { name: /save configuration/i }));
        await waitFor(() => expect(onSave).toHaveBeenCalled());

        const envoye = onSave.mock.calls[0][0] as { llm: Record<string, unknown> };
        // ⛔ The failure this guards against is silent: an untouched optional
        // field carries its `null` default into the request body, where "not
        // configured" and "explicitly set to nothing" stop being
        // distinguishable. It must not come back as "" either — that is what a
        // text box would have posted.
        expect(
            "ponctuation" in envoye.llm,
            "ponctuation was posted although it was never touched",
        ).toBe(false);
    });

    it("posts an optional boolean once it has been switched on", async () => {
        const onSave = afficher();
        await attendreLeFormulaire();

        fireEvent.click(interrupteur("ponctuation"));

        fireEvent.click(screen.getByRole("button", { name: /save configuration/i }));
        await waitFor(() => expect(onSave).toHaveBeenCalled());

        const envoye = onSave.mock.calls[0][0] as { llm: Record<string, unknown> };
        expect(envoye.llm.ponctuation).toBe(true);
    });

    it("posts an optional boolean switched on then off again", async () => {
        const onSave = afficher();
        await attendreLeFormulaire();

        // 🔑 Off after a deliberate switch is NOT the same as never touched:
        // the first means "the client wants it off", the second means "let the
        // default apply". A patch that treats `false` as empty would lose the
        // difference in silence.
        fireEvent.click(interrupteur("ponctuation"));
        fireEvent.click(interrupteur("ponctuation"));

        fireEvent.click(screen.getByRole("button", { name: /save configuration/i }));
        await waitFor(() => expect(onSave).toHaveBeenCalled());

        const envoye = onSave.mock.calls[0][0] as { llm: Record<string, unknown> };
        expect(envoye.llm.ponctuation).toBe(false);
    });
});
