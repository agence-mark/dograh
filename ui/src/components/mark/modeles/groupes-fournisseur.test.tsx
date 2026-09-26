/**
 * [.mark] The Models screen in sub-menus (chantier reorganisation-ecran-reglages,
 * step 6, convention E2), rendered with the REAL schemas of the registry.
 *
 * The payload and the list of fields are frozen by
 * `references/charges-utiles-modeles.test.tsx`. This file checks the layout:
 * the sub-menus and what goes in them per model, the flat group, « Other » for
 * a field nobody filed, the labels in both languages, the same rendering in an
 * agent's per-service override (Services theme), and a provider without groups
 * drawn as before.
 */
import { readFileSync } from "node:fs";
import { join } from "node:path";

import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import type { ReactNode } from "react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { type ServiceConfigurationDefaults, ServiceConfigurationForm } from "@/components/ServiceConfigurationForm";

import { FournisseurLangue } from "../langue/langue";

vi.mock("@/context/UserConfigContext", () => ({
    useUserConfig: () => ({
        userConfig: { stt: { provider: "deepgram", model: "nova-3-general" } },
        refreshConfig: vi.fn(),
    }),
}));
vi.mock("@/components/ui/select", () => import("../reglages-agent/references/select-natif"));
vi.mock("@/components/VoiceSelector", () => ({ VoiceSelector: () => <input id="tts_voice" /> }));
vi.stubGlobal("ResizeObserver", class { observe() {} unobserve() {} disconnect() {} });

type Schemas = Record<"llm" | "tts" | "stt", Record<string, { properties: Record<string, Record<string, unknown>> }>>;
const SCHEMAS = JSON.parse(
    readFileSync(join(process.cwd(), "src/components/mark/modeles/references/schemas-fournisseurs.json"), "utf8"),
) as Schemas;

const defauts = (stt = SCHEMAS.stt) =>
    ({
        llm: SCHEMAS.llm,
        tts: SCHEMAS.tts,
        stt,
        embeddings: {},
        default_providers: { llm: "mistral", tts: "elevenlabs", stt: "deepgram" },
    }) as unknown as ServiceConfigurationDefaults;

afterEach(() => {
    cleanup();
    window.localStorage.clear();
});

const ouvrirTranscription = async (
    model: string,
    options: { stt?: Schemas["stt"]; mode?: "global" | "override"; enveloppe?: (n: ReactNode) => ReactNode } = {},
) => {
    const formulaire = (
        <ServiceConfigurationForm
            mode={options.mode ?? "global"}
            onSave={vi.fn().mockResolvedValue(undefined)}
            configurationDefaults={defauts(options.stt)}
            initialConfig={{
                llm: { provider: "mistral", model: "mistral-large-2512", api_key: ["k"] },
                tts: { provider: "elevenlabs", model: "eleven_flash_v2_5", api_key: ["k"] },
                stt: { provider: "deepgram", model, language: model === "flux-general-en" ? "en" : "fr", api_key: ["k"] },
            }}
            forceRealtime={false}
        />
    );
    render(<>{options.enveloppe ? options.enveloppe(formulaire) : formulaire}</>);
    const onglet = await waitFor(() => screen.getByRole("tab", { name: /transcri/i }));
    fireEvent.mouseDown(onglet);
    fireEvent.click(onglet);
};

const sousMenus = () => Array.from(document.querySelectorAll("[data-sous-menu]")).map((m) => m.getAttribute("data-sous-menu"));
const ouvrirSousMenu = (id: string) =>
    fireEvent.click(document.querySelector(`[data-sous-menu="${id}"] > button`) as HTMLButtonElement);
const champsDe = (id: string) =>
    Array.from(document.querySelectorAll(`[data-sous-menu="${id}"] [data-champ]`)).map((c) => c.getAttribute("data-champ"));

describe("[.mark] Models screen in sub-menus", () => {
    it("files Deepgram Flux's settings by group, only the ones Flux reads", async () => {
        await ouvrirTranscription("flux-general-multi");
        await waitFor(() => expect(sousMenus().length).toBeGreaterThan(0));
        expect(sousMenus()).toEqual(["stt.langue", "stt.fin_de_tour", "stt.hebergement"]);
        // Closed by default: the settings are not drawn until opened.
        expect(document.querySelector('[data-champ="eot_threshold"]')).toBeNull();
        ouvrirSousMenu("stt.fin_de_tour");
        expect(champsDe("stt.fin_de_tour")).toEqual(["eot_threshold", "eager_eot_threshold", "eot_timeout_ms", "min_confidence"]);
        ouvrirSousMenu("stt.langue");
        expect(champsDe("stt.langue")).toEqual(["language", "language_hints"]);
        // Model, provider and keys at the top, outside any sub-menu.
        expect(document.querySelector('[data-champ="model"]')?.closest("[data-sous-menu]")).toBeNull();
        expect(document.querySelector('input[placeholder="Enter API key"]')?.closest("[data-sous-menu]")).toBeNull();
    });

    it("files nova-3's settings, and hides Flux's, by the same model rule", async () => {
        await ouvrirTranscription("nova-3-general");
        await waitFor(() => expect(sousMenus().length).toBeGreaterThan(0));
        expect(sousMenus()).toEqual(["stt.fin_de_tour", "stt.mise_en_forme", "stt.vocabulaire", "stt.hebergement", "stt.analyse"]);
        ouvrirSousMenu("stt.fin_de_tour");
        expect(champsDe("stt.fin_de_tour")).toEqual(["endpointing", "utterance_end_ms", "interim_results"]);
        ouvrirSousMenu("stt.vocabulaire");
        // `keywords` is refused from nova-3 onwards: hidden, as before.
        expect(champsDe("stt.vocabulaire")).toEqual(["replace", "search"]);
    });

    it("draws a group with a single visible setting flat, without a sub-menu", async () => {
        await ouvrirTranscription("flux-general-en");
        await waitFor(() => expect(sousMenus().length).toBeGreaterThan(0));
        expect(sousMenus()).not.toContain("stt.langue");
        expect(document.querySelector('[data-champ="language"]')).not.toBeNull();
        expect(document.querySelector('[data-champ="language"]')?.closest("[data-sous-menu]")).toBeNull();
    });

    it("puts a field nobody filed in « Other », never loses it", async () => {
        const stt = structuredClone(SCHEMAS.stt);
        stt.deepgram.properties.nouveau_reglage = { type: "boolean", default: false, description: "Added upstream." };
        stt.deepgram.properties.autre_nouveau = { type: "boolean", default: false, description: "Added upstream too." };
        await ouvrirTranscription("nova-3-general", { stt });
        await waitFor(() => expect(sousMenus()).toContain("stt.autres"));
        expect(sousMenus().at(-1)).toBe("stt.autres");
        ouvrirSousMenu("stt.autres");
        expect(champsDe("stt.autres")).toEqual(["nouveau_reglage", "autre_nouveau"]);
    });

    it("shows the readable label in the chosen language, with the technical name", async () => {
        await ouvrirTranscription("flux-general-multi", { enveloppe: (n) => <FournisseurLangue>{n}</FournisseurLangue> });
        await waitFor(() => expect(sousMenus().length).toBeGreaterThan(0));
        expect(document.querySelector('[data-sous-menu="stt.fin_de_tour"]')?.textContent).toContain("Fin de tour");
        ouvrirSousMenu("stt.fin_de_tour");
        const champ = document.querySelector('[data-champ="eot_threshold"]') as HTMLElement;
        expect(champ.textContent).toContain("Seuil de fin de tour");
        expect(champ.querySelector("[data-cle-technique]")?.textContent).toBe("eot_threshold");
    });

    it("draws an agent's per-service override the same way (Services theme)", async () => {
        await ouvrirTranscription("flux-general-multi", { mode: "override" });
        fireEvent.click(await waitFor(() => document.getElementById("override-stt") as HTMLButtonElement));
        await waitFor(() => expect(sousMenus()).toEqual(["stt.langue", "stt.fin_de_tour", "stt.hebergement"]));
    });

    it("draws a provider without groups as before", async () => {
        const stt = structuredClone(SCHEMAS.stt);
        for (const propriete of Object.values(stt.deepgram.properties)) {
            delete propriete.mark_groupe;
            delete propriete.mark_libelle;
        }
        await ouvrirTranscription("nova-3-general", { stt });
        await waitFor(() => expect(document.querySelectorAll("label.capitalize").length).toBeGreaterThan(3));
        expect(sousMenus()).toEqual([]);
        expect(document.querySelector('[data-champ="endpointing"]')).not.toBeNull();
    });
});
