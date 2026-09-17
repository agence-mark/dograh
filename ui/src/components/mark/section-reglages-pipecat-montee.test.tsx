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

import { ID_SECTION_ADRESSE_ETABLISSEMENT } from "./SectionAdresseEtablissement";
import { ID_SECTION_HORAIRES_OUVERTURE } from "./SectionHorairesOuverture";
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
        expect(
            screen.getByRole("switch", { name: /write dictated numbers as digits/i }),
        ).toBeTruthy();
    });

    it("[trade vocabulary] shows the three switches on the page", async () => {
        // Same trap as the settings above: a switch that renders in its own
        // test and is mounted nowhere is a setting nobody can touch.
        await rendreLaPage();
        expect(document.getElementById("lexique_metier")).not.toBeNull();
        expect(document.getElementById("sons_communes")).not.toBeNull();
        expect(document.getElementById("sons_lexique")).not.toBeNull();
        expect(
            screen.getByRole("switch", { name: /use the organization's trade vocabulary/i }),
        ).toBeTruthy();
    });

    it("carries its own Save button on the page (existence only -- it is disabled until something changes)", async () => {
        // Honest title: this asserts the button EXISTS, not that a save round
        // trip works. It is disabled at this instant, nothing having changed.
        // What saving actually does is `section-reglages-pipecat.test.tsx`.
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

    it("sits at the file path Next turns into the route, and the canvas SOURCE pushes to it", async () => {
        // Honest title: the second half is a text assertion on their file --
        // the same class of check thrown out one floor below, and acceptable
        // only here. Two reasons: Next routes by file path, so the URL works
        // whatever that button does, and the button is upstream code we do not
        // own. What this really guarantees is the route; the gear is a
        // convenience whose loss would not make the settings unreachable.
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

    it("[opening hours] the card is really mounted, with its field, its Save button and its sidebar entry", async () => {
        // Same trap, same guard, for the card added on 2026-09-15: a card that
        // renders in its own test and is mounted nowhere is hours nobody types.
        const { container } = await rendreLaPage();
        expect(container.querySelector(`#${ID_SECTION_HORAIRES_OUVERTURE}`)).not.toBeNull();
        expect(document.getElementById("horaires_ouverture")).not.toBeNull();
        expect(screen.getByRole("button", { name: /save opening hours/i })).toBeTruthy();
        const entree = container.querySelector(`a[href="#${ID_SECTION_HORAIRES_OUVERTURE}"]`);
        expect(entree).not.toBeNull();
        expect(entree?.textContent).toContain("Opening Hours");
    });

    it("[verification-communes] the business address card is mounted, with its fields, its Save button and its sidebar entry", async () => {
        const { container } = await rendreLaPage();
        expect(container.querySelector(`#${ID_SECTION_ADRESSE_ETABLISSEMENT}`)).not.toBeNull();
        expect(screen.getByText("Business address for this agent")).toBeTruthy();
        expect(document.getElementById("agent-business-address-code-postal")).not.toBeNull();
        expect(document.getElementById("agent-business-address-commune")).not.toBeNull();
        expect(screen.getByRole("button", { name: /save business address/i })).toBeTruthy();
        const entree = container.querySelector(`a[href="#${ID_SECTION_ADRESSE_ETABLISSEMENT}"]`);
        expect(entree).not.toBeNull();
        expect(entree?.textContent).toContain("Business Address");
        // Right after the opening hours (plan, lot 5).
        const horaires = container.querySelector(`#${ID_SECTION_HORAIRES_OUVERTURE}`);
        const adresse = container.querySelector(`#${ID_SECTION_ADRESSE_ETABLISSEMENT}`);
        expect(horaires?.nextElementSibling).toBe(adresse);
    });

    it("[verification-communes] the town check switch is on the page, ON by default", async () => {
        await rendreLaPage();
        const interrupteur = screen.getByRole("switch", { name: /recognise the caller's town/i });
        expect(interrupteur.getAttribute("aria-checked")).toBe("true");
    });

    it("[variables-commune] the town variable names are on the page, under the switch, with the default and the notice", async () => {
        // Rendered on the PAGE, not the section alone: the 29 settings of
        // 2026-09-14 rendered perfectly in a file no screen mounted.
        const { container } = await rendreLaPage();
        const interrupteur = screen.getByRole("switch", { name: /recognise the caller's town/i });
        const champ = screen.getByLabelText("Variables that trigger the town check") as HTMLInputElement;
        expect(champ.value).toBe("commune, commune_*, adresse*");
        // Under the switch, inside the same card.
        const carte = container.querySelector(`#${ID_SECTION_REGLAGES_PIPECAT}`);
        expect(carte?.contains(champ)).toBe(true);
        expect(
            interrupteur.compareDocumentPosition(champ) & Node.DOCUMENT_POSITION_FOLLOWING,
        ).toBeTruthy();
        // The notice: where the name is, commas, the final *, an example, empty = default.
        const texte = carte?.textContent ?? "";
        expect(texte).toMatch(/Variables to Extract and its Variable Name/);
        expect(texte).toMatch(/separate them with commas/);
        expect(texte).toMatch(/A \* at the end means "every name that starts with"/);
        expect(texte).toMatch(/Example: ville, lieu_chantier, adresse\*/);
        expect(texte).toMatch(/Leave empty to go back to the default: commune, commune_\*, adresse\*/);
    });

    it("[coupure] the section of the moments the agent can't be interrupted carries its new title on the page", async () => {
        await rendreLaPage();
        expect(
            screen.getByRole("heading", { name: "Moments when the agent can't be interrupted" }),
        ).toBeTruthy();
        // The old title read as General > Interruption, which is another setting.
        expect(screen.queryByRole("heading", { name: "Interruptions" })).toBeNull();
    });

    it("[nombres-dictes] the number switch tells what it now does, on the page", async () => {
        // The step moved after the aggregator (plan nombres-dictes, N1): the
        // recorded transcript keeps the words, and postal codes are read both
        // ways. The old sentence about "minimum words" no longer holds.
        await rendreLaPage();
        const interrupteur = screen.getByRole("switch", { name: /write dictated numbers as digits/i });
        expect(interrupteur.getAttribute("aria-checked")).toBe("false");
        expect(screen.getByText(/reads postal codes said both ways/i)).toBeTruthy();
        expect(screen.getByText(/the recorded transcript keeps the caller's words/i)).toBeTruthy();
        expect(screen.queryByText(/minimum words/i)).toBeNull();
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
