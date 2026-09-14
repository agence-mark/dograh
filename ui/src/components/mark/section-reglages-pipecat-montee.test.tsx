/**
 * [.mark] Is the Speech Tuning section REACHABLE?
 *
 * The question this file answers, and it answers only this one:
 *
 *     Can Evan and Pierre actually get to the 29 Pipecat settings by clicking
 *     in the application — not "does the component render when a test renders
 *     it"?
 *
 * Why it exists
 * -------------
 * A real, measured failure on 2026-09-14. The 29 settings were mounted in
 * `app/workflow/[workflowId]/components/ConfigurationsDialog.tsx`, a file
 * mounted in NO screen, orphaned in Dograh's own code since `b3bb7328`. The
 * server was right, the settings were in the published spec, every test was
 * green, and nobody could touch a single setting.
 *
 * The tests of the day rendered that dialog and asserted the four sections were
 * mounted INSIDE it. Not one asserted the dialog itself was mounted somewhere.
 * Rendering a component proves the component works. It does not prove anyone
 * can reach it.
 *
 * How this file proves the chain — and why it RENDERS the page
 * -----------------------------------------------------------
 * The first version of this file read the source of `settings/page.tsx` and
 * asserted it contained the right strings. An independent review knocked that
 * down, rightly: a mount commented out, put behind `{false && …}`, or moved
 * into a sub-component nobody renders would leave every assertion green. That
 * is the original defect, one floor up — the same trap the file was written to
 * close.
 *
 * So the page component itself is rendered here. What is mocked is deliberate
 * and narrow: the things a JSDOM test cannot have (auth, routing, the API
 * client, the workflow state hook). Nothing about the page's own structure is
 * mocked — the section list, the sidebar and the card ids all come from their
 * real code. A mount that is commented out, disabled, or orphaned makes this
 * file fail.
 *
 * The last link — that `/workflow/{id}/settings` is a real route, reached by
 * the gear on the agent canvas (`RenderWorkflow.tsx`, `router.push`) — is
 * carried by Next's file-based routing and asserted at the end.
 */

import { readFileSync } from "node:fs";
import { join } from "node:path";

import { render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import { resolveWorkflowConfigurations } from "@/types/workflow-configurations";

import { ID_SECTION_REGLAGES_PIPECAT } from "./SectionReglagesPipecat";

vi.mock("sonner", () => ({ toast: { success: vi.fn(), error: vi.fn() } }));

vi.mock("next/navigation", () => ({
    useParams: () => ({ workflowId: "1" }),
    useRouter: () => ({ push: vi.fn(), replace: vi.fn(), back: vi.fn() }),
}));

vi.mock("@/lib/auth", () => ({
    useAuth: () => ({
        user: { id: "u-1", email: "evan@example.test" },
        loading: false,
        redirectToLogin: vi.fn(),
    }),
}));

vi.mock("@/context/OrgConfigContext", () => ({
    useOrgConfig: () => ({ externalPbxIntegrationsEnabled: false, userConfig: null }),
}));

vi.mock("@/hooks/useAudioPlayback", () => ({
    useAudioPlayback: () => ({ playingId: null, toggle: vi.fn() }),
}));

vi.mock("@/lib/modelConfigurationPricing", () => ({
    fetchModelConfigurationPricing: () => Promise.resolve({ data: null, error: null }),
}));

// The API client: the page asks for the workflow and the model configuration.
// Answering with the shape it expects is enough; the DATA is not what this file
// is about.
const agent = {
    id: 1,
    name: "Agent de test",
    workflow_definition: { nodes: [], edges: [] },
    template_context_variables: {},
    workflow_configurations: {},
};

vi.mock("@/client/sdk.gen", () => ({
    getWorkflowApiV1WorkflowFetchWorkflowIdGet: () =>
        Promise.resolve({ data: agent, error: null }),
    getModelConfigurationV2ApiV1OrganizationsModelConfigurationsV2Get: () =>
        Promise.resolve({ data: null, error: null }),
    getModelConfigurationV2DefaultsApiV1OrganizationsModelConfigurationsV2DefaultsGet: () =>
        Promise.resolve({ data: null, error: null }),
    downloadWorkflowReportApiV1WorkflowWorkflowIdReportGet: () =>
        Promise.resolve({ data: null, error: null }),
    getAmbientNoiseUploadUrlApiV1WorkflowAmbientNoiseUploadUrlPost: () =>
        Promise.resolve({ data: null, error: null }),
}));

// The workflow-state hook talks to the store, the API and the defaults route.
// Its behaviour has its own tests; here it only has to hand the page a
// configuration so the sections render.
vi.mock("@/app/workflow/[workflowId]/hooks/useWorkflowState", () => ({
    useWorkflowState: () => ({
        workflowName: "Agent de test",
        workflowConfigurations: resolveWorkflowConfigurations(null),
        defaultCallDispositions: [],
        textChatInactivityTimeoutConstraints: null,
        widgetTextDefaults: {},
        templateContextVariables: {},
        dictionary: "",
        saveWorkflowConfigurations: vi.fn().mockResolvedValue(undefined),
        saveTemplateContextVariables: vi.fn().mockResolvedValue(undefined),
        saveDictionary: vi.fn().mockResolvedValue(undefined),
    }),
}));

vi.stubGlobal(
    "ResizeObserver",
    class {
        observe() {}
        unobserve() {}
        disconnect() {}
    },
);

vi.stubGlobal(
    "IntersectionObserver",
    class {
        observe() {}
        unobserve() {}
        disconnect() {}
    },
);

// Imported AFTER the mocks, so the page picks them up.
const { default: WorkflowSettingsPage } = await import(
    "@/app/workflow/[workflowId]/settings/page"
);

const rendreLaPage = async () => {
    const rendu = render(<WorkflowSettingsPage />);
    // The page shows a spinner until the workflow fetch resolves.
    await screen.findByText("Speech Tuning", {}, { timeout: 3000 }).catch(() => null);
    return rendu;
};

describe("[.mark] the Speech Tuning section is reachable on the settings page", () => {
    it("is really mounted on the page, not merely mentioned in its source", async () => {
        // The assertion the first version of this file was missing. A mount
        // commented out, put behind `{false && …}`, or moved into a
        // sub-component nobody renders fails here.
        const { container } = await rendreLaPage();
        expect(container.querySelector(`#${ID_SECTION_REGLAGES_PIPECAT}`)).not.toBeNull();
    });

    it("shows the settings themselves, not just an empty card", async () => {
        // Mounted but handed no configuration would render a card with nothing
        // in it -- reachable and useless.
        await rendreLaPage();
        expect(document.getElementById("user_speech_timeout")).not.toBeNull();
        expect(document.getElementById("vad_stop_secs")).not.toBeNull();
        expect(document.getElementById("mute_always")).not.toBeNull();
        expect(document.getElementById("user_idle_prompt")).not.toBeNull();
        expect(
            screen.getByRole("switch", { name: /strip markdown before speaking/i }),
        ).toBeTruthy();
    });

    it("can be saved from the page, so it is not read-only decoration", async () => {
        await rendreLaPage();
        expect(screen.getByRole("button", { name: /save speech tuning/i })).toBeTruthy();
    });

    it("has its own entry in the sidebar, pointing at the card that exists", async () => {
        // The sidebar is a list of `<a href="#id">`, and the intersection
        // observer watches the same ids: an entry whose id no element carries
        // is an entry that does nothing, silently.
        const { container } = await rendreLaPage();
        const entree = container.querySelector(
            `a[href="#${ID_SECTION_REGLAGES_PIPECAT}"]`,
        );
        expect(entree).not.toBeNull();
        expect(entree?.textContent).toContain("Speech Tuning");
        expect(container.querySelector(`#${ID_SECTION_REGLAGES_PIPECAT}`)).not.toBeNull();
    });

    it("sits on a real route, reached by the gear on the agent canvas", async () => {
        // The one link JSDOM cannot render: Next routes by file path, so the
        // file existing at this path IS the route, and the canvas pushes to it.
        const canevas = readFileSync(
            join(process.cwd(), "src/app/workflow/[workflowId]/RenderWorkflow.tsx"),
            "utf8",
        );
        expect(canevas).toContain("/settings`");

        // And the page file is where Next expects the route to live.
        expect(() =>
            readFileSync(
                join(process.cwd(), "src/app/workflow/[workflowId]/settings/page.tsx"),
                "utf8",
            ),
        ).not.toThrow();
    });

    it("is NOT left behind in the dead dialog, where it was unreachable", () => {
        // The guard that would have prevented this whole chantier: nothing of
        // ours goes back into a file no screen mounts.
        const dialogue = readFileSync(
            join(process.cwd(), "src/app/workflow/[workflowId]/components/ConfigurationsDialog.tsx"),
            "utf8",
        );

        expect(dialogue).not.toContain("@/components/mark/");
    });
});
