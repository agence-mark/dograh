/**
 * [.mark] Soniox on the Models screen (chantier exposition-soniox, 2026-09-29),
 * rendered with the REAL schema of the registry (`schemas-fournisseurs.json`,
 * kept current by `api/tests/mark/test_schemas_ecran_modeles_a_jour.py`).
 *
 * What it proves, because a declared field is not a field on screen:
 * - every setting is drawn, in its sub-menu, with its label in both languages;
 * - « Soniox decides the end of turn » switched off hides the three end-of-turn
 *   settings -- the same rule the factory applies when it drops them (E8) --
 *   and the sub-menu stays, so it does not jump when the switch moves (E2);
 * - an agent's per-service override draws the same screen.
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
        userConfig: { stt: { provider: "soniox", model: "stt-rt-v5" } },
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

const FIN_DE_TOUR = ["max_endpoint_delay_ms", "endpoint_sensitivity", "endpoint_latency_adjustment_level"];

afterEach(() => {
    cleanup();
    window.localStorage.clear();
});

const ouvrirSoniox = async (
    options: { stt?: Record<string, unknown>; mode?: "global" | "override"; enveloppe?: (n: ReactNode) => ReactNode } = {},
) => {
    const formulaire = (
        <ServiceConfigurationForm
            mode={options.mode ?? "global"}
            onSave={vi.fn().mockResolvedValue(undefined)}
            configurationDefaults={
                {
                    llm: SCHEMAS.llm,
                    tts: SCHEMAS.tts,
                    stt: SCHEMAS.stt,
                    embeddings: {},
                    default_providers: { llm: "mistral", tts: "elevenlabs", stt: "deepgram" },
                } as unknown as ServiceConfigurationDefaults
            }
            initialConfig={{
                llm: { provider: "mistral", model: "mistral-large-2512", api_key: ["k"] },
                tts: { provider: "elevenlabs", model: "eleven_flash_v2_5", api_key: ["k"] },
                stt: { provider: "soniox", model: "stt-rt-v5", language: "fr", api_key: ["k"], ...(options.stt ?? {}) },
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

describe("[.mark] Soniox on the Models screen", () => {
    it("draws every setting, filed by group", async () => {
        await ouvrirSoniox();
        await waitFor(() => expect(sousMenus().length).toBeGreaterThan(0));
        expect(sousMenus()).toEqual(["stt.langue", "stt.fin_de_tour", "stt.hebergement"]);
        ouvrirSousMenu("stt.langue");
        expect(champsDe("stt.langue")).toEqual(["language", "language_hints_strict", "enable_language_identification"]);
        ouvrirSousMenu("stt.fin_de_tour");
        expect(champsDe("stt.fin_de_tour")).toEqual(["endpoint_detection", ...FIN_DE_TOUR]);
        ouvrirSousMenu("stt.hebergement");
        expect(champsDe("stt.hebergement")).toEqual(["base_url", "region"]);
        // A group with one setting is drawn flat (E2).
        const diarisation = document.querySelector('[data-champ="enable_speaker_diarization"]');
        expect(diarisation).not.toBeNull();
        expect(diarisation?.closest("[data-sous-menu]")).toBeNull();
        // The model at the top, outside any sub-menu.
        expect(document.querySelector('[data-champ="model"]')?.closest("[data-sous-menu]")).toBeNull();
    });

    it("hides the three end-of-turn settings when Soniox does not decide, and keeps the sub-menu", async () => {
        await ouvrirSoniox({ stt: { endpoint_detection: false } });
        await waitFor(() => expect(sousMenus()).toContain("stt.fin_de_tour"));
        ouvrirSousMenu("stt.fin_de_tour");
        expect(champsDe("stt.fin_de_tour")).toEqual(["endpoint_detection"]);
    });

    it("shows them again when the switch is turned on", async () => {
        await ouvrirSoniox({ stt: { endpoint_detection: false } });
        await waitFor(() => expect(sousMenus()).toContain("stt.fin_de_tour"));
        ouvrirSousMenu("stt.fin_de_tour");
        const interrupteur = document.querySelector('[data-champ="endpoint_detection"] button[role="switch"]') as HTMLButtonElement;
        expect(interrupteur).not.toBeNull();
        fireEvent.click(interrupteur);
        await waitFor(() => expect(champsDe("stt.fin_de_tour")).toEqual(["endpoint_detection", ...FIN_DE_TOUR]));
    });

    it("shows the Europe address by default and the region it derives", async () => {
        await ouvrirSoniox();
        await waitFor(() => expect(sousMenus()).toContain("stt.hebergement"));
        ouvrirSousMenu("stt.hebergement");
        const hebergement = document.querySelector('[data-sous-menu="stt.hebergement"]') as HTMLElement;
        expect(hebergement.innerHTML).toContain("stt-rt.eu.soniox.com");
    });

    it("shows the labels in French, with the technical name", async () => {
        await ouvrirSoniox({ enveloppe: (n) => <FournisseurLangue>{n}</FournisseurLangue> });
        await waitFor(() => expect(sousMenus()).toContain("stt.fin_de_tour"));
        ouvrirSousMenu("stt.fin_de_tour");
        const champ = document.querySelector('[data-champ="endpoint_detection"]') as HTMLElement;
        expect(champ.textContent).toMatch(/Soniox d(é|e)cide/);
        expect(champ.querySelector("[data-cle-technique]")?.textContent).toBe("endpoint_detection");
    });

    it("draws an agent's per-service override the same way (Services theme)", async () => {
        await ouvrirSoniox({ mode: "override" });
        fireEvent.click(await waitFor(() => document.getElementById("override-stt") as HTMLButtonElement));
        await waitFor(() => expect(sousMenus()).toEqual(["stt.langue", "stt.fin_de_tour", "stt.hebergement"]));
        ouvrirSousMenu("stt.fin_de_tour");
        expect(champsDe("stt.fin_de_tour")).toEqual(["endpoint_detection", ...FIN_DE_TOUR]);
    });
});
