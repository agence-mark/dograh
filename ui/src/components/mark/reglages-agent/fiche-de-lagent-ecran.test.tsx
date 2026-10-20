/**
 * [.mark] The fiche of an agent on screen (chantier agents-specialises, lot 11 = lot 4 of the fiche plan;
 * convention `22-convention-ecran.md` § 5, items 5, 6 and 8), rendered in the theme « Business » of the page.
 *
 *   - the menu of the fiche: « None » by default, its choice saved as `etablissement_id`, and nothing else;
 *   - the numbers of the agent, read under the menu (C4), and the origin « fiche » in « Establishments served »;
 *   - the agent's own hours and address are drawn ONLY for an agent without a fiche (E8: the code's rule), and an
 *     agent without a fiche sees the theme it saw before (zero loss);
 *   - a specialised agent (`agent_principal_id`) has no menu: « Establishment: the call's »;
 *   - a fiche that no longer exists is said, never silent.
 */
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { resolveWorkflowConfigurations } from "@/types/workflow-configurations";

import { CONFIG_DE_REFERENCE } from "./references/config-de-reference";

const FICHES = [
    { id: "creil", nom: "Magasin de Creil", numeros: [] },
    { id: "senlis", nom: "Magasin de Senlis", numeros: [] },
];

const m = vi.hoisted(() => ({
    config: null as unknown,
    save: vi.fn(() => Promise.resolve(undefined)),
    fiches: vi.fn(),
    servis: vi.fn(),
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
    useOrgConfig: () => ({ externalPbxIntegrationsEnabled: true, userConfig: null, organizationPreferences: null }),
}));
vi.mock("@/hooks/useAudioPlayback", () => ({ useAudioPlayback: () => ({ playingId: null, toggle: vi.fn() }) }));
vi.mock("@/lib/modelConfigurationPricing", () => ({ fetchModelConfigurationPricing: () => Promise.resolve(null) }));
vi.mock("@/components/ui/select", () => import("./references/select-natif"));
vi.mock("@/client/sdk.gen", async (importOriginal) => (await import("../sdk-factice")).sdkFactice(await importOriginal(), {
    getWorkflowApiV1WorkflowFetchWorkflowIdGet: () =>
        Promise.resolve({
            data: { id: 1, name: "Agent", workflow_uuid: "u-u-i-d", workflow_definition: { nodes: [], edges: [] }, template_context_variables: {}, workflow_configurations: {} },
            error: null,
        }),
    getModelConfigurationV2ApiV1OrganizationsModelConfigurationsV2Get: () =>
        Promise.resolve({ data: { source: "organization_v2", configuration: {}, effective_configuration: {} }, error: null }),
    getModelConfigurationV2DefaultsApiV1OrganizationsModelConfigurationsV2DefaultsGet: () => Promise.resolve({ data: {}, error: null }),
    getDefaultConfigurationsApiV1UserConfigurationsDefaultsGet: () => Promise.resolve({ data: { llm: {} }, error: null }),
    listRecordingsApiV1WorkflowRecordingsGet: () => Promise.resolve({ data: { recordings: [] }, error: null }),
    getCommunesDuCodePostalApiV1OrganizationsCommunesGet: () => Promise.resolve({ data: [{ code_insee: "60057", nom: "Beauvais" }], error: null }),
    getEtablissementsApiV1OrganizationsEtablissementsGet: m.fiches,
    postEtablissementsDeLagentApiV1OrganizationsEtablissementsAgentPost: m.servis,
}));
vi.mock("@/components/AIModelConfigurationV2Editor", () => ({ AIModelConfigurationV2Editor: () => <div /> }));
vi.mock("@/components/ServiceConfigurationForm", () => ({ ServiceConfigurationForm: () => <div /> }));
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

const vueServie = (corps: Record<string, unknown>) => ({ data: { etablissements: [], numeros_sans_etablissement: [], numeros_de_lagent: [], ...corps } });

afterEach(() => {
    cleanup();
    window.localStorage.clear();
    m.save.mockClear();
    m.fiches.mockReset();
    m.servis.mockReset();
});

const ouvrir = async (config: Record<string, unknown>, servi: Record<string, unknown> = {}) => {
    window.localStorage.setItem("mark.langue", "en");
    m.fiches.mockResolvedValue({ data: { format: "etablissements-mark", version: 1, etablissements: FICHES } });
    m.servis.mockResolvedValue(vueServie({ numeros_de_lagent: ["+33344000001", "+33344000009"], ...servi }));
    m.config = resolveWorkflowConfigurations({ ...CONFIG_DE_REFERENCE, ...config } as never);
    render(<WorkflowSettingsPage />);
    await waitFor(() => expect(document.querySelectorAll("[data-theme]").length).toBe(9));
    const entete = document.querySelector('[data-theme="etablissement"] > button[aria-expanded]') as HTMLButtonElement;
    if (entete.getAttribute("aria-expanded") === "false") fireEvent.click(entete);
    return document.getElementById("etablissement") as HTMLElement;
};

const menu = () => document.getElementById("etablissement_id") as HTMLSelectElement | null;
const enregistrer = () => screen.getByRole("button", { name: "Save Business" });

describe("[.mark] the fiche of the agent, theme « Business »", () => {
    it("draws the menu with « None » by default, its bounds and default, and finds it in the theme", async () => {
        const theme = await ouvrir({});
        await waitFor(() => expect(menu()).not.toBeNull());
        const reglage = theme.querySelector('[data-reglage="etablissement_id"]');
        expect(reglage).not.toBeNull();
        expect(reglage?.textContent).toContain("Default: none · one fiche at most");
        expect(menu()!.value).toBe("");
        const options = [...menu()!.options].map((o) => [o.value, o.textContent]);
        expect(options).toEqual([
            ["", "None: specialised agent or no place"],
            ["creil", "Magasin de Creil"],
            ["senlis", "Magasin de Senlis"],
        ]);
        expect((enregistrer() as HTMLButtonElement).disabled).toBe(true);
    });

    it("saves the chosen fiche as `etablissement_id`, and nothing else", async () => {
        await ouvrir({});
        await waitFor(() => expect(menu()).not.toBeNull());
        fireEvent.change(menu()!, { target: { value: "creil" } });
        fireEvent.click(enregistrer());
        await waitFor(() => expect(m.save).toHaveBeenCalledTimes(1));
        const [envoye] = m.save.mock.calls[0] as unknown as [Record<string, unknown>, string];
        const base = resolveWorkflowConfigurations(CONFIG_DE_REFERENCE as never) as unknown as Record<string, unknown>;
        const differences = Object.keys(envoye).filter((cle) => JSON.stringify(envoye[cle]) !== JSON.stringify(base[cle]));
        expect(differences).toEqual(["etablissement_id"]);
        expect(envoye.etablissement_id).toBe("creil");
    });

    it("saves « None » as null when the fiche is taken away", async () => {
        await ouvrir({ etablissement_id: "creil" });
        await waitFor(() => expect(menu()).not.toBeNull());
        expect(menu()!.value).toBe("creil");
        fireEvent.change(menu()!, { target: { value: "" } });
        fireEvent.click(enregistrer());
        await waitFor(() => expect(m.save).toHaveBeenCalledTimes(1));
        expect((m.save.mock.calls[0] as unknown as [Record<string, unknown>])[0].etablissement_id).toBeNull();
    });

    it("reads the numbers of the agent under the menu, and asks the server about the chosen fiche", async () => {
        await ouvrir({});
        await waitFor(() => expect(screen.getByTestId("numeros-de-lagent").textContent).toContain("+33344000001, +33344000009"));
        // An agent without a fiche asks exactly as before: no `etablissement_id` in the request.
        await waitFor(() => expect(m.servis).toHaveBeenCalled());
        expect(m.servis.mock.calls[0][0].body).not.toHaveProperty("etablissement_id");
        fireEvent.change(menu()!, { target: { value: "senlis" } });
        await waitFor(() => expect(m.servis.mock.calls.at(-1)?.[0].body.etablissement_id).toBe("senlis"));
    });

    it("says where each value comes from: the fiche, alone, with no numbers on the fiche", async () => {
        const theme = await ouvrir(
            { etablissement_id: "creil" },
            {
                fiche_de_lagent: "creil",
                numeros_de_lagent: ["+33344000001"],
                etablissements: [
                    {
                        id: "creil",
                        nom: "Magasin de Creil",
                        numeros: ["+33999999999"],
                        horaires_ouverture: { valeur: "lundi : fermé", origine: "fiche" },
                        adresse: { valeur: null, origine: "aucune" },
                        annonce_fermeture: { valeur: "Fermé.", origine: "fiche" },
                        annonce_pause: { valeur: null, origine: "aucune" },
                        numero_transfert: { valeur: "+33344000000", origine: "fiche" },
                    },
                ],
            },
        );
        await waitFor(() => expect(theme.querySelector('[data-testid="etablissements-servis"]')).not.toBeNull());
        const servis = theme.querySelector('[data-testid="etablissements-servis"]')!.textContent ?? "";
        expect(servis).toContain("(the fiche of this agent)");
        expect(servis).not.toContain("+33999999999");
        expect(m.servis.mock.calls[0][0].body.etablissement_id).toBe("creil");
    });

    it("draws the agent's own hours and address ONLY for an agent without a fiche", async () => {
        const theme = await ouvrir({});
        // Without a fiche: the theme is the one of before.
        expect(theme.querySelector('[data-reglage="horaires_ouverture"]')).not.toBeNull();
        expect(theme.querySelector('[data-reglage="adresse_etablissement"]')).not.toBeNull();
        expect(theme.querySelector('[data-testid="lieu-de-la-fiche"]')).toBeNull();
        cleanup();
        const avecFiche = await ouvrir({ etablissement_id: "creil" });
        expect(avecFiche.querySelector('[data-reglage="horaires_ouverture"]')).toBeNull();
        expect(avecFiche.querySelector('[data-reglage="adresse_etablissement"]')).toBeNull();
        expect(avecFiche.querySelector('[data-testid="lieu-de-la-fiche"]')).not.toBeNull();
        // The voicemail and the outage fallback are not the place's: they stay.
        expect(avecFiche.querySelector('[data-reglage="voicemail_detection"]')).not.toBeNull();
    });

    it("hides them as soon as a fiche is chosen, and does not send what is no longer read", async () => {
        const theme = await ouvrir({});
        await waitFor(() => expect(menu()).not.toBeNull());
        fireEvent.change(document.getElementById("horaires_ouverture")!, { target: { value: "lundi : fermé" } });
        fireEvent.change(menu()!, { target: { value: "creil" } });
        expect(theme.querySelector('[data-reglage="horaires_ouverture"]')).toBeNull();
        fireEvent.click(enregistrer());
        await waitFor(() => expect(m.save).toHaveBeenCalledTimes(1));
        const [envoye] = m.save.mock.calls[0] as unknown as [Record<string, unknown>];
        expect(envoye.etablissement_id).toBe("creil");
        expect(envoye.horaires_ouverture).toBe((resolveWorkflowConfigurations(CONFIG_DE_REFERENCE as never) as unknown as Record<string, unknown>).horaires_ouverture);
    });

    it("gives a specialised agent no menu: the establishment of the call", async () => {
        const theme = await ouvrir({ agent_principal_id: 5 });
        await waitFor(() => expect(screen.getByTestId("etablissement-de-lappel")).not.toBeNull());
        expect(screen.getByTestId("etablissement-de-lappel").textContent).toBe("Establishment: the call's");
        expect(menu()).toBeNull();
        expect(theme.querySelector('[data-reglage="etablissement_id"]')).not.toBeNull();
        // It has no fiche: its own hours and address stay (an agent without a fiche), as before.
        expect(theme.querySelector('[data-reglage="horaires_ouverture"]')).not.toBeNull();
    });

    it("keeps the menu on a specialised agent that carries a fiche of its own, to be able to remove it", async () => {
        await ouvrir({ agent_principal_id: 5, etablissement_id: "senlis" });
        await waitFor(() => expect(menu()).not.toBeNull());
        expect(menu()!.value).toBe("senlis");
        expect(screen.queryByTestId("etablissement-de-lappel")).toBeNull();
    });

    it("says it when the fiche chosen no longer exists", async () => {
        const theme = await ouvrir({ etablissement_id: "disparue" }, { fiche_de_lagent: "disparue", fiche_introuvable: true });
        await waitFor(() => expect(theme.querySelector('[data-testid="fiche-introuvable"]')).not.toBeNull());
        expect([...menu()!.options].some((o) => o.value === "disparue" && /not found/.test(o.textContent ?? ""))).toBe(true);
    });
});
