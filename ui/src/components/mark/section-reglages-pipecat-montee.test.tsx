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
 * So this file asserts the whole chain, one link at a time:
 *   1. the settings page imports our section,
 *   2. it renders it,
 *   3. it hands it the configuration and the save callback (a section rendered
 *      without them would be a decoration),
 *   4. the sidebar carries an entry for it,
 *   5. and that entry's id is the id our card actually puts in the DOM —
 *      checked by rendering the card and reading the id back, not by trusting
 *      that two string literals match.
 *
 * Link 5 is the one that cannot be faked: it reads their file and our DOM.
 */

import { readFileSync } from "node:fs";
import { join } from "node:path";

import { render } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import type { WorkflowConfigurations } from "@/types/workflow-configurations";
import { resolveWorkflowConfigurations } from "@/types/workflow-configurations";

import {
    ID_SECTION_REGLAGES_PIPECAT,
    SectionReglagesPipecat,
} from "./SectionReglagesPipecat";

vi.mock("sonner", () => ({ toast: { success: vi.fn(), error: vi.fn() } }));

vi.mock("@/context/OrgConfigContext", () => ({
    useOrgConfig: () => ({ userConfig: null, externalPbxIntegrationsEnabled: false }),
}));

vi.mock("@/context/UnsavedChangesContext", () => ({
    useUnsavedChanges: () => undefined,
}));

// vitest runs with the ui/ package as its working directory.
const CHEMIN_PAGE = "src/app/workflow/[workflowId]/settings/page.tsx";

const lirePage = () => readFileSync(join(process.cwd(), CHEMIN_PAGE), "utf8");

const configuration = (): WorkflowConfigurations =>
    resolveWorkflowConfigurations(null);

describe("[.mark] the Speech Tuning section is reachable on the settings page", () => {
    it("is imported by the agent settings page", () => {
        // Read honestly: this reads their page rather than rendering it (the
        // page needs auth, routing and three fetches). It catches the failure
        // that actually threatens us — our mount dropped, or the section left
        // sitting in a file nobody renders.
        expect(lirePage()).toContain('from "@/components/mark/SectionReglagesPipecat"');
    });

    it("is rendered by the agent settings page", () => {
        expect(lirePage()).toContain("<SectionReglagesPipecat");
    });

    it("is handed the configuration and the save callback, not rendered empty", () => {
        const page = lirePage();
        const montage = page.slice(
            page.indexOf("<SectionReglagesPipecat"),
            page.indexOf("<SectionReglagesPipecat") + 400,
        );

        expect(montage).toContain("workflowConfigurations={resolvedWorkflowConfigurationsForRender}");
        expect(montage).toContain("onSave={saveWorkflowConfigurations}");
    });

    it("has its own entry in the sidebar, so it can be found without scrolling blind", () => {
        const page = lirePage();
        const nav = page.slice(page.indexOf("const NAV_ITEMS"), page.indexOf("];", page.indexOf("const NAV_ITEMS")));

        expect(nav).toContain("ID_SECTION_REGLAGES_PIPECAT");
        expect(nav).toContain("Speech Tuning");
    });

    it("puts in the DOM the very id the sidebar entry points at", () => {
        // The link nothing else checks. The sidebar scrolls to `document
        // .getElementById(id)` and the intersection observer watches that same
        // id: an entry whose id no element carries is an entry that does
        // nothing, silently.
        const { container } = render(
            <SectionReglagesPipecat
                workflowConfigurations={configuration()}
                workflowName="Agent Nuances de Feu"
                onSave={vi.fn().mockResolvedValue(undefined)}
            />,
        );

        const carte = container.querySelector(`#${ID_SECTION_REGLAGES_PIPECAT}`);
        expect(carte).not.toBeNull();

        const page = lirePage();
        const nav = page.slice(page.indexOf("const NAV_ITEMS"), page.indexOf("];", page.indexOf("const NAV_ITEMS")));
        expect(nav).toContain(`id: ID_SECTION_REGLAGES_PIPECAT`);
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
