/**
 * [.mark] Payload references of the agent settings page.
 *
 * The question this file answers:
 *
 *     For every setting of the page, what exactly does saving send?
 *
 * Chantier reorganisation-ecran-reglages, step 1 (then step 4). Decision D1 of
 * Evan: « on range, on ne change pas la logique ». Moving 70 settings into 8
 * themes can drop a key, send a default instead of the stored value, or trim
 * where the old card did not -- all in silence. So BEFORE anything moved, every
 * case of `cas-agent.ts` was played on the page as it was (14 cards,
 * `ef03ef5e`) and what the save functions received was frozen in
 * `charges-utiles-agent.json`. This file plays the same cases on the page as it
 * is and demands the same record, case by case.
 *
 * Rewriting the reference is `ECRIRE_REFERENCES=1 npx vitest run <this file>`.
 * ⛔ Only ever on the page as it was: rewriting it on the new page would make
 * the new page its own witness.
 *
 * What is mocked, and why it cannot hide a difference: the API client, auth,
 * routing and the workflow-state hook (its save functions ARE what is
 * recorded); the Radix Select, by a native one (`select-natif.tsx`); and four
 * heavy Dograh components the page REUSES as they are (model editor, per-service
 * form, LLM selector, widget dialog), each replaced by a stub that calls the
 * very callback the page hands it. Both pages get the same mocks.
 */
import { existsSync, readFileSync, writeFileSync } from "node:fs";
import { join } from "node:path";

import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { resolveWorkflowConfigurations } from "@/types/workflow-configurations";

import { AUTOUR_DU_CAS, CAS_AGENT, type CasAgent, type Geste, type ThemeAgent, TITRE_ANGLAIS_DU_THEME } from "./cas-agent";
import {
    COMMUNES_DE_REFERENCE,
    CONFIG_DE_REFERENCE,
    NOM_AGENT_DE_REFERENCE,
    VARIABLES_DE_REFERENCE,
} from "./config-de-reference";
import { commeEnvoye, jouerGeste, relever } from "./jouer";

const FICHIER = join(process.cwd(), "src/components/mark/reglages-agent/references/charges-utiles-agent.json");
const ECRIRE = process.env.ECRIRE_REFERENCES === "1";

const m = vi.hoisted(() => ({
    saveWorkflowConfigurations: vi.fn(),
    saveTemplateContextVariables: vi.fn(),
    saveDictionary: vi.fn(),
    config: null as unknown,
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
    useOrgConfig: () => ({
        externalPbxIntegrationsEnabled: true,
        userConfig: null,
        organizationPreferences: {
            adresse_etablissement: { code_postal: "60000", code_insee: "60057", commune: "Beauvais", voie: null },
        },
    }),
}));
vi.mock("@/hooks/useAudioPlayback", () => ({ useAudioPlayback: () => ({ playingId: null, toggle: vi.fn() }) }));
vi.mock("@/lib/modelConfigurationPricing", () => ({ fetchModelConfigurationPricing: () => Promise.resolve(null) }));
vi.mock("@/components/ui/select", () => import("./select-natif"));

vi.mock("@/client/sdk.gen", () => ({
    getWorkflowApiV1WorkflowFetchWorkflowIdGet: () => Promise.resolve({
        data: {
            id: 1,
            name: "Accueil de référence",
            workflow_uuid: "7f3c9a1e-52b0-4c1e-9d0a-8e41c6a2d42b",
            workflow_definition: { nodes: [], edges: [] },
            template_context_variables: {},
            workflow_configurations: {},
        },
        error: null,
    }),
    getModelConfigurationV2ApiV1OrganizationsModelConfigurationsV2Get: () => Promise.resolve({
        data: { source: "organization_v2", configuration: {}, effective_configuration: {} },
        error: null,
    }),
    getModelConfigurationV2DefaultsApiV1OrganizationsModelConfigurationsV2DefaultsGet: () =>
        Promise.resolve({ data: {}, error: null }),
    downloadWorkflowReportApiV1WorkflowWorkflowIdReportGet: () => Promise.resolve({ data: null, error: null }),
    getAmbientNoiseUploadUrlApiV1WorkflowAmbientNoiseUploadUrlPost: () => Promise.resolve({ data: null, error: null }),
    listRecordingsApiV1WorkflowRecordingsGet: () => Promise.resolve({ data: { recordings: [] }, error: null }),
    getCommunesDuCodePostalApiV1OrganizationsCommunesGet: () =>
        Promise.resolve({ data: [{ code_insee: "60057", nom: "Beauvais" }], error: null }),
}));

// The four reused Dograh components: each stub calls the callback the page
// hands it, with a fixed value, so what is recorded is the PAGE's wiring.
vi.mock("@/components/AIModelConfigurationV2Editor", () => ({
    AIModelConfigurationV2Editor: ({ onSave, submitLabel }: { onSave: (c: unknown) => void; submitLabel: string }) => (
        <button type="button" onClick={() => onSave({ llm: { provider: "mistral", model: "mistral-large-2512" } })}>
            {submitLabel}
        </button>
    ),
}));
vi.mock("@/components/ServiceConfigurationForm", () => ({
    ServiceConfigurationForm: ({ onSave, submitLabel }: { onSave: (c: unknown) => void; submitLabel: string }) => (
        <button type="button" onClick={() => onSave({ model_overrides: { llm: { provider: "mistral", model: "mistral-large-2512" } } })}>
            {submitLabel}
        </button>
    ),
}));
vi.mock("@/components/LLMConfigSelector", () => ({ LLMConfigSelector: () => null }));
vi.mock("@/app/workflow/[workflowId]/components/EmbedDialog", () => ({
    EmbedDialog: ({
        open,
        workflowConfigurations,
        workflowName,
        onSaveWorkflowConfigurations,
    }: {
        open: boolean;
        workflowConfigurations: Record<string, unknown>;
        workflowName: string;
        onSaveWorkflowConfigurations: (c: unknown, n: string) => void;
    }) =>
        open ? (
            <button
                type="button"
                onClick={() => onSaveWorkflowConfigurations({ ...workflowConfigurations, embed: { stub: true } }, workflowName)}
            >
                Stub: save widget
            </button>
        ) : null,
}));

vi.mock("@/app/workflow/[workflowId]/hooks/useWorkflowState", () => ({
    useWorkflowState: () => ({
        workflowName: "Accueil de référence",
        workflowConfigurations: m.config,
        defaultCallDispositions: [],
        defaultAnswerClassifierPrompt: "Consignes intégrées.",
        textChatInactivityTimeoutConstraints: null,
        widgetTextDefaults: {},
        templateContextVariables: { nom_entreprise: "Nuances de Feu" },
        dictionary: "poêle à granulés, insert",
        saveWorkflowConfigurations: m.saveWorkflowConfigurations,
        saveTemplateContextVariables: m.saveTemplateContextVariables,
        saveDictionary: m.saveDictionary,
    }),
}));

vi.stubGlobal(
    "IntersectionObserver",
    class {
        observe() {}
        unobserve() {}
        disconnect() {}
    },
);
vi.stubGlobal(
    "ResizeObserver",
    class {
        observe() {}
        unobserve() {}
        disconnect() {}
    },
);

const { default: WorkflowSettingsPage } = await import("@/app/workflow/[workflowId]/settings/page");

// The configuration the hook hands the page. The page resolves it once more;
// resolving is idempotent, so this is exactly what the cards start from.
m.config = resolveWorkflowConfigurations(CONFIG_DE_REFERENCE as never);
const BASE = commeEnvoye(m.config) as Record<string, unknown>;

afterEach(() => {
    cleanup();
    m.saveWorkflowConfigurations.mockReset().mockResolvedValue(undefined);
    m.saveTemplateContextVariables.mockReset().mockResolvedValue(undefined);
    m.saveDictionary.mockReset().mockResolvedValue(undefined);
});
m.saveWorkflowConfigurations.mockResolvedValue(undefined);
m.saveTemplateContextVariables.mockResolvedValue(undefined);
m.saveDictionary.mockResolvedValue(undefined);

const ouvrirLaPage = async () => {
    render(<WorkflowSettingsPage />);
    await waitFor(() => expect(document.querySelectorAll("[data-theme]").length).toBe(8));
};

/** Opens a theme by its header (the one thing that folds, E1). */
const ouvrirLeTheme = (theme: ThemeAgent) => {
    const entete = document.querySelector(`[data-theme="${theme}"] > button[aria-expanded]`) as HTMLButtonElement;
    if (entete.getAttribute("aria-expanded") === "false") fireEvent.click(entete);
};

/** Waits for what a gesture reaches: the model configuration and the town list load late. */
const attendreLaCible = async (geste: Geste) => {
    await waitFor(() => {
        if (geste.type === "interrupteur" || geste.type === "choisir" || geste.type === "etiquette") {
            expect(document.getElementById(geste.id)).toBeTruthy();
        } else if (geste.type === "saisir" && geste.id) {
            expect(document.getElementById(geste.id)).toBeTruthy();
        } else if (geste.type === "cliquer") {
            expect(screen.getByRole("button", { name: geste.nom })).toBeTruthy();
        }
    });
};

/** Plays one case on the themes, and presses the save of its theme. */
const jouer = async (cas: CasAgent) => {
    await ouvrirLaPage();
    ouvrirLeTheme(cas.theme);
    const autour = AUTOUR_DU_CAS[cas.id] ?? { avant: [], apres: [] };
    for (const geste of [...autour.avant, ...cas.gestes, ...autour.apres]) {
        await attendreLaCible(geste);
        jouerGeste(geste);
    }
    if (!cas.enregistreSeul) {
        const nom = `Save ${TITRE_ANGLAIS_DU_THEME[cas.theme]}`;
        const bouton = (await screen.findByRole("button", { name: nom })) as HTMLButtonElement;
        expect(bouton.disabled, `${cas.id}: ${nom} must be enabled after the change`).toBe(false);
        fireEvent.click(bouton);
    }
    await waitFor(() =>
        expect(
            m.saveWorkflowConfigurations.mock.calls.length
            + m.saveTemplateContextVariables.mock.calls.length
            + m.saveDictionary.mock.calls.length,
        ).toBeGreaterThan(0),
    );
    return relever(m, BASE);
};

const references: {
    base: Record<string, unknown>;
    nom: string;
    variables: Record<string, string>;
    communes: unknown;
    boutonsInactifsSansModification: Record<string, boolean>;
    cas: Record<string, unknown>;
} = existsSync(FICHIER) && !ECRIRE
    ? JSON.parse(readFileSync(FICHIER, "utf8"))
    : {
        base: BASE,
        nom: NOM_AGENT_DE_REFERENCE,
        variables: VARIABLES_DE_REFERENCE,
        communes: COMMUNES_DE_REFERENCE,
        boutonsInactifsSansModification: {},
        cas: {},
    };

describe("payload references of the agent settings page", () => {
    it("starts from the same resolved configuration as the reference", () => {
        expect(BASE).toEqual(references.base);
    });

    it("leaves every save button disabled while nothing was touched", async () => {
        // Step 1 froze the eight card buttons of the old page, all disabled
        // untouched. The themes that carry a button must be the same.
        expect(Object.values(references.boutonsInactifsSansModification).every(Boolean)).toBe(true);
        await ouvrirLaPage();
        const themesAvecBouton = (Object.keys(TITRE_ANGLAIS_DU_THEME) as ThemeAgent[]).filter((t) => t !== "briques");
        for (const theme of themesAvecBouton) {
            ouvrirLeTheme(theme);
            const bouton = (await screen.findByRole("button", { name: `Save ${TITRE_ANGLAIS_DU_THEME[theme]}` })) as HTMLButtonElement;
            expect(bouton.disabled, `${theme} must be disabled untouched`).toBe(true);
        }
    });

    it.each(CAS_AGENT.map((cas) => [cas.id, cas] as const))("case %s sends what the reference froze", async (_id, cas) => {
        const appels = await jouer(cas);
        if (ECRIRE) references.cas[cas.id] = { carte: cas.carte, theme: cas.theme, appels };
        else expect({ carte: cas.carte, theme: cas.theme, appels }).toEqual(references.cas[cas.id]);
    }, 20000);

    it("wrote or matched every case, no more, no less", () => {
        if (ECRIRE) writeFileSync(FICHIER, `${JSON.stringify(references, null, 2)}\n`, "utf8");
        expect(Object.keys(references.cas).sort()).toEqual(CAS_AGENT.map((c) => c.id).sort());
    });
});
