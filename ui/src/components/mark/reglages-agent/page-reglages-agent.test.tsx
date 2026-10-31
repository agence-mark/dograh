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
import { readFileSync } from "node:fs";
import { join } from "node:path";

import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import type { ReactNode } from "react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { resolveWorkflowConfigurations } from "@/types/workflow-configurations";

import { FournisseurLangue } from "../langue/langue";
import { CONSIGNE_GENERIQUE_GREFFIER } from "./consigne-greffier";
import { INVENTAIRE_AGENT } from "./inventaire-agent";
import { CLES_MODULES, MODULES_AGENT } from "./modules-agent";
import { CONFIG_DE_REFERENCE } from "./references/config-de-reference";

const m = vi.hoisted(() => ({
    config: null as unknown,
    userConfig: null as unknown,
    modules: undefined as unknown,
    // What the page saves: read by the clerk's tests below.
    save: vi.fn(() => Promise.resolve(undefined)),
    // Plan porte-parlee: the graph the page is opened with.
    definition: { nodes: [], edges: [] } as unknown,
    // Lot 4 d'orchestrateur-trois-cerveaux: the tools of the organization (a transfer, the end of the call and
    // an MCP server are never offered to the background brain).
    outils: [
        { tool_uuid: "outil-creneau", name: "Chercher un creneau", description: "Cherche un creneau libre.", category: "http_api", status: "active", icon_color: null },
        { tool_uuid: "outil-transfert", name: "Passer a un humain", description: "Transfert d'appel.", category: "transfer_call", status: "active", icon_color: null },
        { tool_uuid: "outil-fin", name: "Raccrocher", description: "Fin d'appel.", category: "end_call", status: "active", icon_color: null },
        { tool_uuid: "outil-mcp", name: "Serveur MCP", description: "Un serveur MCP.", category: "mcp", status: "active", icon_color: null },
    ] as unknown[],
    // Lot C d'agent-leger-greffier (D9): the schemas the clerk's generated form reads.
    schemasLlm: {
        mistral: {
            title: "Mistral",
            properties: {
                provider: {}, api_key: {},
                model: { type: "string", examples: ["mistral-large-2512"] },
                temperature: { type: "number", default: 0.1, mark_groupe: "generation", mark_libelle: { en: "Temperature", fr: "Température" } },
            },
        },
        openai: {
            title: "OpenAI",
            properties: {
                provider: {}, api_key: {},
                model: { type: "string", examples: ["gpt-4.1"] },
                temperature: { type: "number", default: 0.1, mark_groupe: "generation" },
                reasoning_effort: { anyOf: [{ type: "string", enum: ["none", "minimal", "low", "medium", "high"] }, { type: "null" }], mark_groupe: "generation" },
                base_url: { type: "string", default: "https://api.openai.com/v1", mark_groupe: "technique" },
            },
        },
    } as Record<string, unknown>,
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
vi.mock("@/client/sdk.gen", async (importOriginal) => (await import("../sdk-factice")).sdkFactice(await importOriginal(), {
    getWorkflowApiV1WorkflowFetchWorkflowIdGet: () =>
        Promise.resolve({
            data: { id: 1, name: "Agent", workflow_uuid: "u-u-i-d", workflow_definition: m.definition, template_context_variables: {}, workflow_configurations: {} },
            error: null,
        }),
    getModelConfigurationV2ApiV1OrganizationsModelConfigurationsV2Get: () =>
        Promise.resolve({ data: { source: "organization_v2", configuration: {}, effective_configuration: {} }, error: null }),
    getModelConfigurationV2DefaultsApiV1OrganizationsModelConfigurationsV2DefaultsGet: () => Promise.resolve({ data: {}, error: null }),
    getDefaultConfigurationsApiV1UserConfigurationsDefaultsGet: () => Promise.resolve({ data: { llm: m.schemasLlm }, error: null }),
    listRecordingsApiV1WorkflowRecordingsGet: () => Promise.resolve({ data: { recordings: [] }, error: null }),
    getCommunesDuCodePostalApiV1OrganizationsCommunesGet: () => Promise.resolve({ data: [{ code_insee: "60057", nom: "Beauvais" }], error: null }),
    // Lot 4 d'orchestrateur-trois-cerveaux: the catalogue the background brain's tool list reads.
    listToolsApiV1ToolsGet: () => Promise.resolve({ data: m.outils, error: null }),
    // cloture-code, F8: what the server says of the agent's modules (absent: the page works without it).
    getModulesDeLAgentApiV1AgentsAgentIdModulesGet: () => Promise.resolve({ data: m.modules, error: null }),
}));
// Lot 3 d'orchestrateur-trois-cerveaux (D7): the stand-ins draw the note they are given for a locked voice.
vi.mock("@/components/AIModelConfigurationV2Editor", () => ({
    AIModelConfigurationV2Editor: ({ voixVerrouillee }: { voixVerrouillee?: ReactNode }) => <div data-testid="editeur-v2">{voixVerrouillee}</div>,
}));
vi.mock("@/components/ServiceConfigurationForm", () => ({
    ServiceConfigurationForm: ({ voixVerrouillee }: { voixVerrouillee?: ReactNode }) => <div data-testid="formulaire-service">{voixVerrouillee}</div>,
}));
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
        saveWorkflowConfigurations: m.save,
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
    await waitFor(() => expect(document.querySelectorAll("[data-theme]").length).toBe(11));
};

const ouvrirLeTheme = (id: string) => {
    const entete = document.querySelector(`[data-theme="${id}"] > button[aria-expanded]`) as HTMLButtonElement;
    if (entete.getAttribute("aria-expanded") === "false") fireEvent.click(entete);
    // cloture-code, F8 (M4): the theme « Modules » holds one drop-down sub-menu per module, opened too.
    document
        .querySelectorAll<HTMLButtonElement>(`[data-theme="${id}"] [data-sous-menu-module] > button[aria-expanded="false"]`)
        .forEach((bouton) => fireEvent.click(bouton));
    return document.getElementById(id) as HTMLElement;
};

// cloture-code, F8 (M4): the theme « Modules », one drop-down sub-menu per module; the cards moved, never doubled.
describe("[.mark] the theme « Modules »", () => {
    const registre = readFileSync(join(process.cwd(), "..", "api/services/modules/registre.py"), "utf8");
    const reglages = readFileSync(join(process.cwd(), "..", "api/services/groupe/reglages.py"), "utf8");

    it("holds the registry's modules and exactly the keys of CLES_THEME_MODULES, in order", () => {
        const codes = [...registre.matchAll(/^ {4}Module\(\s*"([a-z_]+)"/gm)].map((m) => m[1]);
        expect(codes.length).toBeGreaterThan(5);
        expect(MODULES_AGENT.map((m) => m.code)).toEqual(codes);
        const debut = reglages.indexOf("CLES_THEME_MODULES: tuple[str, ...] = (");
        const corps = reglages.slice(debut, reglages.indexOf(")", debut)).replace(/#.*$/gm, "");
        expect(CLES_MODULES).toEqual([...corps.matchAll(/"([a-z_0-9]+)"/g)].map((m) => m[1]));
    });

    it("draws one closed sub-menu per module; a moved card is no longer where it was", async () => {
        await ouvrir(CONFIG_DE_REFERENCE as Record<string, unknown>, NOVA);
        const entete = document.querySelector('[data-theme="modules"] > button[aria-expanded]') as HTMLButtonElement;
        fireEvent.click(entete);
        const sousMenus = document.querySelectorAll('[data-theme="modules"] [data-sous-menu-module]');
        expect([...sousMenus].map((s) => s.getAttribute("data-sous-menu-module"))).toEqual(MODULES_AGENT.map((m) => m.code));
        expect(document.querySelector('[data-theme="modules"] [data-reglage="verification_communes"]')).toBeNull();
        fireEvent.click(screen.getByRole("button", { name: "Town and street" }));
        await waitFor(() => expect(document.querySelector('[data-theme="modules"] [data-reglage="verification_communes"]')).not.toBeNull());
        // Moved: nothing of a module left in « Listening » nor « Call data » (convention: replace, never add).
        for (const theme of ["ecoute", "donnees"]) {
            const ouvert = ouvrirLeTheme(theme);
            await waitFor(() => expect(ouvert.querySelector("[data-reglage]")).not.toBeNull());
            for (const cle of CLES_MODULES) expect(ouvert.querySelector(`[data-reglage="${cle}"]`), `${cle} in ${theme}`).toBeNull();
        }
    });

    it("shows what the server says: the translator plugged in, a module switched on by its tools", async () => {
        m.modules = {
            agent_id: 1,
            modules: [
                {
                    code: "planificateur",
                    libelle: { en: "Appointment planner", fr: "Planificateur de rendez-vous" },
                    actif: true,
                    besoins: [
                        { code: "lire_les_creneaux", libelle: { en: "Read free slots", fr: "Lire les créneaux libres" }, domaine: "agenda", traducteur: { systeme: "google_agenda", libelle: "Google Agenda" } },
                    ],
                },
            ],
        };
        try {
            await ouvrir(CONFIG_DE_REFERENCE as Record<string, unknown>, NOVA);
            const theme = ouvrirLeTheme("modules");
            await waitFor(() => expect(theme.querySelector('[data-besoin="lire_les_creneaux"]')?.textContent).toContain("Google Agenda"));
            const sousMenu = theme.querySelector('[data-sous-menu-module="planificateur"]') as HTMLElement;
            expect(sousMenu.querySelector("button")?.textContent).toContain("On");
            expect(sousMenu.querySelector('[data-allume-par-ses-outils="planificateur"]')).not.toBeNull();
        } finally {
            m.modules = undefined;
        }
    });

    it("« show » opens the sub-menu of a value to fix (E7)", async () => {
        await ouvrir({ ...(CONFIG_DE_REFERENCE as Record<string, unknown>), verification_communes: true, variables_commune: "ville; *" }, NOVA);
        const entete = document.querySelector('[data-theme="modules"] > button[aria-expanded]') as HTMLButtonElement;
        fireEvent.click(entete);
        expect(document.querySelector('[data-reglage="variables_commune"]')).toBeNull();
        fireEvent.click(await screen.findByRole("button", { name: "show" }));
        await waitFor(() => expect(document.querySelector('[data-theme="modules"] [data-reglage="variables_commune"]')).not.toBeNull());
    });
});

describe("[.mark] the agent page in themes", () => {
    it("draws every setting the inventory puts on screen, in its theme", async () => {
        await ouvrir(CONFIG_DE_REFERENCE as Record<string, unknown>, NOVA);
        for (const [cle, entree] of Object.entries(INVENTAIRE_AGENT)) {
            if ("horsEcran" in entree || "via" in entree || SEULEMENT_DANS_UN_MODE.includes(cle) || SEULEMENT_AVEC_CONTROLE.includes(cle) || SEULEMENT_DANS_UN_GROUPE.includes(cle) || SEULEMENT_AVEC_LE_TRAVAIL.includes(cle)) continue;
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

    // Cloture-code, lot 5 (M11): the settings templates button sits in the FIXED header, next to the agent's name,
    // outside the themes, and opens the centred modal.
    it("has the settings templates button in the fixed header, outside the themes", async () => {
        await ouvrir(CONFIG_DE_REFERENCE as Record<string, unknown>, NOVA);
        const bouton = document.querySelector("header [data-bouton-modeles]") as HTMLElement;
        expect(bouton, "the button is in the header").not.toBeNull();
        expect(document.querySelector("[data-theme] [data-bouton-modeles]")).toBeNull();
        fireEvent.click(bouton);
        await waitFor(() => expect(document.querySelector('[data-modale-phrase="modeles-de-reglages"]')).not.toBeNull());
    });

    // Plan mode-prise-de-notes, part 2: the clerk's settings are drawn only in
    // its mode, like in the code (no clerk, nothing to set).
    // Plan porte-parlee: « Transitions in the reply » only in Postscript (tested below).
    const SEULEMENT_EN_GREFFIER = ["greffier_llm", "greffier_consigne"];
    const SEULEMENT_DANS_UN_MODE = [
        ...SEULEMENT_EN_GREFFIER,
        "portes_dans_la_reponse",
        // Plan postscriptum-note-d-abord: Postscript only, like the transitions in the reply.
        "ordre_de_la_reponse",
        "indices_des_modules",
        // Chantier postscriptum-et-communes, B5: Postscript, « note, reply » order only.
        "phrase_sans_redemande",
    ];
    // Chantier l-agent-collegue, L7: the names of « Field recognition » are read only when « Check
    // the data » is on, and drawn only then (E8, the same rule as the code).
    // Lot 4 d'orchestrateur-trois-cerveaux: drawn only with « Background work » on (tested below).
    const SEULEMENT_AVEC_LE_TRAVAIL = ["travail_llm", "travail_consigne", "travail_outils", "travail_delai_max_s", "travail_llm_repli"];
    const SEULEMENT_AVEC_CONTROLE = ["variables_telephone", "variables_code_postal", "variables_courriel", "variables_date"];
    // Chantier agents-specialises, lot 12: the group's settings are drawn only for a main agent (or, for the
    // brain, a specialised one): a lone agent's page is what it was (tested below).
    const SEULEMENT_DANS_UN_GROUPE = [
        "prechauffage_agents",
        "passation_sans_resume_jusqua",
        "un_seul_renvoi_par_appel",
        "passations_max_par_appel",
        // Lot 2 d'orchestrateur-trois-cerveaux (B2): under « Specialised agents », a main agent only.
        "filet_de_fin",
        "attente",
        "transfert_humain",
        "cerveau_propre",
    ];
    it("draws the fields recognised by their name only with « Check the data » on", async () => {
        await ouvrir(CONFIG_DE_REFERENCE as Record<string, unknown>, NOVA);
        // cloture-code, F8: « Field recognition » moved to the theme « Modules », same rule (E8).
        let theme = ouvrirLeTheme("modules");
        await waitFor(() => expect(theme.querySelector('[data-reglage="controle_donnees"]')).not.toBeNull());
        for (const cle of SEULEMENT_AVEC_CONTROLE) expect(theme.querySelector(`[data-reglage="${cle}"]`), cle).toBeNull();
        cleanup();
        await ouvrir({ ...(CONFIG_DE_REFERENCE as Record<string, unknown>), controle_donnees: true }, NOVA);
        theme = ouvrirLeTheme("modules");
        for (const cle of SEULEMENT_AVEC_CONTROLE) {
            await waitFor(() => expect(theme.querySelector(`[data-reglage="${cle}"]`), cle).not.toBeNull());
        }
    });
    it("draws the clerk's settings in the clerk mode only", async () => {
        await ouvrir({ ...(CONFIG_DE_REFERENCE as Record<string, unknown>), fiche_mode_de_note: "greffier" }, NOVA);
        const theme = ouvrirLeTheme("donnees");
        for (const cle of SEULEMENT_EN_GREFFIER) {
            await waitFor(() => expect(theme.querySelector(`[data-reglage="${cle}"]`), cle).not.toBeNull());
        }
        cleanup();
        await ouvrir(CONFIG_DE_REFERENCE as Record<string, unknown>, NOVA);
        const outil = ouvrirLeTheme("donnees");
        await waitFor(() => expect(outil.querySelector('[data-reglage="fiche_mode_de_note"]')).not.toBeNull());
        for (const cle of SEULEMENT_EN_GREFFIER) expect(outil.querySelector(`[data-reglage="${cle}"]`), cle).toBeNull();
    });

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
    const NE_JOUENT_PAS = ["user_speech_timeout", "stt_ttfs_p99_latency", "turn_wait_for_transcript"];
    const SONIOX_DECIDE = { stt: { provider: "soniox", model: "stt-rt-v3", endpoint_detection: true } };

    for (const [nom, transcription] of [["Flux", FLUX], ["Soniox deciding", SONIOX_DECIDE]] as const) {
        it(`${nom}: shows the settings that play, hides the ones that do not, and says which is which`, async () => {
            // Lot 8: « The provider decides » for the start, so the interim transcripts (they feed the word count) stay hidden.
            await ouvrir({ turn_stop_strategy: "turn_analyzer", turn_start_strategy: "default" }, transcription);
            const tour = ouvrirLeTheme("tour");
            for (const id of JOUENT) expect(document.getElementById(id), id).not.toBeNull();
            for (const id of [...NE_JOUENT_PAS, "turn_start_use_interim", "smart_turn_pre_speech_ms", "smart_turn_max_duration_secs"]) {
                expect(document.getElementById(id), id).toBeNull();
            }
            const note = tour.querySelector('[data-note="tour-pilote"]');
            expect(note).not.toBeNull();
            expect(note?.textContent).not.toMatch(/builds none|ne construit aucun/i);
            // D-C9-2 and D-C9-4: the two strategies stay; the end of the turn says it has no effect here.
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

    // Lot 8 of cloture-code-avant-migration (Evan, 22/10): the START and the END of the turn are two
    // independent choices of this theme, so an A/B test is a few clicks.
    describe("two independent choices: start and end of the turn", () => {
        const INK2 = { stt: { provider: "cartesia", model: "ink-2" } };
        const SONIOX_LOCAL = { stt: { provider: "soniox", model: "stt-rt-v3", endpoint_detection: false } };
        const lesOptions = (id: string) => [...(document.getElementById(id) as HTMLSelectElement).options].map((o) => [o.value, o.textContent]);
        const choisir = (id: string, valeur: string) => fireEvent.change(document.getElementById(id) as HTMLSelectElement, { target: { value: valeur } });
        const enregistrerTour = async () => {
            m.save.mockClear();
            fireEvent.click(await screen.findByRole("button", { name: "Save Turn taking" }));
            await waitFor(() => expect(m.save).toHaveBeenCalled());
            const appels = m.save.mock.calls as unknown as Array<[Record<string, unknown>]>;
            return appels[appels.length - 1][0];
        };

        it("words the start of the turn « The provider decides » / « Minimum number of words », values unchanged", async () => {
            await ouvrir({}, NOVA);
            ouvrirLeTheme("tour");
            expect(lesOptions("turn_start_strategy")).toEqual([
                ["default", "The provider decides"],
                ["min_words", "Minimum number of words"],
            ]);
            cleanup();
            await ouvrir({}, NOVA, (page) => <FournisseurLangue>{page}</FournisseurLangue>);
            ouvrirLeTheme("tour");
            expect(lesOptions("turn_start_strategy")).toEqual([
                ["default", "Le fournisseur décide"],
                ["min_words", "Nombre minimum de mots"],
            ]);
        });

        for (const [nom, transcription] of [["Flux", FLUX], ["Soniox deciding", SONIOX_DECIDE], ["ink-2", INK2]] as const) {
            it(`${nom}: « Minimum number of words » plays, so the « no effect » note of the interruption is gone`, async () => {
                await ouvrir({ turn_start_strategy: "min_words" }, transcription);
                const tour = ouvrirLeTheme("tour");
                expect(tour.querySelector('[data-note="sans-effet-interruption"]')).toBeNull();
                expect(document.getElementById("turn_start_min_words")).not.toBeNull();
                expect(document.getElementById("turn_start_use_interim")).not.toBeNull();
                // The end of the turn stays the provider's: its note and its hidden settings are still right.
                expect(tour.querySelector('[data-note="sans-effet-fin-de-tour"]')).not.toBeNull();
                expect(document.getElementById("user_speech_timeout")).toBeNull();
            });
        }

        it("Flux: the end of the turn is frozen on the provider, with the model of the same brand that lets Dograh decide", async () => {
            await ouvrir({}, FLUX);
            const tour = ouvrirLeTheme("tour");
            const menu = document.getElementById("fin_de_tour_decideur") as HTMLSelectElement;
            expect(menu.disabled).toBe(true);
            expect(menu.value).toBe("fournisseur");
            expect(lesOptions("fin_de_tour_decideur")).toEqual([["fournisseur", "The provider decides"]]);
            expect(tour.querySelector('[data-note="fin-de-tour-figee"]')?.textContent).toContain("Nova-3");
        });

        it("ink-2: frozen too, with Ink-Whisper as the model that lets Dograh decide", async () => {
            await ouvrir({}, INK2);
            const tour = ouvrirLeTheme("tour");
            expect((document.getElementById("fin_de_tour_decideur") as HTMLSelectElement).disabled).toBe(true);
            expect(tour.querySelector('[data-note="fin-de-tour-figee"]')?.textContent).toContain("Ink-Whisper");
        });

        it("a provider that announces no turns: « Dograh decides », with no other choice", async () => {
            await ouvrir({}, NOVA);
            const tour = ouvrirLeTheme("tour");
            const menu = document.getElementById("fin_de_tour_decideur") as HTMLSelectElement;
            expect(menu.disabled).toBe(true);
            expect(lesOptions("fin_de_tour_decideur")).toEqual([["dograh", "Dograh decides"]]);
            expect(tour.querySelector('[data-note="fin-de-tour-figee"]')).toBeNull();
        });

        it("claims nothing when the screen cannot read the transcription", async () => {
            await ouvrir({}, null);
            ouvrirLeTheme("tour");
            expect(document.getElementById("fin_de_tour_decideur")).toBeNull();
        });

        it("Soniox: a real choice; « Dograh decides » brings the settings and drops the notes at once", async () => {
            await ouvrir({}, SONIOX_DECIDE);
            const tour = ouvrirLeTheme("tour");
            expect((document.getElementById("fin_de_tour_decideur") as HTMLSelectElement).disabled).toBe(false);
            expect(lesOptions("fin_de_tour_decideur")).toEqual([
                ["fournisseur", "The provider decides"],
                ["dograh", "Dograh decides"],
            ]);
            expect(tour.querySelector('[data-note="sans-effet-fin-de-tour"]')).not.toBeNull();
            expect(document.getElementById("user_speech_timeout")).toBeNull();

            choisir("fin_de_tour_decideur", "dograh");
            await waitFor(() => expect(tour.querySelector('[data-note="sans-effet-fin-de-tour"]')).toBeNull());
            expect(tour.querySelector('[data-note="tour-pilote"]')).toBeNull();
            expect(document.getElementById("user_speech_timeout")).not.toBeNull();
        });

        it("Soniox: « Dograh decides » writes endpoint_detection = false in a per-service overlay, nothing else of the transcription", async () => {
            await ouvrir({}, SONIOX_DECIDE);
            ouvrirLeTheme("tour");
            choisir("fin_de_tour_decideur", "dograh");
            const charge = await enregistrerTour();
            expect(charge.model_overrides).toEqual({ stt: { endpoint_detection: false } });
            expect(charge.mark_per_service_override).toBe(true);
            expect(charge.model_configuration_v2_override).toBeUndefined();
        });

        it("Soniox in local detection: « The provider decides » writes endpoint_detection = true next to the overlay the agent already has", async () => {
            await ouvrir({ model_overrides: { stt: { provider: "soniox", model: "stt-rt-v3", endpoint_detection: false, language: "fr" }, tts: { voice: "v1" } } }, SONIOX_LOCAL);
            ouvrirLeTheme("tour");
            expect((document.getElementById("fin_de_tour_decideur") as HTMLSelectElement).value).toBe("dograh");
            choisir("fin_de_tour_decideur", "fournisseur");
            const charge = await enregistrerTour();
            expect(charge.model_overrides).toEqual({
                stt: { provider: "soniox", model: "stt-rt-v3", endpoint_detection: true, language: "fr" },
                tts: { voice: "v1" },
            });
        });

        it("Soniox: an agent with a full configuration of its own gets the value in THAT configuration", async () => {
            const complete = {
                mode: "byok",
                byok: { mode: "pipeline", pipeline: { stt: { provider: "soniox", model: "stt-rt-v3", endpoint_detection: true }, tts: { provider: "x" } } },
            };
            await ouvrir({ model_configuration_v2_override: complete }, null);
            ouvrirLeTheme("tour");
            choisir("fin_de_tour_decideur", "dograh");
            const charge = await enregistrerTour();
            expect(charge.model_overrides).toBeUndefined();
            expect(charge.model_configuration_v2_override).toEqual({
                mode: "byok",
                byok: { mode: "pipeline", pipeline: { stt: { provider: "soniox", model: "stt-rt-v3", endpoint_detection: false }, tts: { provider: "x" } } },
            });
        });

        it("saving nothing about the end of the turn when the choice is left alone", async () => {
            await ouvrir({}, SONIOX_DECIDE);
            ouvrirLeTheme("tour");
            choisir("turn_start_strategy", "min_words");
            const charge = await enregistrerTour();
            expect(charge.model_overrides).toBeUndefined();
            expect(charge.mark_per_service_override).toBeUndefined();
        });
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

    it("offers the three modes, the clerk included (part 2)", async () => {
        await ouvrir(FICHE, NOVA);
        ouvrirLeTheme("donnees");
        await waitFor(() => expect(menu()).not.toBeNull());
        const options = Array.from(menu()!.options).map((o) => [o.value, o.disabled]);
        expect(options).toEqual([
            ["outil", false],
            ["post_scriptum", false],
            ["greffier", false],
        ]);
    });
});

describe("[.mark] the clerk's dialog (plan mode-prise-de-notes, part 2; D9 of agent-leger-greffier)", () => {
    const MASQUE = "sk-***abcd";
    const GREFFIER = {
        fiche_au_fil_de_leau: true,
        fiche_mode_de_note: "greffier",
        fiche_champs: [{ nom: "nom", type: "string", origine: "dicte", description: "Nom", lecteur: null, valeurs: null }],
        greffier_llm: { provider: "mistral", model: "mistral-small-2603", api_key: MASQUE },
    };
    const envoye = () => {
        const appels = m.save.mock.calls as unknown as Array<[Record<string, unknown>]>;
        return appels[appels.length - 1][0];
    };
    const enregistrer = async () => {
        m.save.mockClear();
        fireEvent.click(await screen.findByRole("button", { name: "Save Call data" }));
        await waitFor(() => expect(m.save).toHaveBeenCalled());
        return envoye();
    };
    const regler = async (config: Record<string, unknown> = GREFFIER) => {
        await ouvrir(config, NOVA);
        ouvrirLeTheme("donnees");
        fireEvent.click(await screen.findByRole("button", { name: "Configure the clerk" }));
        await waitFor(() => expect(document.getElementById("greffier_model")).not.toBeNull());
    };
    const saisir = (id: string, valeur: string) =>
        fireEvent.change(document.getElementById(id) as HTMLElement, { target: { value: valeur } });
    const ouvrirLeGroupe = (nom: RegExp) => fireEvent.click(screen.getByRole("button", { name: nom }));
    const termine = async () => {
        fireEvent.click(screen.getByRole("button", { name: "Done" }));
        return enregistrer();
    };

    it("the saved key goes back as its mask, untouched, with the model changed", async () => {
        await regler();
        saisir("greffier_model", "mistral-large-2512");
        const charge = await termine();
        expect(charge.greffier_llm).toEqual({ provider: "mistral", model: "mistral-large-2512", api_key: MASQUE });
        expect(charge.greffier_consigne ?? null).toBeNull();
    });

    it("the provider's own settings are generated from its schema and saved in the block", async () => {
        await regler();
        saisir("greffier_provider", "openai");
        saisir("greffier_model", "mistral-small-3.2-24b-instruct-2506");
        ouvrirLeGroupe(/Generation/);
        saisir("greffier_reasoning_effort", "low");
        saisir("greffier_temperature", "0,2");
        ouvrirLeGroupe(/Technical/);
        saisir("greffier_base_url", "https://api.scaleway.ai/v1");
        const charge = await termine();
        // Another provider: the key and the settings of the previous one never carry over.
        expect(charge.greffier_llm).toEqual({
            provider: "openai",
            model: "mistral-small-3.2-24b-instruct-2506",
            reasoning_effort: "low",
            temperature: 0.2,
            base_url: "https://api.scaleway.ai/v1",
        });
    });

    it("« Guaranteed format » is unticked by default and absent from the block", async () => {
        await regler();
        expect(document.getElementById("greffier_format_garanti")?.getAttribute("aria-checked")).toBe("false");
        saisir("greffier_model", "mistral-large-2512");
        const charge = await termine();
        expect(charge.greffier_llm).toEqual({ provider: "mistral", model: "mistral-large-2512", api_key: MASQUE });
    });

    it("« Guaranteed format » is read from the block, saved in it, and survives a provider change", async () => {
        await regler({ ...GREFFIER, greffier_llm: { ...GREFFIER.greffier_llm, format_garanti: true } });
        expect(document.getElementById("greffier_format_garanti")?.getAttribute("aria-checked")).toBe("true");
        saisir("greffier_provider", "openai");
        saisir("greffier_model", "x");
        const charge = await termine();
        expect(charge.greffier_llm).toEqual({ provider: "openai", model: "x", format_garanti: true });
    });

    it("ticking « Guaranteed format » alone saves it in the block", async () => {
        await regler();
        fireEvent.click(document.getElementById("greffier_format_garanti") as HTMLElement);
        const charge = await termine();
        expect(charge.greffier_llm).toEqual({ ...GREFFIER.greffier_llm, format_garanti: true });
    });

    it("unticking « Guaranteed format » removes the key from the block", async () => {
        await regler({ ...GREFFIER, greffier_llm: { ...GREFFIER.greffier_llm, format_garanti: true } });
        fireEvent.click(document.getElementById("greffier_format_garanti") as HTMLElement);
        const charge = await termine();
        expect(charge.greffier_llm).toEqual(GREFFIER.greffier_llm);
    });

    it("a key of the library is kept as its reference, named and never shown", async () => {
        const ref = "mark-cle:343322ca-f4d1-4806-8bf6-b2c7ed904a4a";
        await regler({ ...GREFFIER, greffier_llm: { provider: "openai", model: "x", api_key: ref } });
        expect(screen.getByTestId("cle-de-la-bibliotheque")).toBeTruthy();
        const charge = await termine().catch(() => null);
        // Nothing changed: the theme has nothing to save, the reference stays as it is.
        expect(charge === null || (charge.greffier_llm as Record<string, unknown>).api_key === ref).toBe(true);
    });

    it("an emptied setting leaves the block: it then comes from the conversation", async () => {
        await regler({ ...GREFFIER, greffier_llm: { provider: "mistral", model: "m", temperature: 0.3 } });
        ouvrirLeGroupe(/Generation/);
        saisir("greffier_temperature", "");
        const charge = await termine();
        expect(charge.greffier_llm).toEqual({ provider: "mistral", model: "m" });
    });

    it("« as the conversation » empties the block, and no key nor setting is offered", async () => {
        await regler();
        saisir("greffier_provider", "__comme_la_conversation__");
        expect(document.querySelector("[data-champ-fournisseur]")).toBeNull();
        expect(screen.queryByText("API key")).toBeNull();
        const charge = await termine();
        expect(charge.greffier_llm ?? null).toBeNull();
    });

    it("instructions back to the template are sent empty", async () => {
        await ouvrir({ ...GREFFIER, greffier_consigne: "Tu tiens la fiche." }, NOVA);
        ouvrirLeTheme("donnees");
        fireEvent.click(await screen.findByRole("button", { name: "Edit the instructions" }));
        await waitFor(() => expect((document.getElementById("greffier_consigne") as HTMLTextAreaElement).value).toBe("Tu tiens la fiche."));
        fireEvent.click(screen.getByRole("button", { name: "Back to the template" }));
        expect((document.getElementById("greffier_consigne") as HTMLTextAreaElement).value).toBe(CONSIGNE_GENERIQUE_GREFFIER);
        fireEvent.click(screen.getByRole("button", { name: "Done" }));
        const charge = await enregistrer();
        expect(charge.greffier_consigne).toBeNull();
        expect(charge.greffier_llm).toEqual(GREFFIER.greffier_llm);
    });
});


// [.mark] passages-fiables, lot B: the arbiter's brain, the clerk's dialog to the letter (same place, same form, same key rule).
describe("[.mark] the arbiter's dialog (passages-fiables, lot B)", () => {
    const MASQUE = "sk-***abcd";
    const AVEC_ARBITRE = { arbitre_llm: { provider: "mistral", model: "mistral-small-2603", api_key: MASQUE } };
    const envoye = () => {
        const appels = m.save.mock.calls as unknown as Array<[Record<string, unknown>]>;
        return appels[appels.length - 1][0];
    };
    const regler = async (config: Record<string, unknown> = AVEC_ARBITRE) => {
        await ouvrir({ ...(CONFIG_DE_REFERENCE as Record<string, unknown>), ...config }, NOVA);
        ouvrirLeTheme("donnees");
        fireEvent.click(await screen.findByRole("button", { name: "Configure the arbiter" }));
        await waitFor(() => expect(document.getElementById("arbitre_model")).not.toBeNull());
    };
    const saisir = (id: string, valeur: string) =>
        fireEvent.change(document.getElementById(id) as HTMLElement, { target: { value: valeur } });
    const termine = async () => {
        fireEvent.click(screen.getByRole("button", { name: "Done" }));
        m.save.mockClear();
        fireEvent.click(await screen.findByRole("button", { name: "Save Call data" }));
        await waitFor(() => expect(m.save).toHaveBeenCalled());
        return envoye();
    };

    it("names its own brain in the help under « API key » (the clerk's window keeps its own words)", async () => {
        await regler();
        const aideArbitre = document.getElementById("arbitre_api_key")?.closest("div.space-y-1")?.querySelector("p.text-xs")?.textContent ?? "";
        expect(aideArbitre).toContain("Empty, the arbiter uses the conversation's key");
        expect(aideArbitre).not.toContain("clerk");
    });

    it("is drawn next to the clerk's settings, in every note-taking mode, with its own key rule", async () => {
        await ouvrir(CONFIG_DE_REFERENCE as Record<string, unknown>, NOVA);
        const theme = ouvrirLeTheme("donnees");
        await waitFor(() => expect(theme.querySelector('[data-reglage="arbitre_llm"]')).not.toBeNull());
        expect(screen.getByText("The clerk's model · conversation's key")).toBeTruthy();
    });

    it("the saved key goes back as its mask, untouched, with the model changed", async () => {
        await regler();
        saisir("arbitre_model", "mistral-small-3.2");
        const charge = await termine();
        expect(charge.arbitre_llm).toEqual({ provider: "mistral", model: "mistral-small-3.2", api_key: MASQUE });
    });

    it("the provider's own settings are generated from its schema, with the arbiter's ids", async () => {
        await regler({});
        saisir("arbitre_provider", "openai");
        saisir("arbitre_model", "mistral-small-3.2-24b-instruct-2506");
        const charge = await termine();
        expect(charge.arbitre_llm).toEqual({ provider: "openai", model: "mistral-small-3.2-24b-instruct-2506" });
        expect(document.getElementById("greffier_model")).toBeNull();
    });

    it("« as the conversation » empties the block: the clerk's model is used again", async () => {
        await regler();
        saisir("arbitre_provider", "__comme_la_conversation__");
        expect(document.querySelector("[data-champ-fournisseur]")).toBeNull();
        const charge = await termine();
        expect(charge.arbitre_llm ?? null).toBeNull();
    });

    it("an untouched page saves no arbiter block (absent block = today's behaviour)", async () => {
        await ouvrir(CONFIG_DE_REFERENCE as Record<string, unknown>, NOVA);
        ouvrirLeTheme("donnees");
        const bouton = await screen.findByRole("button", { name: "Save Call data" });
        expect((bouton as HTMLButtonElement).disabled).toBe(true);
    });
});


// [.mark] Plan porte-parlee, lot 6: « Transitions in the reply », rendered.
describe("[.mark] transitions in the reply, in the call data theme", () => {
    const FICHE = {
        fiche_au_fil_de_leau: true,
        fiche_champs: [{ nom: "nom", type: "string", origine: "dicte", description: "Nom", lecteur: null, valeurs: null }],
    };
    const POST_SCRIPTUM = { ...FICHE, fiche_mode_de_note: "post_scriptum" };
    const caseAPorte = () => document.getElementById("portes_dans_la_reponse");
    const GRAPHE = {
        nodes: [
            { id: "start", type: "startCall", data: { name: "Accueil" } },
            { id: "etape", type: "agentNode", data: { name: "Panne", premiere_replique: "Quelle marque ?" } },
            { id: "fin", type: "endCall", data: { name: "Clôture", premiere_replique: "  " } },
        ],
        edges: [
            { id: "a", source: "start", target: "etape" },
            { id: "b", source: "etape", target: "fin" },
        ],
    };
    const enregistrer = async () => {
        m.save.mockClear();
        fireEvent.click(await screen.findByRole("button", { name: "Save Call data" }));
        await waitFor(() => expect(m.save).toHaveBeenCalled());
        const appels = m.save.mock.calls as unknown as Array<[Record<string, unknown>]>;
        return appels[appels.length - 1][0];
    };
    afterEach(() => {
        m.definition = { nodes: [], edges: [] };
    });

    it("is shown in Postscript and in Clerk mode, never in Tool mode, like in the code", async () => {
        await ouvrir(FICHE, NOVA);
        ouvrirLeTheme("donnees");
        await waitFor(() => expect(document.getElementById("fiche_mode_de_note")).not.toBeNull());
        expect(caseAPorte()).toBeNull();
        fireEvent.change(document.getElementById("fiche_mode_de_note") as HTMLElement, { target: { value: "post_scriptum" } });
        await waitFor(() => expect(caseAPorte()).not.toBeNull());
        // greffier-conversation, lot A (D2): the clerk takes its transitions in the reply too.
        fireEvent.change(document.getElementById("fiche_mode_de_note") as HTMLElement, { target: { value: "greffier" } });
        await waitFor(() => expect(caseAPorte()).not.toBeNull());
        fireEvent.change(document.getElementById("fiche_mode_de_note") as HTMLElement, { target: { value: "outil" } });
        await waitFor(() => expect(caseAPorte()).toBeNull());
    });

    it("sends the box in Clerk mode (greffier-conversation, lot A)", async () => {
        await ouvrir({ ...FICHE, fiche_mode_de_note: "greffier" }, NOVA);
        ouvrirLeTheme("donnees");
        await waitFor(() => expect(caseAPorte()).not.toBeNull());
        fireEvent.click(caseAPorte() as HTMLElement);
        const charge = await enregistrer();
        expect(charge.portes_dans_la_reponse).toBe(true);
        expect(charge.fiche_mode_de_note).toBe("greffier");
    });

    it("is off for an agent saved before it, and reads back what the server stored", async () => {
        await ouvrir(POST_SCRIPTUM, NOVA);
        ouvrirLeTheme("donnees");
        await waitFor(() => expect(caseAPorte()?.getAttribute("aria-checked")).toBe("false"));
        cleanup();
        await ouvrir({ ...POST_SCRIPTUM, portes_dans_la_reponse: true }, NOVA);
        ouvrirLeTheme("donnees");
        await waitFor(() => expect(caseAPorte()?.getAttribute("aria-checked")).toBe("true"));
    });

    it("sends the box when switched on", async () => {
        await ouvrir(POST_SCRIPTUM, NOVA);
        ouvrirLeTheme("donnees");
        await waitFor(() => expect(caseAPorte()).not.toBeNull());
        fireEvent.click(caseAPorte() as HTMLElement);
        const charge = await enregistrer();
        expect(charge.portes_dans_la_reponse).toBe(true);
        expect(charge.fiche_mode_de_note).toBe("post_scriptum");
    });

    it("leaving Postscript sends the box off, or the server would refuse the save", async () => {
        await ouvrir({ ...POST_SCRIPTUM, portes_dans_la_reponse: true }, NOVA);
        ouvrirLeTheme("donnees");
        await waitFor(() => expect(caseAPorte()).not.toBeNull());
        fireEvent.change(document.getElementById("fiche_mode_de_note") as HTMLElement, { target: { value: "outil" } });
        const charge = await enregistrer();
        expect(charge.fiche_mode_de_note).toBe("outil");
        expect(charge.portes_dans_la_reponse).toBe(false);
    });

    it("names the steps a transition leads to that have no first reply, without blocking", async () => {
        m.definition = GRAPHE;
        await ouvrir({ ...POST_SCRIPTUM, portes_dans_la_reponse: true }, NOVA);
        ouvrirLeTheme("donnees");
        const note = await screen.findByRole("note");
        expect(note.textContent).toContain("Steps without a first reply");
        expect(note.textContent).toContain("Clôture");
        expect(note.textContent).not.toContain("Panne");
        expect(note.textContent).not.toContain("Accueil");
        // Not an error: the theme's button is not blocked.
        fireEvent.click(caseAPorte() as HTMLElement);
        fireEvent.click(caseAPorte() as HTMLElement);
        expect(screen.queryByRole("note")).not.toBeNull();
    });
});

// [.mark] Constat B4 de la réparation globale: le bouton Enregistrer d'un thème reste gris quand
// seuls « Ordre de la réponse » ou « Indices des modules » changent.
describe("[.mark] the save button follows the reply order and the module hints", () => {
    const POST_SCRIPTUM = {
        fiche_au_fil_de_leau: true,
        fiche_champs: [{ nom: "nom", type: "string", origine: "dicte", description: "Nom", lecteur: null, valeurs: null }],
        fiche_mode_de_note: "post_scriptum",
    };
    const bouton = async () => (await screen.findByRole("button", { name: "Save Call data" })) as HTMLButtonElement;

    it("is grey with nothing changed", async () => {
        await ouvrir(POST_SCRIPTUM, NOVA);
        ouvrirLeTheme("donnees");
        await waitFor(() => expect(document.getElementById("indices_des_modules")).not.toBeNull());
        expect((await bouton()).disabled).toBe(true);
    });

    it("turns on when only the module hints switch is flipped", async () => {
        await ouvrir(POST_SCRIPTUM, NOVA);
        ouvrirLeTheme("donnees");
        await waitFor(() => expect(document.getElementById("indices_des_modules")).not.toBeNull());
        fireEvent.click(document.getElementById("indices_des_modules") as HTMLElement);
        await waitFor(async () => expect((await bouton()).disabled).toBe(false));
    });

    it("turns on when only the reply order is changed", async () => {
        await ouvrir(POST_SCRIPTUM, NOVA);
        ouvrirLeTheme("donnees");
        await waitFor(() => expect(document.getElementById("ordre_de_la_reponse")).not.toBeNull());
        fireEvent.change(document.getElementById("ordre_de_la_reponse") as HTMLElement, { target: { value: "porte_note_phrase" } });
        await waitFor(async () => expect((await bouton()).disabled).toBe(false));
    });
});

// [.mark] Chantier postscriptum-et-communes, B5: « No repeated question » lives in the Data theme,
// only in Postscript with the « Transition, note, reply » order, off by default.
describe("[.mark] the no-repeated-question switch", () => {
    const BASE = {
        fiche_au_fil_de_leau: true,
        fiche_champs: [{ nom: "nom", type: "string", origine: "dicte", description: "Nom", lecteur: null, valeurs: null }],
        fiche_mode_de_note: "post_scriptum",
    };
    const bouton = async () => (await screen.findByRole("button", { name: "Save Call data" })) as HTMLButtonElement;
    const interrupteur = () => document.getElementById("phrase_sans_redemande");

    it("is drawn in the Data theme with the note-first order, off", async () => {
        await ouvrir({ ...BASE, ordre_de_la_reponse: "porte_note_phrase" }, NOVA);
        ouvrirLeTheme("donnees");
        await waitFor(() => expect(interrupteur()).not.toBeNull());
        expect(interrupteur()?.getAttribute("aria-checked")).toBe("false");
        expect((await bouton()).disabled).toBe(true);
    });

    it("is not drawn with the order of before", async () => {
        await ouvrir(BASE, NOVA);
        ouvrirLeTheme("donnees");
        await waitFor(() => expect(document.getElementById("indices_des_modules")).not.toBeNull());
        expect(interrupteur()).toBeNull();
    });

    it("turns the save button on when flipped", async () => {
        await ouvrir({ ...BASE, ordre_de_la_reponse: "porte_note_phrase" }, NOVA);
        ouvrirLeTheme("donnees");
        await waitFor(() => expect(interrupteur()).not.toBeNull());
        fireEvent.click(interrupteur() as HTMLElement);
        await waitFor(async () => expect((await bouton()).disabled).toBe(false));
    });
});

// [.mark] Chantier repliques-coupees, lot 6 bis (D16), then schema-parcours-unique (C1, C2, C6):
// one flow map box, the retry reasoning and the model request trace, all in the Agent theme.
describe("[.mark] the flow map, the retry reasoning and the model request trace", () => {
    const FICHE = {
        fiche_au_fil_de_leau: true,
        fiche_champs: [{ nom: "nom", type: "string", origine: "dicte", description: "Nom", lecteur: null, valeurs: null }],
    };
    const GREFFIER = { ...FICHE, fiche_mode_de_note: "greffier", portes_dans_la_reponse: true };
    const relance = () => document.getElementById("reflexion_de_relance") as HTMLSelectElement | null;
    const enregistrer = async (theme: string) => {
        m.save.mockClear();
        fireEvent.click(await screen.findByRole("button", { name: `Save ${theme}` }));
        await waitFor(() => expect(m.save).toHaveBeenCalled());
        const appels = m.save.mock.calls as unknown as Array<[Record<string, unknown>]>;
        return appels[appels.length - 1][0];
    };

    it("draws the map and the retry reasoning in the Agent theme, in every mode (C6)", async () => {
        for (const config of [FICHE, GREFFIER, { ...FICHE, fiche_mode_de_note: "post_scriptum" }]) {
            await ouvrir(config, NOVA);
            const theme = ouvrirLeTheme("agent");
            await waitFor(() => expect(theme.querySelector('[data-reglage="reflexion_de_relance"]')).not.toBeNull());
            expect(theme.querySelector('[data-reglage="generer_schema_parcours"]')).not.toBeNull();
            expect(relance()?.value).toBe("reglage_de_l_agent");
            cleanup();
        }
    });

    it("no longer draws « Readable flow » nor the retry reasoning in Call data", async () => {
        await ouvrir({ ...GREFFIER, parcours_lisible: true, reflexion_de_relance: "low" }, NOVA);
        const theme = ouvrirLeTheme("donnees");
        await waitFor(() => expect(theme.querySelector('[data-reglage="portes_dans_la_reponse"]')).not.toBeNull());
        expect(theme.querySelector('[data-reglage="parcours_lisible"]')).toBeNull();
        expect(theme.querySelector('[data-reglage="reflexion_de_relance"]')).toBeNull();
        expect(document.getElementById("parcours_lisible")).toBeNull();
    });

    it("reads back what the server stored", async () => {
        await ouvrir({ ...GREFFIER, generer_schema_parcours: true, reflexion_de_relance: "low" }, NOVA);
        ouvrirLeTheme("agent");
        await waitFor(() => expect(relance()?.value).toBe("low"));
        expect(document.getElementById("generer_schema_parcours")?.getAttribute("aria-checked")).toBe("true");
    });

    it("sends the retry reasoning alone, and an empty one back as null", async () => {
        await ouvrir({ ...GREFFIER, reflexion_de_relance: "low" }, NOVA);
        ouvrirLeTheme("agent");
        await waitFor(() => expect(relance()).not.toBeNull());
        fireEvent.change(relance() as HTMLElement, { target: { value: "reglage_de_l_agent" } });
        const charge = await enregistrer("Agent");
        expect(charge.reflexion_de_relance).toBeNull();
        expect("generer_schema_parcours" in charge).toBe(false);
        expect("trace_requetes_modele" in charge).toBe(false);
    });

    it("draws the trace in the Agent theme, off, and sends it when switched on", async () => {
        await ouvrir(FICHE, NOVA);
        ouvrirLeTheme("agent");
        const trace = () => document.getElementById("trace_requetes_modele");
        await waitFor(() => expect(trace()).not.toBeNull());
        expect(trace()?.getAttribute("aria-checked")).toBe("false");
        fireEvent.click(trace() as HTMLElement);
        const charge = await enregistrer("Agent");
        expect(charge.trace_requetes_modele).toBe(true);
    });
    // ---- Chantier agents-specialises, lot 12: the group's screens ---------------------------------------
    const PRINCIPAL = { ...(CONFIG_DE_REFERENCE as Record<string, unknown>), agents_specialises: [7, 8] };
    const SPECIALISE = { ...(CONFIG_DE_REFERENCE as Record<string, unknown>), agent_principal_id: 5 };
    const REGLAGES_DU_GROUPE = [
        "prechauffage_agents",
        "passation_sans_resume_jusqua",
        "un_seul_renvoi_par_appel",
        "passations_max_par_appel",
    ];

    it("draws « Specialised agents » and « Waiting » for a main agent, with the defaults of a group", async () => {
        await ouvrir(PRINCIPAL, NOVA);
        const agent = ouvrirLeTheme("agent");
        await waitFor(() => expect(agent.querySelector('[data-groupe="agent-agents-specialises"]')).not.toBeNull());
        for (const cle of REGLAGES_DU_GROUPE) expect(agent.querySelector('[data-reglage="' + cle + '"]'), cle).not.toBeNull();
        // Defaults of a group: pre-warming on, 40 messages, one transfer, ceiling 6.
        expect(document.getElementById("prechauffage_agents")?.getAttribute("aria-checked")).toBe("true");
        expect((document.getElementById("passation_sans_resume_jusqua") as HTMLInputElement).value).toBe("40");
        expect(document.getElementById("un_seul_renvoi_par_appel")?.getAttribute("aria-checked")).toBe("true");
        expect((document.getElementById("passations_max_par_appel") as HTMLInputElement).value).toBe("6");
        const voix = ouvrirLeTheme("voix");
        await waitFor(() => expect(voix.querySelector('[data-groupe="voix-attente"]')).not.toBeNull());
        // fiabilite-orchestration, lot 4 bis: the bridge phrase and the hand-over sentence moved to the theme Phrases.
        expect(voix.querySelector('[data-note="phrases-deplacees"]')).not.toBeNull();
        for (const cle of ["attente.son", "attente.duree_min_s", "attente.passation", "attente.transfert_humain"]) {
            expect(voix.querySelector('[data-reglage="' + cle + '"]'), cle).not.toBeNull();
        }
        // The text that says no waiting is played towards an agent already built.
        expect(voix.querySelector('[data-note="attente-agent-construit"]')).not.toBeNull();
    });

    it("draws none of the group's settings for a lone agent, and no banner", async () => {
        await ouvrir(CONFIG_DE_REFERENCE as Record<string, unknown>, NOVA);
        const agent = ouvrirLeTheme("agent");
        await waitFor(() => expect(agent.querySelector('[data-reglage="trace_requetes_modele"]')).not.toBeNull());
        expect(agent.querySelector('[data-groupe="agent-agents-specialises"]')).toBeNull();
        const voix = ouvrirLeTheme("voix");
        await waitFor(() => expect(voix.querySelector('[data-reglage="tts_cache_enabled"]')).not.toBeNull());
        expect(voix.querySelector('[data-groupe="voix-attente"]')).toBeNull();
        expect(document.querySelector('[data-bandeau="regle-sur-le-principal"]')).toBeNull();
        expect(document.querySelector('[data-lecture="commune"]')).toBeNull();
        ouvrirLeTheme("briques");
        await waitFor(() => expect(document.querySelector('[data-theme="briques"] [data-reglage="model_configuration_v2_override"]')).not.toBeNull());
        expect(document.getElementById("cerveau_propre")).toBeNull();
    });

    it("greys out « Generate the flow map » in a group (the code always generates it), never for a lone agent", async () => {
        const interrupteur = () => document.getElementById("generer_schema_parcours") as HTMLElement;
        const aide = () => document.querySelector('[data-reglage="generer_schema_parcours"]')?.textContent ?? "";
        for (const [config, force] of [
            [PRINCIPAL, true],
            [SPECIALISE, true],
            [{ ...PRINCIPAL, agents_specialises: [] }, false], // a main agent with no specialised agent yet: the server sees a lone agent
            [CONFIG_DE_REFERENCE as Record<string, unknown>, false],
        ] as const) {
            await ouvrir(config, NOVA);
            ouvrirLeTheme("agent");
            await waitFor(() => expect(interrupteur()).not.toBeNull());
            expect(interrupteur().hasAttribute("disabled"), JSON.stringify(Object.keys(config))).toBe(force);
            expect(aide().includes("Toujours actif dans un groupe") || aide().includes("Always on in a group")).toBe(force);
            if (force) expect(interrupteur().getAttribute("aria-checked")).toBe("true");
            cleanup();
        }
    });

    it("shows the common themes of a specialised agent read only, with the banner and no save button", async () => {
        await ouvrir(SPECIALISE, NOVA);
        for (const id of ["ecoute", "tour", "voix", "rythme", "donnees", "etablissement"]) {
            const theme = ouvrirLeTheme(id);
            await waitFor(() => expect(theme.querySelector('[data-bandeau="regle-sur-le-principal"]'), id).not.toBeNull());
            const lecture = theme.querySelector('[data-lecture="commune"]') as HTMLFieldSetElement;
            expect(lecture, id).not.toBeNull();
            expect(lecture.disabled, id).toBe(true);
            // The main agent's saves are the only way to change them: no « Save » of this theme.
            expect(theme.querySelector('button[aria-label^="Save "]'), id).toBeNull();
            // The link to the main agent.
            expect(theme.querySelector('a[href="/workflow/5/settings"]'), id).not.toBeNull();
        }
        // Its own themes stay editable: the name is not in a read only zone.
        const agent = ouvrirLeTheme("agent");
        await waitFor(() => expect(document.getElementById("workflow_name")).not.toBeNull());
        expect(document.getElementById("workflow_name")?.closest("fieldset[disabled]")).toBeNull();
        // The common part of the theme Agent (« Specialised agents ») is read only, the brain-bound ones too.
        expect(agent.querySelector('[data-groupe="agent-agents-specialises"]')?.closest("fieldset[disabled]")).not.toBeNull();
        expect(document.getElementById("trace_requetes_modele")?.closest("fieldset[disabled]")).not.toBeNull();
    });

    it("lets a specialised agent detach its brain, and shows the same menu read only until then", async () => {
        await ouvrir(SPECIALISE, NOVA);
        const briques = ouvrirLeTheme("briques");
        await waitFor(() => expect(document.getElementById("cerveau_propre")).not.toBeNull());
        const interrupteur = document.getElementById("cerveau_propre") as HTMLElement;
        expect(interrupteur.getAttribute("aria-checked")).toBe("false");
        expect(interrupteur.closest("fieldset[disabled]")).toBeNull();
        // Unticked: the menu below is the main agent's, read only.
        await waitFor(() => expect(briques.querySelector('[data-reglage="model_configuration_v2_override"]')).not.toBeNull());
        expect(briques.querySelector('[data-reglage="model_configuration_v2_override"]')?.closest("fieldset[disabled]")).not.toBeNull();
        expect(briques.querySelector('[data-bandeau="regle-sur-le-principal"]')).not.toBeNull();
        // Ticking saves at once, the key alone changed.
        m.save.mockClear();
        fireEvent.click(interrupteur);
        await waitFor(() => expect(m.save).toHaveBeenCalled());
        const charge = (m.save.mock.calls as unknown as Array<[Record<string, unknown>, string]>)[0][0];
        expect(charge.cerveau_propre).toBe(true);
        expect(charge.agent_principal_id).toBe(5);
    });

    it("draws the menu editable and the banner « detached » when the brain is its own", async () => {
        await ouvrir({ ...SPECIALISE, cerveau_propre: true }, NOVA);
        const briques = ouvrirLeTheme("briques");
        await waitFor(() => expect(briques.querySelector('[data-bandeau="cerveau-detache"]')).not.toBeNull());
        expect(document.getElementById("cerveau_propre")?.getAttribute("aria-checked")).toBe("true");
        expect(briques.querySelector('[data-reglage="model_configuration_v2_override"]')?.closest("fieldset[disabled]")).toBeNull();
        expect(briques.querySelector('[data-bandeau="regle-sur-le-principal"]')).toBeNull();
        // The retry reasoning follows the detached brain: editable again.
        ouvrirLeTheme("agent");
        await waitFor(() => expect(document.getElementById("reflexion_de_relance")).not.toBeNull());
        expect(document.getElementById("reflexion_de_relance")?.closest("fieldset[disabled]")).toBeNull();
        // The trace does not: one switch for the whole group, the main agent's (Evan, 19/10).
        expect(document.getElementById("trace_requetes_modele")?.closest("fieldset[disabled]")).not.toBeNull();
    });

    // Lot 3 d'orchestrateur-trois-cerveaux (D7): the call has one voice, the main agent's. Even with « Own brain »,
    // an agent of a group cannot change its voice; a lone agent and a main agent keep theirs.
    it("locks the voice of a specialised agent with its own brain, in both editors, and only there", async () => {
        const note = () => document.querySelectorAll('[data-bandeau="voix-de-l-appel"]').length;
        // Complete configuration of its own (the all-in-one editor).
        await ouvrir({ ...SPECIALISE, cerveau_propre: true, model_configuration_v2_override: { version: 2, mode: "dograh" } }, NOVA);
        ouvrirLeTheme("briques");
        await waitFor(() => expect(document.querySelector('[data-testid="editeur-v2"]')).not.toBeNull());
        expect(document.querySelector('[data-testid="editeur-v2"] [data-bandeau="voix-de-l-appel"]')).not.toBeNull();
        cleanup();
        // Service-by-service override (the form).
        await ouvrir({ ...SPECIALISE, cerveau_propre: true, model_overrides: { tts: { provider: "mistral" } } }, NOVA);
        ouvrirLeTheme("briques");
        await waitFor(() => expect(document.querySelector('[data-testid="formulaire-service"]')).not.toBeNull());
        expect(document.querySelector('[data-testid="formulaire-service"] [data-bandeau="voix-de-l-appel"]')).not.toBeNull();
        cleanup();
        // A main agent and a lone agent: the voice is theirs, no note anywhere.
        for (const config of [
            { ...PRINCIPAL, model_configuration_v2_override: { version: 2, mode: "dograh" } },
            { ...(CONFIG_DE_REFERENCE as Record<string, unknown>), model_overrides: { tts: { provider: "mistral" } } },
        ]) {
            await ouvrir(config, NOVA);
            ouvrirLeTheme("briques");
            await waitFor(() => expect(document.querySelector('[data-testid="editeur-v2"], [data-testid="formulaire-service"]')).not.toBeNull());
            expect(note()).toBe(0);
            cleanup();
        }
    });

    it("sends the group's four settings together, with their values, when one is changed", async () => {
        await ouvrir(PRINCIPAL, NOVA);
        ouvrirLeTheme("agent");
        await waitFor(() => expect(document.getElementById("passations_max_par_appel")).not.toBeNull());
        fireEvent.change(document.getElementById("passations_max_par_appel") as HTMLElement, { target: { value: "4" } });
        const charge = await enregistrer("Agent");
        expect(charge.passations_max_par_appel).toBe(4);
        expect(charge.prechauffage_agents).toBe(true);
        expect(charge.agents_specialises).toEqual([7, 8]);
    });
});

// Lot 4 d'orchestrateur-trois-cerveaux (D8, D10, D13): « Background work », in the Services theme (« Briques »).
describe("[.mark] the background work settings (lot 4)", () => {
    const REFERENCE = CONFIG_DE_REFERENCE as Record<string, unknown>;
    const SPECIALISE_LOT4 = { ...REFERENCE, agent_principal_id: 5 };
    const MASQUE_LOT4 = "sk-***abcd";
    const AUTRES = ["travail_llm", "travail_consigne", "travail_outils", "travail_delai_max_s"];
    const dernierEnvoi = () => {
        const appels = m.save.mock.calls as unknown as Array<[Record<string, unknown>, string]>;
        return appels[appels.length - 1];
    };
    const ouvrirBriques = async (config: Record<string, unknown>, enveloppe?: (n: ReactNode) => ReactNode) => {
        await ouvrir(config, NOVA, enveloppe);
        const theme = ouvrirLeTheme("briques");
        await waitFor(() => expect(document.getElementById("travail_actif")).not.toBeNull());
        return theme;
    };
    const saisirTravail = (id: string, valeur: string) =>
        fireEvent.change(document.getElementById(id) as HTMLElement, { target: { value: valeur } });

    it("draws only the switch while it is off", async () => {
        const briques = await ouvrirBriques(REFERENCE);
        expect(document.getElementById("travail_actif")?.getAttribute("aria-checked")).toBe("false");
        for (const cle of AUTRES) expect(briques.querySelector(`[data-reglage="${cle}"]`), cle).toBeNull();
    });

    it("turning it on saves at once with the switch alone, and draws the four other settings", async () => {
        await ouvrirBriques(REFERENCE);
        m.save.mockClear();
        fireEvent.click(document.getElementById("travail_actif") as HTMLElement);
        await waitFor(() => expect(m.save).toHaveBeenCalled());
        const [charge, nom] = dernierEnvoi();
        expect(charge.travail_actif).toBe(true);
        expect(nom).toBe("Agent");
        for (const cle of AUTRES) expect(charge[cle] ?? null, cle).toBeNull();
        cleanup();
        const allume = await ouvrirBriques({ ...REFERENCE, travail_actif: true });
        for (const cle of AUTRES) {
            await waitFor(() => expect(allume.querySelector(`[data-reglage="${cle}"]`), cle).not.toBeNull());
        }
    });

    it("offers the catalogue's tools minus a transfer, the end of the call and MCP, and saves the choice at once", async () => {
        await ouvrirBriques({ ...REFERENCE, travail_actif: true });
        const outil = await screen.findByRole("checkbox", { name: /Chercher un creneau/ });
        expect(screen.queryByRole("checkbox", { name: /Passer a un humain/ })).toBeNull();
        expect(screen.queryByRole("checkbox", { name: /Raccrocher/ })).toBeNull();
        expect(screen.queryByText("Serveur MCP")).toBeNull();
        m.save.mockClear();
        fireEvent.click(outil);
        await waitFor(() => expect(m.save).toHaveBeenCalled());
        expect(dernierEnvoi()[0].travail_outils).toEqual(["outil-creneau"]);
    });

    it("refuses a duration out of bounds and saves a valid one", async () => {
        await ouvrirBriques({ ...REFERENCE, travail_actif: true });
        const bouton = () => screen.getByRole("button", { name: "Save the duration" }) as HTMLButtonElement;
        expect(bouton().disabled).toBe(true);
        for (const mauvaise of ["3", "301", "12.5"]) {
            saisirTravail("travail_delai_max_s", mauvaise);
            expect(bouton().disabled, mauvaise).toBe(true);
        }
        m.save.mockClear();
        saisirTravail("travail_delai_max_s", "120");
        expect(bouton().disabled).toBe(false);
        fireEvent.click(bouton());
        await waitFor(() => expect(m.save).toHaveBeenCalled());
        expect(dernierEnvoi()[0].travail_delai_max_s).toBe(120);
    });

    it("sends the model and the instructions from one dialog; the saved key goes back as its mask", async () => {
        await ouvrirBriques({
            ...REFERENCE,
            travail_actif: true,
            travail_llm: { provider: "mistral", model: "mistral-small-2603", api_key: MASQUE_LOT4 },
            travail_consigne: "Fais la demande.",
        });
        fireEvent.click(await screen.findByRole("button", { name: "Configure the background brain" }));
        await waitFor(() => expect(document.getElementById("travail_model")).not.toBeNull());
        expect((document.getElementById("travail_consigne") as HTMLTextAreaElement).value).toBe("Fais la demande.");
        saisirTravail("travail_model", "mistral-large-2512");
        m.save.mockClear();
        fireEvent.click(screen.getByRole("button", { name: "Save the background brain" }));
        await waitFor(() => expect(m.save).toHaveBeenCalled());
        const charge = dernierEnvoi()[0];
        expect(charge.travail_llm).toEqual({ provider: "mistral", model: "mistral-large-2512", api_key: MASQUE_LOT4 });
        expect(charge.travail_consigne).toBe("Fais la demande.");
    });

    it("« Back to the default » empties the instructions, which are then sent as null", async () => {
        await ouvrirBriques({ ...REFERENCE, travail_actif: true, travail_consigne: "Une consigne." });
        fireEvent.click(await screen.findByRole("button", { name: "Configure the background brain" }));
        await waitFor(() => expect(document.getElementById("travail_consigne")).not.toBeNull());
        const retour = screen.getByRole("button", { name: "Back to the default" }) as HTMLButtonElement;
        expect(retour.disabled).toBe(false);
        fireEvent.click(retour);
        expect((document.getElementById("travail_consigne") as HTMLTextAreaElement).value).toBe("");
        m.save.mockClear();
        fireEvent.click(screen.getByRole("button", { name: "Save the background brain" }));
        await waitFor(() => expect(m.save).toHaveBeenCalled());
        expect(dernierEnvoi()[0].travail_consigne ?? null).toBeNull();
    });

    it("writes the labels in English by default and in French once the page speaks French", async () => {
        const briques = await ouvrirBriques({ ...REFERENCE, travail_actif: true });
        const en = briques.querySelector('[data-groupe="briques-travail"]')?.textContent ?? "";
        expect(en).toContain("Background work");
        expect(en).toContain("Allowed tools");
        expect(en).toContain("Max duration (s)");
        cleanup();
        window.localStorage.setItem("mark.langue", "fr");
        const brFr = await ouvrirBriques({ ...REFERENCE, travail_actif: true }, (page) => <FournisseurLangue>{page}</FournisseurLangue>);
        const fr = brFr.querySelector('[data-groupe="briques-travail"]')?.textContent ?? "";
        expect(fr).toContain("Travail en arrière-plan");
        expect(fr).toContain("Outils autorisés");
        expect(fr).toContain("Durée maximale (s)");
    });

    it("is read only on a specialised agent that follows the main agent's brain, editable with its own brain", async () => {
        await ouvrirBriques(SPECIALISE_LOT4);
        expect(document.getElementById("travail_actif")?.closest("fieldset[disabled]")).not.toBeNull();
        cleanup();
        await ouvrirBriques({ ...SPECIALISE_LOT4, cerveau_propre: true });
        expect(document.getElementById("travail_actif")?.closest("fieldset[disabled]")).toBeNull();
        m.save.mockClear();
        fireEvent.click(document.getElementById("travail_actif") as HTMLElement);
        await waitFor(() => expect(m.save).toHaveBeenCalled());
        const charge = dernierEnvoi()[0];
        expect(charge.travail_actif).toBe(true);
        expect(charge.cerveau_propre).toBe(true);
        expect(charge.agent_principal_id).toBe(5);
    });
});

// Voix-soniox, relecture m3: the theme « Voice » says which sending mode the call uses, and where it comes from.
describe("[.mark] the sending mode of the text, as the call will use it", () => {
    const mode = () => document.querySelector("[data-mode-retenu]")?.getAttribute("data-mode-retenu");
    const SONIOX = (text_aggregation_mode: string) => ({ tts: { provider: "soniox", text_aggregation_mode } });

    it("says sentence by sentence by default, for any voice", async () => {
        await ouvrir(CONFIG_DE_REFERENCE as Record<string, unknown>, NOVA);
        ouvrirLeTheme("voix");
        expect(mode()).toBe("sentence:defaut");
    });

    it("says word by word from the agent's own setting", async () => {
        await ouvrir({ ...(CONFIG_DE_REFERENCE as Record<string, unknown>), tts_text_aggregation_mode: "token" }, SONIOX("sentence"));
        ouvrirLeTheme("voix");
        expect(mode()).toBe("token:agent");
        expect(document.querySelector('[data-note="balises-sans-effet"]')).not.toBeNull();
    });

    it("says word by word from the Soniox voice when the agent leaves the default", async () => {
        // The reference agent carries an ElevenLabs voice override of its own: this one has none.
        await ouvrir({ ...(CONFIG_DE_REFERENCE as Record<string, unknown>), model_overrides: {} }, SONIOX("token"));
        ouvrirLeTheme("voix");
        expect(mode()).toBe("token:voix");
        expect(document.querySelector("[data-mode-retenu]")?.textContent).toMatch(/Soniox voice/);
        // The tags card says it too: nothing is sent as tags word by word.
        expect(document.querySelector('[data-note="balises-sans-effet"]')).not.toBeNull();
    });

    it("reads the agent's own voice override before the organisation's", async () => {
        await ouvrir(
            { ...(CONFIG_DE_REFERENCE as Record<string, unknown>), model_overrides: { tts: { provider: "elevenlabs" } } },
            SONIOX("token"),
        );
        ouvrirLeTheme("voix");
        expect(mode()).toBe("sentence:defaut");
    });
});

// [.mark] passages-fiables, lots F and G: « Improving the agent » in Call data, two boxes, both off by default.
describe("[.mark] the agent's improvement boxes (passages-fiables, lots F and G)", () => {
    it("draws the box and the mail box under « Improving the agent », off by default, with the English label", async () => {
        await ouvrir(CONFIG_DE_REFERENCE as Record<string, unknown>, NOVA);
        const theme = ouvrirLeTheme("donnees");
        await waitFor(() => expect(theme.querySelector('[data-reglage="signaler_un_probleme"]')).not.toBeNull());
        expect(screen.getByText("Improving the agent", { selector: "h3, h4, legend, p, span, div" })).toBeTruthy();
        expect(screen.getByText("The agent can flag an issue")).toBeTruthy();
        expect(screen.getByText("Alerts by mail")).toBeTruthy();
        expect((document.getElementById("signaler_un_probleme") as HTMLElement).getAttribute("aria-checked")).toBe("false");
        expect((document.getElementById("alertes_par_mail") as HTMLElement).getAttribute("aria-checked")).toBe("false");
    });

    it("shows the French labels", async () => {
        await ouvrir(CONFIG_DE_REFERENCE as Record<string, unknown>, NOVA, (page) => <FournisseurLangue>{page}</FournisseurLangue>);
        const theme = ouvrirLeTheme("donnees");
        await waitFor(() => expect(theme.querySelector('[data-reglage="signaler_un_probleme"]')).not.toBeNull());
        expect(screen.getByText("L'agent peut signaler un problème")).toBeTruthy();
        expect(screen.getByText("Alertes par mail")).toBeTruthy();
        expect(screen.getAllByText("Amélioration de l'agent").length).toBeGreaterThan(0);
    });

    it("saves the two keys, and only when changed (E6)", async () => {
        await ouvrir(CONFIG_DE_REFERENCE as Record<string, unknown>, NOVA);
        ouvrirLeTheme("donnees");
        const bouton = await screen.findByRole("button", { name: "Save Call data" });
        expect((bouton as HTMLButtonElement).disabled).toBe(true);
        fireEvent.click(document.getElementById("signaler_un_probleme") as HTMLElement);
        fireEvent.click(document.getElementById("alertes_par_mail") as HTMLElement);
        m.save.mockClear();
        fireEvent.click(await screen.findByRole("button", { name: "Save Call data" }));
        await waitFor(() => expect(m.save).toHaveBeenCalled());
        const appels = m.save.mock.calls as unknown as Array<[Record<string, unknown>]>;
        const charge = appels[appels.length - 1][0];
        expect(charge.signaler_un_probleme).toBe(true);
        expect(charge.alertes_par_mail).toBe(true);
    });
});
