/**
 * [.mark] Clôture SA-5 (É35) : la liste des appels d'un agent envoie la recherche et le motif AU SERVEUR (dans la requête, page 1), et
 * propose les motifs que le serveur rend.
 */
import { act, cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { FournisseurLangue } from "@/components/mark/langue/langue";

const m = vi.hoisted(() => ({ runs: vi.fn() }));
vi.mock("@/client/sdk.gen", async (importOriginal) =>
    (await import("@/components/mark/sdk-factice")).sdkFactice(await importOriginal(), { getWorkflowRunsApiV1WorkflowWorkflowIdRunsGet: m.runs }),
);
vi.mock("@/components/mark/studio/liste-deroulante", async () => await import("@/components/mark/studio/liste-deroulante-natif-test"));
vi.mock("next/navigation", () => ({ useRouter: () => ({ push: vi.fn() }) }));
vi.mock("@/lib/auth", () => ({ useAuth: () => ({ isAuthenticated: true, user: { id: 1 }, loading: false }) }));
vi.mock("@/hooks/useDispositionCodes", () => ({ useDispositionCodes: () => ({ codes: [] }) }));
vi.mock("@/hooks/useOrganizationTimezone", () => ({ useOrganizationTimezone: () => "Europe/Paris" }));
vi.mock("@/components/filters/FilterBuilder", () => ({ FilterBuilder: () => null }));
vi.mock("@/components/MediaPreviewDialog", () => ({ MediaPreviewButton: () => null, MediaPreviewDialog: () => ({ openPreview: vi.fn(), dialog: null }) }));

import { WorkflowExecutions } from "./WorkflowExecutions";

const UN = {
    id: 1, workflow_id: 9, name: "r", mode: "twilio", created_at: "2026-11-09T10:00:00Z", is_completed: true, cost_info: { call_duration_seconds: 30 },
    call_type: "inbound", gathered_context: {}, motif: "Devis", resume: null, juge_par: null, note_juge: null,
};

beforeEach(() => {
    m.runs.mockResolvedValue({ data: { runs: [UN], total_count: 1, page: 1, limit: 50, total_pages: 1, motifs: ["Devis", "Dépannage"] } });
});
afterEach(() => {
    cleanup();
    vi.clearAllMocks();
    window.localStorage.clear();
});

const monter = () =>
    render(
        <FournisseurLangue>
            <WorkflowExecutions workflowId={9} searchParams={new URLSearchParams()} forme="agent" />
        </FournisseurLangue>,
    );

describe("[.mark] la liste des appels d'un agent interroge le serveur", () => {
    it("le motif choisi part dans la requête, en page 1, et les motifs viennent du serveur", async () => {
        monter();
        const liste = (await screen.findByLabelText("Motif")) as HTMLSelectElement;
        expect(Array.from(liste.options).map((o) => o.textContent)).toEqual(["Tous les motifs", "Devis", "Dépannage"]);
        expect(m.runs.mock.calls[0][0].query.motif).toBeUndefined();
        fireEvent.change(liste, { target: { value: "Dépannage" } });
        await waitFor(() => expect(m.runs.mock.calls.at(-1)![0].query).toMatchObject({ page: 1, motif: "Dépannage" }));
    });

    it("la recherche part dans la requête après la pause de saisie", async () => {
        monter();
        const champ = await screen.findByLabelText("Chercher un mot");
        fireEvent.change(champ, { target: { value: "chaudière" } });
        await act(async () => void (await new Promise((r) => setTimeout(r, 500))));
        await waitFor(() => expect(m.runs.mock.calls.at(-1)![0].query).toMatchObject({ page: 1, recherche: "chaudière" }));
    });
});
