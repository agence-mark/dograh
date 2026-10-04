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
        // Every key of the inventory, one after the other: slow under a full run.
    }, 30000);

    // C9 (chantier correctifs-banc-34, question n° 272): under a transcription
    // that decides the turns, the screen shows what plays and hides what does
    // not -- the table frozen in `api/tests/mark/test_traversants_appel.py`.
    const JOUENT = [
        "vad_confidence",
        "vad_start_secs",
        "vad_stop_secs",
        "vad_min_volume",
        "audio_idle_timeout",
        "user_turn_stop_timeout",
        "filter_incomplete_user_turns",
    ];
    const NE_JOUENT_PAS = ["user_speech_timeout", "stt_ttfs_p99_latency", "turn_wait_for_transcript", "turn_start_use_interim"];
    const SONIOX_DECIDE = { stt: { provider: "soniox", model: "stt-rt-v3", endpoint_detection: true } };

    for (const [nom, transcription] of [["Flux", FLUX], ["Soniox deciding", SONIOX_DECIDE]] as const) {
        it(`${nom}: shows the settings that play, hides the ones that do not, and says which is which`, async () => {
            await ouvrir({ turn_stop_strategy: "turn_analyzer", turn_start_strategy: "min_words" }, transcription);
            const tour = ouvrirLeTheme("tour");
            for (const id of JOUENT) expect(document.getElementById(id), id).not.toBeNull();
            for (const id of [...NE_JOUENT_PAS, "smart_turn_pre_speech_ms", "smart_turn_max_duration_secs"]) {
                expect(document.getElementById(id), id).toBeNull();
            }
            const note = tour.querySelector('[data-note="tour-pilote"]');
            expect(note).not.toBeNull();
            expect(note?.textContent).not.toMatch(/builds none|ne construit aucun/i);
            // D-C9-2 and D-C9-4: the two strategies stay, each saying it has no effect here.
            expect(document.getElementById("turn_stop_strategy")).not.toBeNull();
            expect(document.getElementById("turn_start_strategy")).not.toBeNull();
            expect(tour.querySelector('[data-note="sans-effet-fin-de-tour"]')).not.toBeNull();
            expect(tour.querySelector('[data-note="sans-effet-interruption"]')).not.toBeNull();
            // D-C9-1: the voice detector says what it still commands.
            expect(tour.querySelector('[data-note="detecteur-sous-tours-externes"]')).not.toBeNull();
            expect(document.getElementById("mute_always")).not.toBeNull();
            ouvrirLeTheme("ecoute");
            expect(document.getElementById("audio_in_noise_filter")).not.toBeNull();
        });
    }

    it("shows them for an agent on nova, the same rule the other way", async () => {
        await ouvrir({}, NOVA);
        const tour = ouvrirLeTheme("tour");
        expect(tour.querySelector('[data-note="tour-pilote"]')).toBeNull();
        expect(tour.querySelector('[data-note="sans-effet-fin-de-tour"]')).toBeNull();
        expect(tour.querySelector('[data-note="sans-effet-interruption"]')).toBeNull();
        expect(document.getElementById("user_speech_timeout")).not.toBeNull();
        expect(document.getElementById("vad_confidence")).not.toBeNull();
    });

    it("names a value out of range that another choice hides, blocks the theme, and « show » reveals it", async () => {
        // C9: the detector is shown under Flux now; the pause stays hidden there.
        await ouvrir({ user_speech_timeout: 11 }, FLUX);
        // The red dot, on the theme and in the navigation, before anything is opened.
        expect(document.querySelector('[data-theme="tour"] [data-pastille="erreur"]')).not.toBeNull();
        await waitFor(() => expect(document.querySelector('[data-navigation="tour"] [data-pastille="erreur"]')).not.toBeNull());

        ouvrirLeTheme("tour");
        expect(document.getElementById("user_speech_timeout")).toBeNull();
        const alerte = screen.getByRole("alert");
        expect(alerte.textContent).toContain("Pause before the agent answers");
        expect(alerte.textContent).toContain("user_speech_timeout");
        expect(alerte.textContent).toContain("at most 10");
        expect((screen.getByRole("button", { name: "Save Turn taking" }) as HTMLButtonElement).disabled).toBe(true);

        fireEvent.click(screen.getByRole("button", { name: "show" }));
        const champ = await waitFor(() => {
            const trouve = document.getElementById("user_speech_timeout");
            if (!trouve) throw new Error("not revealed yet");
            return trouve as HTMLInputElement;
        });
        expect(document.querySelector('[data-reglage="user_speech_timeout"]')?.textContent).toContain("shown here only so its value can be fixed");

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

// [.mark] Plan mode-prise-de-notes, lot 6: the note-taking mode, rendered.
describe("[.mark] the note-taking mode in the call data theme", () => {
    const FICHE = {
        fiche_au_fil_de_leau: true,
        fiche_champs: [{ nom: "nom", type: "string", origine: "dicte", description: "Nom", lecteur: null, valeurs: null }],
    };
    const menu = () => document.getElementById("fiche_mode_de_note") as HTMLSelectElement | null;

    it("shows the stored mode, read back from the server", async () => {
        await ouvrir({ ...FICHE, fiche_mode_de_note: "post_scriptum" }, NOVA);
        ouvrirLeTheme("donnees");
        await waitFor(() => expect(menu()?.value).toBe("post_scriptum"));
    });

    it("an agent saved before the setting reads « tool »", async () => {
        await ouvrir(FICHE, NOVA);
        ouvrirLeTheme("donnees");
        await waitFor(() => expect(menu()?.value).toBe("outil"));
    });

    it("is shown only with the record on, like in the code", async () => {
        await ouvrir({ ...FICHE, fiche_au_fil_de_leau: false }, NOVA);
        ouvrirLeTheme("donnees");
        await waitFor(() => expect(document.getElementById("fiche_au_fil_de_leau")).not.toBeNull());
        expect(menu()).toBeNull();
        fireEvent.click(document.getElementById("fiche_au_fil_de_leau") as HTMLElement);
        await waitFor(() => expect(menu()).not.toBeNull());
    });

    it("offers the clerk greyed out until part 2", async () => {
        await ouvrir(FICHE, NOVA);
        ouvrirLeTheme("donnees");
        await waitFor(() => expect(menu()).not.toBeNull());
        const options = Array.from(menu()!.options).map((o) => [o.value, o.disabled]);
        expect(options).toEqual([
            ["outil", false],
            ["post_scriptum", false],
            ["greffier", true],
        ]);
    });
});
