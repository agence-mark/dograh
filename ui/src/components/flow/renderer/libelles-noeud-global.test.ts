/**
 * [.mark] Clôture SA-5 (É68, Evan 09/11) : les restes anglais du nœud « Global Node » : le champ du prompt dit « Prompt général » (et non
 * « Prompt de l'étape »), sans exemple anglais, et le nom d'un nœud global neuf se dit dans la langue de l'écran.
 */
import { describe, expect, it } from "vitest";

import type { NodeSpec } from "@/client/types.gen";

import { localiserLaPropriete, nomParDefautDuNoeudGlobal } from "./libelles-fr";

const prompt = {
    name: "prompt",
    display_name: "Global Prompt",
    description: "Text appended to every prompted node's system prompt.",
    placeholder: "You are a friendly assistant calling on behalf of {{company_name}}.",
    type: "string",
} as unknown as NodeSpec["properties"][number];

describe("nœud global en français", () => {
    it("le champ prompt du nœud global est le Prompt général, sans exemple anglais", () => {
        const fr = localiserLaPropriete(prompt, "fr", "globalNode");
        expect(fr.display_name).toBe("Prompt général");
        expect(fr.description).toContain("prompt général");
        expect(fr.placeholder ?? "").not.toMatch(/friendly assistant/);
    });

    it("le champ prompt d'une étape reste « Prompt de l'étape »", () => {
        expect(localiserLaPropriete(prompt, "fr", "agentNode").display_name).toBe("Prompt de l'étape");
    });

    it("en anglais le texte du serveur reste tel quel", () => {
        expect(localiserLaPropriete(prompt, "en", "globalNode")).toBe(prompt);
    });

    it("le nom d'un nœud global neuf suit la langue de l'écran", () => {
        expect(nomParDefautDuNoeudGlobal("fr")).toBe("Prompt général");
        expect(nomParDefautDuNoeudGlobal("en")).toBe("General prompt");
    });
});
