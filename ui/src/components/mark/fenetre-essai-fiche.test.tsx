/**
 * [.mark] The test window and the fiche of the agent (chantier agents-specialises, lot 11, C8), mounted in
 * Dograh's real tester panel.
 *
 *   - an agent WITHOUT a fiche: the choice of the establishment is offered, and the run is created with the
 *     establishment chosen (as before);
 *   - an agent WITH a fiche: nothing to choose (it brings its own), and no establishment is sent, even if one
 *     had been chosen before the fiche was set.
 */
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { WorkflowTesterPanel } from "@/app/workflow/[workflowId]/components/WorkflowTesterPanel";

import { FournisseurLangue } from "./langue/langue";

const m = vi.hoisted(() => ({ creer: vi.fn(), fiches: vi.fn() }));

vi.mock("@/client/sdk.gen", async (importOriginal) => (await import("./sdk-factice")).sdkFactice(await importOriginal(), {
    createWorkflowRunApiV1WorkflowWorkflowIdRunsPost: m.creer,
    getEtablissementsApiV1OrganizationsEtablissementsGet: m.fiches,
}));
vi.mock("sonner", () => ({ toast: { error: vi.fn(), success: vi.fn() } }));
vi.mock("posthog-js", () => ({ default: { capture: vi.fn() } }));
vi.mock("@/lib/auth", () => {
    const auth = { isAuthenticated: true, loading: false, user: { id: "u-1" }, getAccessToken: async () => "jeton" };
    return { useAuth: () => auth };
});
vi.mock("@/context/OnboardingContext", () => ({ useOnboarding: () => ({ markActionCompleted: vi.fn() }) }));
vi.mock("@/components/onboarding/OnboardingTooltip", () => ({ OnboardingTooltip: () => null }));
vi.mock("@/app/workflow/[workflowId]/components/workflow-tester/EmbeddedVoiceTester", () => ({
    EmbeddedVoiceTester: () => <div data-testid="voice-tester" />,
}));
vi.mock("@/app/workflow/[workflowId]/components/workflow-tester/ManualTextChatPanel", () => ({ ManualTextChatPanel: () => <div /> }));
vi.mock("@/app/workflow/[workflowId]/components/workflow-tester/AiSimulatorPlaceholder", () => ({ AiSimulatorPlaceholder: () => null }));

const FICHES = [
    { id: "creil", nom: "Magasin de Creil", numeros: [] },
    { id: "senlis", nom: "Magasin de Senlis", numeros: [] },
];

afterEach(() => {
    cleanup();
    m.creer.mockReset();
    m.fiches.mockReset();
    window.localStorage.clear();
});

const rendre = (ficheDeLagent: string | null) => {
    window.localStorage.setItem("mark.langue", "en");
    m.fiches.mockResolvedValue({ data: { format: "etablissements-mark", version: 1, etablissements: FICHES } });
    m.creer.mockResolvedValue({ data: { id: 77 }, error: undefined });
    return render(
        <FournisseurLangue>
            <WorkflowTesterPanel workflowId={34} disabled={false} disabledReason={null} ficheDeLagent={ficheDeLagent} />
        </FournisseurLangue>,
    );
};

const lancer = async () => {
    fireEvent.click(await screen.findByRole("button", { name: /run test/i }));
    await waitFor(() => expect(m.creer).toHaveBeenCalledTimes(1));
    return m.creer.mock.calls[0][0].body as Record<string, unknown>;
};

describe("[.mark] the test window, establishment choice (C8)", () => {
    it("offers the choice to an agent without a fiche, and sends the establishment chosen", async () => {
        rendre(null);
        const choix = await screen.findByTestId("choix-etablissement-essai");
        fireEvent.change(choix.querySelector("select")!, { target: { value: "senlis" } });
        expect((await lancer()).etablissement_id).toBe("senlis");
    });

    it("offers none to an agent with a fiche, and sends no establishment", async () => {
        rendre("creil");
        await waitFor(() => expect(m.fiches).toHaveBeenCalled());
        expect(screen.queryByTestId("choix-etablissement-essai")).toBeNull();
        expect(await lancer()).not.toHaveProperty("etablissement_id");
    });

    it("forgets an establishment chosen earlier once the agent has a fiche", async () => {
        const { rerender } = rendre(null);
        const choix = await screen.findByTestId("choix-etablissement-essai");
        fireEvent.change(choix.querySelector("select")!, { target: { value: "senlis" } });
        rerender(
            <FournisseurLangue>
                <WorkflowTesterPanel workflowId={34} disabled={false} disabledReason={null} ficheDeLagent="creil" />
            </FournisseurLangue>,
        );
        expect(screen.queryByTestId("choix-etablissement-essai")).toBeNull();
        expect(await lancer()).not.toHaveProperty("etablissement_id");
    });
});
