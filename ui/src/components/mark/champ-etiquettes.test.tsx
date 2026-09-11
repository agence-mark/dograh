/**
 * [.mark] A list setting, as seen on screen.
 *
 * The question this file answers, and it answers only this one:
 *
 *     When the schema declares a list of strings, does the generated form let
 *     the client add and remove entries one by one — and does an empty list
 *     stay out of what is posted?
 *
 * Why it exists
 * -------------
 * The generated form has no branch for `array`, so a list falls through to the
 * final branch and renders as a free text box. The client is then asked to
 * guess the separator. That guess is not innocent for two Deepgram settings:
 * `redact` and `replace` take values that CONTAIN separators
 * (`poil:poele`), so "type them comma-separated" is ambiguous the moment the
 * value has a colon or a space in it.
 *
 * A tag field removes the guess: one entry per pastille, each removable in one
 * click.
 *
 * ⛔ This file RENDERS the component. "Declared" is not "usable": the proof is
 * a rendered field the client can type into, never a property found in a JSON
 * schema.
 *
 * The schema below is a literal, not an import: it describes the CONTRACT
 * between Python and this screen, so it must break loudly if one side moves
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

// A synthetic provider. ⛔ Not a copy of Deepgram: this rule belongs to the
// form, not to one provider.
const schemaTemoin = {
    title: "Témoin",
    properties: {
        provider: { type: "string", default: "temoin" },
        api_key: { type: "string" },
        model: { type: "string", default: "modele-temoin", description: "Modèle." },
        // Optional list: Pydantic writes `list[str] | None` as an anyOf.
        termes: {
            anyOf: [{ type: "array", items: { type: "string" } }, { type: "null" }],
            default: null,
            description: "An optional list of terms.",
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
        expect(screen.getAllByText("termes").length).toBeGreaterThan(0),
    );
}

function bloc(libelle: string): HTMLElement {
    const etiquette = screen
        .getAllByText(libelle)
        .find(el => el.tagName === "LABEL");
    expect(etiquette, `no label reads "${libelle}" on screen`).toBeTruthy();
    return etiquette!.parentElement as HTMLElement;
}

function saisie(libelle: string): HTMLInputElement {
    const champ = bloc(libelle).querySelector("input");
    expect(
        champ,
        `the "${libelle}" label carries no input — a list the client cannot ` +
        `type into is a list that stays empty`,
    ).toBeTruthy();
    return champ as HTMLInputElement;
}

function ajouter(libelle: string, texte: string) {
    const champ = saisie(libelle);
    fireEvent.change(champ, { target: { value: texte } });
    fireEvent.keyDown(champ, { key: "Enter", code: "Enter" });
}

function etiquettes(libelle: string): string[] {
    return Array.from(
        bloc(libelle).querySelectorAll("[data-etiquette]"),
    ).map(el => el.getAttribute("data-etiquette") as string);
}

async function enregistrer(onSave: ReturnType<typeof vi.fn>) {
    fireEvent.click(screen.getByRole("button", { name: /save configuration/i }));
    await waitFor(() => expect(onSave).toHaveBeenCalled());
    return onSave.mock.calls[0][0] as { llm: Record<string, unknown> };
}

describe("[.mark] a list setting on screen", () => {
    it("shows a field the client can add entries to", async () => {
        afficher();
        await attendreLeFormulaire();

        expect(saisie("termes")).toBeTruthy();
        expect(screen.getByText(/An optional list of terms/i)).toBeTruthy();
    });

    it("adds one entry per Enter, and shows each as its own tag", async () => {
        afficher();
        await attendreLeFormulaire();

        ajouter("termes", "veranda");
        ajouter("termes", "poele a granules");

        expect(etiquettes("termes")).toEqual(["veranda", "poele a granules"]);
        // The input empties itself, so the next entry can be typed straight in.
        expect(saisie("termes").value).toBe("");
    });

    it("splits a pasted comma-separated list into one tag each", async () => {
        afficher();
        await attendreLeFormulaire();

        ajouter("termes", "veranda, poele, devis");

        expect(etiquettes("termes")).toEqual(["veranda", "poele", "devis"]);
    });

    it("keeps a value that contains a colon in one piece", async () => {
        afficher();
        await attendreLeFormulaire();

        // 🔑 This is why the tag field exists rather than a text box: `replace`
        // takes `poil:poele`, and `redact` takes multi-word categories. A
        // separator inside the value is exactly what a free text box cannot
        // express without a guess.
        ajouter("termes", "poil:poele");

        expect(etiquettes("termes")).toEqual(["poil:poele"]);
    });

    it("removes an entry in one click", async () => {
        afficher();
        await attendreLeFormulaire();

        ajouter("termes", "veranda");
        ajouter("termes", "poele");

        const retirer = bloc("termes").querySelector(
            "[data-etiquette='veranda'] button",
        );
        expect(retirer, "a tag carries no remove button").toBeTruthy();
        fireEvent.click(retirer as HTMLElement);

        expect(etiquettes("termes")).toEqual(["poele"]);
    });

    it("ignores an empty entry and a duplicate", async () => {
        afficher();
        await attendreLeFormulaire();

        ajouter("termes", "veranda");
        ajouter("termes", "   ");
        ajouter("termes", "veranda");

        expect(etiquettes("termes")).toEqual(["veranda"]);
    });

    it("posts the list once it has entries", async () => {
        const onSave = afficher();
        await attendreLeFormulaire();

        ajouter("termes", "veranda, poele");

        const envoye = await enregistrer(onSave);
        expect(envoye.llm.termes).toEqual(["veranda", "poele"]);
    });

    it("does not post a list that was never touched", async () => {
        const onSave = afficher();
        await attendreLeFormulaire();

        const envoye = await enregistrer(onSave);
        expect(
            "termes" in envoye.llm,
            "termes was posted although it was never touched",
        ).toBe(false);
    });

    it("does not post an empty list either", async () => {
        const onSave = afficher();
        await attendreLeFormulaire();

        // ⛔ An empty list is NOT "absent": posted as `[]` it means "the client
        // explicitly wants no terms", which for several Deepgram settings is a
        // different request from sending nothing at all. Adding then removing
        // an entry must land back on "not configured".
        ajouter("termes", "veranda");
        fireEvent.click(
            bloc("termes").querySelector("[data-etiquette='veranda'] button") as HTMLElement,
        );

        const envoye = await enregistrer(onSave);
        expect(
            "termes" in envoye.llm,
            "termes was posted as an empty list instead of being left out",
        ).toBe(false);
    });
});
