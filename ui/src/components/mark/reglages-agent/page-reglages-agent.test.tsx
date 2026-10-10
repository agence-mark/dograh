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
import { CONSIGNE_GENERIQUE_GREFFIER } from "./consigne-greffier";
import { INVENTAIRE_AGENT } from "./inventaire-agent";
import { CONFIG_DE_REFERENCE } from "./references/config-de-reference";

const m = vi.hoisted(() => ({
    config: null as unknown,
    userConfig: null as unknown,
    // What the page saves: read by the clerk's tests below.
    save: vi.fn(() => Promise.resolve(undefined)),
    // Plan porte-parlee: the graph the page is opened with.
    definition: { nodes: [], edges: [] } as unknown,
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
            if ("horsEcran" in entree || "via" in entree || SEULEMENT_DANS_UN_MODE.includes(cle) || SEULEMENT_AVEC_CONTROLE.includes(cle)) continue;
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
    ];
    // Chantier l-agent-collegue, L7: the names of « Field recognition » are read only when « Check
    // the data » is on, and drawn only then (E8, the same rule as the code).
    const SEULEMENT_AVEC_CONTROLE = ["variables_telephone", "variables_code_postal", "variables_courriel", "variables_date"];
    it("draws the fields recognised by their name only with « Check the data » on", async () => {
        await ouvrir(CONFIG_DE_REFERENCE as Record<string, unknown>, NOVA);
        let theme = ouvrirLeTheme("ecoute");
        await waitFor(() => expect(theme.querySelector('[data-reglage="controle_donnees"]')).not.toBeNull());
        for (const cle of SEULEMENT_AVEC_CONTROLE) expect(theme.querySelector(`[data-reglage="${cle}"]`), cle).toBeNull();
        cleanup();
        await ouvrir({ ...(CONFIG_DE_REFERENCE as Record<string, unknown>), controle_donnees: true }, NOVA);
        theme = ouvrirLeTheme("ecoute");
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

    it("is shown only in Postscript, like in the code", async () => {
        await ouvrir(FICHE, NOVA);
        ouvrirLeTheme("donnees");
        await waitFor(() => expect(document.getElementById("fiche_mode_de_note")).not.toBeNull());
        expect(caseAPorte()).toBeNull();
        fireEvent.change(document.getElementById("fiche_mode_de_note") as HTMLElement, { target: { value: "post_scriptum" } });
        await waitFor(() => expect(caseAPorte()).not.toBeNull());
        fireEvent.change(document.getElementById("fiche_mode_de_note") as HTMLElement, { target: { value: "greffier" } });
        await waitFor(() => expect(caseAPorte()).toBeNull());
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
