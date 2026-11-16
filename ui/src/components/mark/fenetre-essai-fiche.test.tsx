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
// La liste déroulante du design system (V1b) est un faux <select> pour le test, comme dans liste-deroulante.test.tsx.
vi.mock("@/components/ui/select", async () => await import("./studio/select-natif-test"));
vi.mock("sonner", () => ({ toast: { error: vi.fn(), success: vi.fn() } }));
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
    fireEvent.click(await screen.findByRole("button", { name: /start the call/i }));
    await waitFor(() => expect(m.creer).toHaveBeenCalledTimes(1));
    return m.creer.mock.calls[0][0].body as Record<string, unknown>;
};

describe("[.mark] the test window, no establishment row (lot 20, F12)", () => {
    // Evan, 15/11 : la ligne « Établissement joué » est retirée de la fenêtre d'essai (l'agent est relié à son établissement ; le restaurant de test se
    // choisit dans la fenêtre Caisse / POS, au Labo).
    it("offers no establishment choice to an agent without a fiche, and sends no establishment", async () => {
        rendre(null);
        await screen.findByRole("button", { name: /start the call/i });
        expect(screen.queryByTestId("choix-etablissement-essai")).toBeNull();
        expect(screen.queryByText(/establishment played/i)).toBeNull();
        expect(await lancer()).not.toHaveProperty("etablissement_id");
    });

    it("offers none to an agent with a fiche either, and sends no establishment", async () => {
        rendre("creil");
        await screen.findByRole("button", { name: /start the call/i });
        expect(screen.queryByTestId("choix-etablissement-essai")).toBeNull();
        expect(await lancer()).not.toHaveProperty("etablissement_id");
    });

    it("shows no simulators menu outside the Labo (the demo till does not exist for this account)", async () => {
        rendre(null);
        await screen.findByRole("button", { name: /start the call/i });
        expect(screen.queryByRole("button", { name: /add a simulator/i })).toBeNull();
    });
});
