/**
 * [.mark] builder-agent-vocal (lot 4): the builder's part of the editor's top bar.
 *
 * Questions of this file:
 *
 *     Are « Builder AI » and « Tests » in the bar when the builder is wired, and absent when it is not? Is « Publish »
 *     greyed WITH its reason while the builder's changes are being reviewed, and not otherwise?
 */
import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { WorkflowEditorHeader } from "./WorkflowEditorHeader";

vi.mock("next/navigation", () => ({ useRouter: () => ({ push: vi.fn() }) }));
vi.mock("next/link", () => ({ default: ({ children, href, ...r }: { children: React.ReactNode; href: string }) => <a href={href} {...r}>{children}</a> }));
vi.mock("sonner", () => ({ toast: Object.assign(vi.fn(), { promise: vi.fn(), success: vi.fn(), error: vi.fn() }) }));
vi.mock("@/client/sdk.gen", () => ({
    duplicateWorkflowEndpointApiV1WorkflowWorkflowIdDuplicatePost: vi.fn(),
    publishWorkflowApiV1WorkflowWorkflowIdPublishPost: vi.fn(),
}));
vi.mock("@/components/layout/GitHubStarBadge", () => ({ GitHubStarBadge: () => null }));
vi.mock("@/components/ui/sidebar", () => ({ useSidebar: () => ({ toggleSidebar: vi.fn() }) }));

afterEach(cleanup);

const base = {
    workflowName: "Agent",
    isDirty: false,
    workflowValidationErrors: [],
    rfInstance: { current: null },
    workflowId: 5,
    saveWorkflow: vi.fn(),
    user: { id: "u" },
    onPhoneCallClick: vi.fn(),
    onTestAgentClick: vi.fn(),
    onHistoryClick: vi.fn(),
    isViewingHistoricalVersion: false,
    onBackToDraft: vi.fn(),
    hasDraft: true,
    onPublished: vi.fn(),
    renameWorkflow: vi.fn(),
};

describe("la barre du haut avec le builder", () => {
    it("montre « Builder IA » et « Tests » (lien vers la page des tests) quand le builder est branché", () => {
        const onToggle = vi.fn();
        render(<WorkflowEditorHeader {...base} builder={{ ouvert: false, onToggle, testsHref: "/workflow/5/tests", raisonDeBlocage: null }} />);
        fireEvent.click(screen.getByRole("button", { name: "Builder AI" }));
        expect(onToggle).toHaveBeenCalledTimes(1);
        expect(screen.getByRole("link", { name: "Tests" }).getAttribute("href")).toBe("/workflow/5/tests");
        expect((screen.getByRole("button", { name: /Publish/ }) as HTMLButtonElement).disabled).toBe(false);
    });

    it("grise « Publier » avec la raison tant que les changements du builder sont à relire", () => {
        render(
            <WorkflowEditorHeader
                {...base}
                builder={{ ouvert: true, onToggle: vi.fn(), testsHref: "/x", raisonDeBlocage: "Review the builder's changes first." }}
            />,
        );
        const publier = screen.getByRole("button", { name: /Publish/ }) as HTMLButtonElement;
        expect(publier.disabled).toBe(true);
        expect(publier.title).toBe("Review the builder's changes first.");
        expect(document.querySelector("[data-raison-publication]")?.textContent).toBe("Review the builder's changes first.");
    });

    it("sans builder branché, la barre est celle d'avant", () => {
        render(<WorkflowEditorHeader {...base} />);
        expect(screen.queryByRole("button", { name: "Builder AI" })).toBeNull();
        expect(screen.queryByRole("link", { name: "Tests" })).toBeNull();
        expect((screen.getByRole("button", { name: /Publish/ }) as HTMLButtonElement).disabled).toBe(false);
    });
});
