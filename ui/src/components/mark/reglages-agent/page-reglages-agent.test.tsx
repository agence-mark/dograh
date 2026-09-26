/**
 * [.mark] The agent settings page in 8 themes, rendered (chantier
 * reorganisation-ecran-reglages, step 4).
 *
 * What the payload references do not ask:
 *
 *   - every setting the inventory says is on screen IS found in its theme
 *     (convention § 6, « Rendu »);
 *   - the turn-taking settings hide for an agent whose transcription drives
 *     the turns, by the pipeline's own rule, and the input noise filter stays
 *     (E8);
 *   - a value out of range that another choice HIDES is still named, blocks
 *     the theme, and « show » brings it on screen to be fixed (E7);
 *   - the page speaks French until the user chooses (D12).
 */
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import type { ReactNode } from "react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { resolveWorkflowConfigurations } from "@/types/workflow-configurations";

import { FournisseurLangue } from "../langue/langue";
import { INVENTAIRE_AGENT } from "./inventaire-agent";
import { CONFIG_DE_REFERENCE } from "./references/config-de-reference";

const m = vi.hoisted(() => ({
    config: null as unknown,
    userConfig: null as unknown,
}));

vi.mock("sonner", () => ({ toast: { success: vi.fn(), error: vi.fn() } }));
vi.mock("next/navigation", () => ({
    useParams: () => ({ workflowId: "1" }),
    useRouter: () => ({ push: vi.fn(), replace: vi.fn(), back: vi.fn() }),
}));
vi.mock("@/lib/auth", () => ({
    useAuth: () => ({ user: { id: "u-1", email: "evan@example.test" }, loading: false, redirectToLogin: vi.fn() }),
}));
vi.mock("@/context/OrgConfigContext", () => ({
    useOrgConfig: () => ({ externalPbxIntegrationsEnabled: true, userConfig: m.userConfig, organizationPreferences: null }),
}));
vi.mock("@/hooks/useAudioPlayback", () => ({ useAudioPlayback: () => ({ playingId: null, toggle: vi.fn() }) }));
vi.mock("@/lib/modelConfigurationPricing", () => ({ fetchModelConfigurationPricing: () => Promise.resolve(null) }));
vi.mock("@/components/ui/select", () => import("./references/select-natif"));
vi.mock("@/client/sdk.gen", () => ({
    getWorkflowApiV1WorkflowFetchWorkflowIdGet: () =>
        Promise.resolve({
            data: { id: 1, name: "Agent", workflow_uuid: "u-u-i-d", workflow_definition: { nodes: [], edges: [] }, template_context_variables: {}, workflow_configurations: {} },
            error: null,
        }),
    getModelConfigurationV2ApiV1OrganizationsModelConfigurationsV2Get: () =>
        Promise.resolve({ data: { source: "organization_v2", configuration: {}, effective_configuration: {} }, error: null }),
    getModelConfigurationV2DefaultsApiV1OrganizationsModelConfigurationsV2DefaultsGet: () => Promise.resolve({ data: {}, error: null }),
    listRecordingsApiV1WorkflowRecordingsGet: () => Promise.resolve({ data: { recordings: [] }, error: null }),
    getCommunesDuCodePostalApiV1OrganizationsCommunesGet: () => Promise.resolve({ data: [{ code_insee: "60057", nom: "Beauvais" }], error: null }),
}));
vi.mock("@/components/AIModelConfigurationV2Editor", () => ({ AIModelConfigurationV2Editor: () => <div data-testid="editeur-v2" /> }));
vi.mock("@/components/ServiceConfigurationForm", () => ({ ServiceConfigurationForm: () => <div data-testid="formulaire-service" /> }));
vi.mock("@/components/LLMConfigSelector", () => ({ LLMConfigSelector: () => null }));
vi.mock("@/app/workflow/[workflowId]/components/EmbedDialog", () => ({ EmbedDialog: () => null }));
vi.mock("@/app/workflow/[workflowId]/hooks/useWorkflowState", () => ({
    useWorkflowState: () => ({
        workflowName: "Agent",
        workflowConfigurations: m.config,
        defaultCallDispositions: [],
        defaultAnswerClassifierPrompt: "Consignes intégrées.",
        textChatInactivityTimeoutConstraints: null,
        widgetTextDefaults: {},
        templateContextVariables: {},
        dictionary: "",
        saveWorkflowConfigurations: vi.fn().mockResolvedValue(undefined),
        saveTemplateContextVariables: vi.fn().mockResolvedValue(undefined),
        saveDictionary: vi.fn().mockResolvedValue(undefined),
    }),
}));
vi.stubGlobal("IntersectionObserver", class { observe() {} unobserve() {} disconnect() {} });
vi.stubGlobal("ResizeObserver", class { observe() {} unobserve() {} disconnect() {} });

const { default: WorkflowSettingsPage } = await import("@/app/workflow/[workflowId]/settings/page");

const FLUX = { stt: { provider: "deepgram", model: "flux-general-multi" } };
const NOVA = { stt: { provider: "deepgram", model: "nova-3-general" } };

afterEach(() => {
    cleanup();
    window.localStorage.clear();
});

const ouvrir = async (config: Record<string, unknown>, userConfig: unknown, enveloppe?: (n: ReactNode) => ReactNode) => {
    m.config = resolveWorkflowConfigurations(config as never);
    m.userConfig = userConfig;
    render(<>{enveloppe ? enveloppe(<WorkflowSettingsPage />) : <WorkflowSettingsPage />}</>);
    await waitFor(() => expect(document.querySelectorAll("[data-theme]").length).toBe(8));
};

const ouvrirLeTheme = (id: string) => {
    const entete = document.querySelector(`[data-theme="${id}"] > button[aria-expanded]`) as HTMLButtonElement;
    if (entete.getAttribute("aria-expanded") === "false") fireEvent.click(entete);
    return document.getElementById(id) as HTMLElement;
};

describe("[.mark] the agent page in themes", () => {
    it("draws every setting the inventory puts on screen, in its theme", async () => {
        await ouvrir(CONFIG_DE_REFERENCE as Record<string, unknown>, NOVA);
        for (const [cle, entree] of Object.entries(INVENTAIRE_AGENT)) {
            if ("horsEcran" in entree || "via" in entree) continue;
            const theme = ouvrirLeTheme(entree.theme);
            await waitFor(() => {
                const trouve =
                    theme.querySelector(`[data-reglage="${cle}"], [data-reglage^="${cle}."]`)
                    ?? (cle === "model_overrides" || cle === "mark_per_service_override"
                        ? theme.querySelector('[data-testid="per-service-override"]')
                        : null);
                expect(trouve, `${cle} not found in theme ${entree.theme}`).not.toBeNull();
            });
        }
    });

    it("hides the turn-taking settings when the transcription drives the turns, and keeps the noise filter", async () => {
        await ouvrir({}, FLUX);
        const tour = ouvrirLeTheme("tour");
        expect(tour.querySelector('[data-note="tour-pilote"]')).not.toBeNull();
        for (const id of ["user_speech_timeout", "stt_ttfs_p99_latency", "user_turn_stop_timeout", "turn_wait_for_transcript", "turn_start_use_interim", "vad_confidence", "audio_idle_timeout", "filter_incomplete_user_turns"]) {
            expect(document.getElementById(id), id).toBeNull();
        }
        // What does not depend on who drives the turns stays.
        expect(document.getElementById("turn_stop_strategy")).not.toBeNull();
        expect(document.getElementById("mute_always")).not.toBeNull();
        ouvrirLeTheme("ecoute");
        expect(document.getElementById("audio_in_noise_filter")).not.toBeNull();
    });

    it("shows them for an agent on nova, the same rule the other way", async () => {
        await ouvrir({}, NOVA);
        const tour = ouvrirLeTheme("tour");
        expect(tour.querySelector('[data-note="tour-pilote"]')).toBeNull();
        expect(document.getElementById("user_speech_timeout")).not.toBeNull();
        expect(document.getElementById("vad_confidence")).not.toBeNull();
    });

    it("names a value out of range that another choice hides, blocks the theme, and « show » reveals it", async () => {
        await ouvrir({ vad_confidence: 2 }, FLUX);
        // The red dot, on the theme and in the navigation, before anything is opened.
        expect(document.querySelector('[data-theme="tour"] [data-pastille="erreur"]')).not.toBeNull();
        await waitFor(() => expect(document.querySelector('[data-navigation="tour"] [data-pastille="erreur"]')).not.toBeNull());

        ouvrirLeTheme("tour");
        expect(document.getElementById("vad_confidence")).toBeNull();
        const alerte = screen.getByRole("alert");
        expect(alerte.textContent).toContain("Confidence required");
        expect(alerte.textContent).toContain("vad_confidence");
        expect(alerte.textContent).toContain("Must be at most 1.");
        expect((screen.getByRole("button", { name: "Save Turn taking" }) as HTMLButtonElement).disabled).toBe(true);

        fireEvent.click(screen.getByRole("button", { name: "show" }));
        const champ = await waitFor(() => {
            const trouve = document.getElementById("vad_confidence");
            if (!trouve) throw new Error("not revealed yet");
            return trouve as HTMLInputElement;
        });
        expect(document.querySelector('[data-reglage="vad_confidence"]')?.textContent).toContain("shown here only so its value can be fixed");

        // Fixed, the theme can be saved.
        fireEvent.change(champ, { target: { value: "0.8" } });
        expect(screen.queryByRole("alert")).toBeNull();
        expect((screen.getByRole("button", { name: "Save Turn taking" }) as HTMLButtonElement).disabled).toBe(false);
    });

    it("speaks French until the user chooses, English once chosen", async () => {
        await ouvrir({}, NOVA, (page) => <FournisseurLangue>{page}</FournisseurLangue>);
        expect(document.querySelector('[data-theme="tour"]')?.textContent).toContain("Tour de parole");
        expect(document.querySelector('[data-theme="rythme"]')?.textContent).toContain("Rythme de l'appel");
        ouvrirLeTheme("tour");
        expect(screen.getByRole("button", { name: "Enregistrer Tour de parole" })).toBeTruthy();
        cleanup();

        window.localStorage.setItem("mark.langue", "en");
        await ouvrir({}, NOVA, (page) => <FournisseurLangue>{page}</FournisseurLangue>);
        await waitFor(() => expect(document.querySelector('[data-theme="tour"]')?.textContent).toContain("Turn taking"));
    });
});
