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

import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import { resolveWorkflowConfigurations } from "@/types/workflow-configurations";


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
    await waitFor(() => expect(document.querySelectorAll("[data-theme]").length).toBe(8), { timeout: 3000 });
    return rendu;
};

/**
 * [.mark] Since the chantier reorganisation-ecran-reglages (26/09/2026) the
 * page is 8 themes that fold (convention E1): a setting is reached by opening
 * its theme. Every question below is the one this file asked of the cards,
 * asked of the themes -- the setting still has to be REACHABLE by clicking.
 */
const ouvrirLeTheme = (id: string) => {
    const entete = document.querySelector(`[data-theme="${id}"] > button[aria-expanded]`) as HTMLButtonElement;
    if (entete.getAttribute("aria-expanded") === "false") fireEvent.click(entete);
    return document.getElementById(id) as HTMLElement;
};

describe("[.mark] our settings are reachable on the settings page", () => {
    it("is really mounted on the page, not merely mentioned in its source", async () => {
        // The assertion the first version of this file was missing. A mount
        // commented out, put behind `{false && …}`, or moved into a
        // sub-component nobody renders fails here.
        const { container } = await rendreLaPage();
        for (const id of ["agent", "briques", "ecoute", "tour", "voix", "rythme", "donnees", "etablissement"]) {
            expect(container.querySelector(`#${id}[data-theme]`), id).not.toBeNull();
        }
    });

    it("shows the settings themselves, not just an empty theme", async () => {
        // Mounted but handed no configuration would render a theme with nothing
        // in it -- reachable and useless.
        await rendreLaPage();
        ouvrirLeTheme("tour");
        ouvrirLeTheme("rythme");
        ouvrirLeTheme("voix");
        ouvrirLeTheme("ecoute");
        expect(document.getElementById("user_speech_timeout")).not.toBeNull();
        expect(document.getElementById("vad_stop_secs")).not.toBeNull();
        expect(document.getElementById("mute_always")).not.toBeNull();
        expect(document.getElementById("user_idle_prompt")).not.toBeNull();
        expect(screen.getByRole("switch", { name: /strip markdown before speaking/i })).toBeTruthy();
        expect(screen.getByRole("switch", { name: /write dictated numbers as digits/i })).toBeTruthy();
    });

    it("[name and title] shows both switches, and its notice, on the page", async () => {
        // ⛔ Même piège, et il coûterait plus cher ici qu'ailleurs : deux
        // interrupteurs visibles dans leur propre test mais montés nulle part
        // laisseraient croire qu'on a coupé la prononciation du nom alors que
        // l'agent continue de le dire. Une promesse fausse au client.
        await rendreLaPage();
        ouvrirLeTheme("voix");
        expect(document.getElementById("interdire_nom_appelant")).not.toBeNull();
        expect(document.getElementById("interdire_civilite_appelant")).not.toBeNull();
        expect(screen.getByRole("switch", { name: /never say the caller's name/i })).toBeTruthy();
        // Le pense-bête de rédaction : sans lui, la confirmation du nom perd son
        // objet dès que l'interrupteur est allumé.
        expect(document.body.textContent).toContain("SPELLING it back");
    });

    it("[trade vocabulary] shows the three switches on the page", async () => {
        await rendreLaPage();
        ouvrirLeTheme("ecoute");
        expect(document.getElementById("lexique_metier")).not.toBeNull();
        expect(document.getElementById("sons_communes")).not.toBeNull();
        expect(document.getElementById("sons_lexique")).not.toBeNull();
        expect(screen.getByRole("switch", { name: /use the organization's trade vocabulary/i })).toBeTruthy();
    });

    it("[greeting and silence, E1 E2 of 25/09] shows the three settings, off and 2 and 35 by default", async () => {
        await rendreLaPage();
        ouvrirLeTheme("tour");
        ouvrirLeTheme("rythme");
        const accueil = screen.getByRole("switch", { name: /caller can cut the greeting/i });
        expect(accueil.getAttribute("aria-checked")).toBe("false");
        const mots = document.getElementById("accueil_mots_minimum") as HTMLInputElement;
        const silence = document.getElementById("raccrochage_silence_agent_s") as HTMLInputElement;
        expect(mots.value).toBe("2");
        expect(silence.value).toBe("35");
        // The bounds are shown (convention E5), and the word count is inert
        // while the greeting cannot be cut.
        expect(document.querySelector('[data-reglage="accueil_mots_minimum"]')?.textContent).toContain("≥ 1 · ≤ 10");
        expect(document.querySelector('[data-reglage="raccrochage_silence_agent_s"]')?.textContent).toContain("≥ 10 · ≤ 120");
        expect(mots.disabled).toBe(true);
    });

    it("carries a Save button per theme on the page (existence only -- disabled until something changes)", async () => {
        // What saving actually sends is `reglages-agent/references/charges-utiles-agent.test.tsx`.
        await rendreLaPage();
        ouvrirLeTheme("tour");
        ouvrirLeTheme("ecoute");
        expect(screen.getByRole("button", { name: "Save Turn taking" })).toBeTruthy();
        expect(screen.getByRole("button", { name: "Save Listening" })).toBeTruthy();
    });

    it("has an entry per theme in the navigation, pointing at a theme that exists", async () => {
        // An entry whose id no element carries is an entry that does nothing, silently.
        const { container } = await rendreLaPage();
        for (const id of ["agent", "briques", "ecoute", "tour", "voix", "rythme", "donnees", "etablissement"]) {
            expect(container.querySelector(`a[href="#${id}"]`), id).not.toBeNull();
            expect(container.querySelector(`#${id}`), id).not.toBeNull();
        }
        expect(container.querySelector('a[href="#tour"]')?.textContent).toContain("Turn taking");
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

    it("[call record] is really mounted, with its switch, its field editor, its theme's Save button and navigation entry", async () => {
        // Plan fiche au fil de l'eau, lot 5: a switch nobody can reach is a
        // switch nobody turns on.
        const { container } = await rendreLaPage();
        const theme = ouvrirLeTheme("donnees");
        expect(theme.contains(document.getElementById("fiche_au_fil_de_leau"))).toBe(true);
        expect(document.getElementById("fiche_au_fil_de_leau")?.getAttribute("aria-checked")).toBe("false");
        expect(screen.getByRole("button", { name: /edit fields/i })).toBeTruthy();
        expect(screen.getByRole("button", { name: "Save Call data" })).toBeTruthy();
        expect(container.querySelector('a[href="#donnees"]')?.textContent).toContain("Call data");
    });

    it("[call record] the field editor of the MOUNTED theme offers the allowed values (PB3)", async () => {
        await rendreLaPage();
        ouvrirLeTheme("donnees");
        screen.getByRole("button", { name: /edit fields/i }).click();
        (await screen.findByRole("button", { name: /add field/i })).click();
        expect(await screen.findByLabelText("Allowed values")).toBe(document.getElementById("fiche_valeurs_0"));
    });

    it("[call record] a brand field of the MOUNTED theme is read by the trade vocabulary (C10)", async () => {
        await rendreLaPage();
        ouvrirLeTheme("donnees");
        screen.getByRole("button", { name: /edit fields/i }).click();
        (await screen.findByRole("button", { name: /add field/i })).click();
        const nom = (await screen.findByLabelText("Name")) as HTMLInputElement;
        fireEvent.change(nom, { target: { value: "marque_appareil" } });
        expect(document.getElementById("fiche_lecteur_0")?.textContent).toContain("From the name (lexique)");
    });

    it("[reference reader] its trigger names are on the page when the number conversion is on", async () => {
        await rendreLaPage();
        ouvrirLeTheme("ecoute");
        // Off by default: the field appears with the switch.
        expect(document.getElementById("variables_reference")).toBeNull();
        (document.getElementById("conversion_nombres_transcription") as HTMLElement).click();
        const champ = (await screen.findByLabelText(/variables that trigger the reference reader/i)) as HTMLInputElement;
        expect(champ.value).toBe("reference*");
    });

    it("[opening hours] are really mounted, with their field, their theme's Save button and navigation entry", async () => {
        const { container } = await rendreLaPage();
        const theme = ouvrirLeTheme("etablissement");
        expect(theme.contains(document.getElementById("horaires_ouverture"))).toBe(true);
        expect(screen.getByRole("button", { name: "Save Business" })).toBeTruthy();
        expect(container.querySelector('a[href="#etablissement"]')?.textContent).toContain("Business");
    });

    it("[verification-communes] the business address is mounted, with its fields, right after the opening hours", async () => {
        await rendreLaPage();
        ouvrirLeTheme("etablissement");
        expect(screen.getByRole("heading", { name: "Business address for this agent" })).toBeTruthy();
        const codePostal = document.getElementById("agent-business-address-code-postal");
        expect(codePostal).not.toBeNull();
        expect(document.getElementById("agent-business-address-commune")).not.toBeNull();
        // After the opening hours (plan, lot 5).
        const horaires = document.getElementById("horaires_ouverture") as HTMLElement;
        expect(horaires.compareDocumentPosition(codePostal as HTMLElement) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy();
    });

    it("[verification-communes] the town check switch is on the page, ON by default", async () => {
        await rendreLaPage();
        ouvrirLeTheme("ecoute");
        const interrupteur = screen.getByRole("switch", { name: /recognise the caller's town/i });
        expect(interrupteur.getAttribute("aria-checked")).toBe("true");
    });

    it("[variables-commune] the town variable names are on the page, under the switch, with the default and the notice", async () => {
        // Rendered on the PAGE, not the section alone: the 29 settings of
        // 2026-09-14 rendered perfectly in a file no screen mounted.
        await rendreLaPage();
        const theme = ouvrirLeTheme("ecoute");
        const interrupteur = screen.getByRole("switch", { name: /recognise the caller's town/i });
        const champ = screen.getByLabelText("Variables that trigger the town check") as HTMLInputElement;
        expect(champ.value).toBe("commune, commune_*, adresse*");
        // Under the switch, inside the same theme.
        expect(theme.contains(champ)).toBe(true);
        expect(interrupteur.compareDocumentPosition(champ) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy();
        // The notice: where the name is, commas, the final *, an example, empty = default.
        const texte = theme.textContent ?? "";
        expect(texte).toMatch(/Variables to Extract and its Variable Name/);
        expect(texte).toMatch(/separate them with commas/);
        expect(texte).toMatch(/A \* at the end means "every name that starts with"/);
        expect(texte).toMatch(/Example: ville, lieu_chantier, adresse\*/);
        expect(texte).toMatch(/Leave empty to go back to the default: commune, commune_\*, adresse\*/);
    });

    it("[coupure] the group of the moments the agent can't be interrupted carries its title on the page", async () => {
        await rendreLaPage();
        ouvrirLeTheme("tour");
        expect(screen.getByRole("heading", { name: "Moments when the agent can't be interrupted" })).toBeTruthy();
        // The old title read as General > Interruption, which is another setting.
        expect(screen.queryByRole("heading", { name: "Interruptions" })).toBeNull();
    });

    it("[nombres-dictes] the number switch tells what it now does, on the page", async () => {
        await rendreLaPage();
        ouvrirLeTheme("ecoute");
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
