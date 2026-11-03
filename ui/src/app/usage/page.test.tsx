/**
 * [.mark] K8 : Conversations (appels passés) à la forme de la maquette : un titre, les filtres, puis un tableau NU (jamais
 * dans une carte) dont un clic sur la ligne ouvre l'appel ; états vides `premier`, `filtre`, `chargement`, `erreur`.
 */
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { FournisseurLangue } from "@/components/mark/langue/langue";

const m = vi.hoisted(() => ({
    historique: vi.fn(),
    push: vi.fn(),
    replace: vi.fn(),
}));

vi.mock("@/client/sdk.gen", () => ({
    getUsageHistoryApiV1OrganizationsUsageRunsGet: m.historique,
    getDailyUsageBreakdownApiV1OrganizationsUsageDailyBreakdownGet: vi.fn().mockResolvedValue({ data: null }),
    getPreferencesApiV1OrganizationsPreferencesGet: vi.fn().mockResolvedValue({ data: {} }),
    savePreferencesApiV1OrganizationsPreferencesPut: vi.fn(),
    getWorkflowsSummaryApiV1WorkflowSummaryGet: vi.fn().mockResolvedValue({ data: [] }),
    downloadUsageRunsReportApiV1OrganizationsUsageRunsReportGet: vi.fn(),
}));
vi.mock("@/lib/auth", () => ({ useAuth: () => ({ isAuthenticated: true, user: { id: 1 }, loading: false }) }));
vi.mock("@/context/UserConfigContext", () => ({ useUserConfig: () => ({ organizationPricing: null }) }));
vi.mock("@/hooks/useDispositionCodes", () => ({ useDispositionCodes: () => ({ codes: [], systemCodes: [], endTaskReasonCodes: [], isLoading: false }) }));
vi.mock("next/navigation", () => ({
    useRouter: () => ({ push: m.push, replace: m.replace, prefetch: vi.fn() }),
    useSearchParams: () => new URLSearchParams(),
}));
vi.mock("react-timezone-select", () => ({ default: () => <div data-testid="fuseau" /> }));
vi.mock("@/components/filters/FilterBuilder", () => ({ FilterBuilder: () => <div data-testid="filtres" /> }));
vi.mock("@/components/MediaPreviewDialog", () => ({
    MediaPreviewDialog: () => ({ openPreview: vi.fn(), dialog: null }),
    MediaPreviewButton: ({ runId }: { runId: number }) => <button type="button" data-testid={`apercu-${runId}`}>aperçu</button>,
}));
vi.mock("@/components/DailyUsageTable", () => ({ DailyUsageTable: () => null }));
vi.mock("@/components/CallTypeCell", () => ({ CallTypeCell: ({ callType }: { callType?: string | null }) => <span>{callType}</span> }));

import UsagePage from "./page";

const RUN = {
    id: 41,
    workflow_id: 3,
    workflow_name: "Standard Nuances de Feu",
    name: "run",
    created_at: "2026-11-03T09:30:00Z",
    dograh_token_usage: 10,
    call_duration_seconds: 125,
    call_type: "inbound",
    mode: "twilio",
    caller_number: "+33344000000",
    called_number: null,
    disposition: "Rendez-vous créé",
    client: "Claire Dupont",
    motif: "Devis",
    note_juge: 3.2,
    version: 4,
    canal: "site",
};
const page = (runs: unknown[], total = runs.length, pages = 1) => ({
    data: { runs, page: 1, limit: 50, total_count: total, total_pages: pages, total_dograh_tokens: 0, total_duration_seconds: 0 },
});

const monter = () => render(<FournisseurLangue><UsagePage /></FournisseurLangue>);

beforeEach(() => {
    m.historique.mockReset();
    m.push.mockReset();
});
afterEach(() => cleanup());

describe("[.mark] K8 : Conversations", () => {
    it("un tableau nu : Quand, Agent, Version, Client, Motif, Canal, Issue, Durée, Note, Médias ; jamais dans une carte", async () => {
        m.historique.mockResolvedValue(page([RUN]));
        const { container } = monter();
        expect(await screen.findByText("Standard Nuances de Feu")).toBeTruthy();
        expect(screen.getByRole("heading", { level: 1 }).textContent).toContain("Conversations");
        expect(Array.from(container.querySelectorAll("th")).map((th) => th.textContent)).toEqual([
            "Quand", "Agent", "Version", "Client", "Motif", "Canal", "Issue", "Durée", "Note", "Médias",
        ]);
        expect(screen.getByText("Rendez-vous créé")).toBeTruthy();
        expect(screen.getByText("+33344000000")).toBeTruthy(); // le numéro reste, sous le nom
        expect(screen.getByText("2m 5s")).toBeTruthy();
        expect(container.querySelector('[data-slot="card"]')).toBeNull();
        expect(container.querySelector("table")?.parentElement?.className ?? "").not.toMatch(/border|shadow/);
    });

    it("un clic sur la ligne ouvre l'appel ; le bouton d'aperçu n'ouvre pas la ligne", async () => {
        m.historique.mockResolvedValue(page([RUN]));
        monter();
        fireEvent.click(await screen.findByTestId("apercu-41"));
        expect(m.push).not.toHaveBeenCalled();
        fireEvent.click(screen.getByText("Standard Nuances de Feu"));
        expect(m.push).toHaveBeenCalledWith("/workflow/3/run/41");
    });

    it("aucun appel : l'état vide « Aucun appel encore », sans tableau", async () => {
        m.historique.mockResolvedValue(page([]));
        const { container } = monter();
        expect(await screen.findByText("Aucun appel encore")).toBeTruthy();
        expect(container.querySelector("table")).toBeNull();
    });

    it("une lecture qui échoue montre l'état d'erreur, et « Réessayer » relit", async () => {
        m.historique.mockResolvedValueOnce({ error: { detail: "boom" } });
        m.historique.mockResolvedValueOnce(page([RUN]));
        monter();
        fireEvent.click(await screen.findByRole("button", { name: /Réessayer/ }));
        await waitFor(() => expect(m.historique).toHaveBeenCalledTimes(2));
        expect(await screen.findByText("Standard Nuances de Feu")).toBeTruthy();
    });

    it("au-delà d'une page, la barre de pagination relit la page suivante", async () => {
        m.historique.mockResolvedValue(page([RUN], 120, 3));
        monter();
        await screen.findByText("Standard Nuances de Feu");
        fireEvent.click(screen.getByRole("button", { name: /Page suivante/ }));
        await waitFor(() => expect(m.historique).toHaveBeenLastCalledWith(expect.objectContaining({ query: expect.objectContaining({ page: 2, limit: 50 }) })));
    });

    it("chaque colonne est lue de la ligne : client, motif, version, canal, note (pastille sous 3,5)", async () => {
        m.historique.mockResolvedValue(page([RUN, { ...RUN, id: 42, client: null, motif: null, note_juge: null, version: null, canal: "telephony" }]));
        const { container } = monter();
        await screen.findAllByText("Standard Nuances de Feu");
        expect(screen.getByText("Claire Dupont")).toBeTruthy();
        expect(screen.getByText("Devis")).toBeTruthy();
        expect(screen.getByText("v4")).toBeTruthy();
        expect(screen.getByText("Site")).toBeTruthy();
        expect(screen.getByText("Téléphone")).toBeTruthy();
        expect(screen.getByText("3,2")).toBeTruthy();
        expect(screen.getByText("–")).toBeTruthy(); // pas encore jugé : un tiret, jamais 0
        expect(container.querySelectorAll("tbody tr")).toHaveLength(2);
    });

    it("les en-têtes Version et Note trient côté serveur", async () => {
        m.historique.mockResolvedValue(page([RUN]));
        monter();
        await screen.findByText("Standard Nuances de Feu");
        fireEvent.click(screen.getByRole("button", { name: /^Note/ }));
        await waitFor(() => expect(m.historique).toHaveBeenLastCalledWith(expect.objectContaining({ query: expect.objectContaining({ sort_by: "judge_note", sort_order: "desc" }) })));
        fireEvent.click(screen.getByRole("button", { name: /^Version/ }));
        await waitFor(() => expect(m.historique).toHaveBeenLastCalledWith(expect.objectContaining({ query: expect.objectContaining({ sort_by: "version" }) })));
    });

    it("la recherche dans les transcriptions part après une pause, à partir de 3 lettres, et s'efface avec la case", async () => {
        m.historique.mockResolvedValue(page([RUN]));
        monter();
        await screen.findByText("Standard Nuances de Feu");
        const champ = screen.getByRole("textbox", { name: /Chercher dans les transcriptions/ });
        fireEvent.change(champ, { target: { value: "de" } });
        await new Promise((r) => setTimeout(r, 600));
        expect(m.historique.mock.calls.every(([a]) => !("q" in a.query))).toBe(true); // 2 lettres : rien ne part
        fireEvent.change(champ, { target: { value: "devis" } });
        await waitFor(() => expect(m.historique).toHaveBeenLastCalledWith(expect.objectContaining({ query: expect.objectContaining({ q: "devis", page: 1 }) })));
        fireEvent.change(champ, { target: { value: "" } });
        await waitFor(() => expect(m.historique.mock.calls.at(-1)?.[0].query).not.toHaveProperty("q"));
    });

    it("une recherche sans résultat montre l'état « filtre » avec le terme", async () => {
        m.historique.mockResolvedValueOnce(page([RUN]));
        m.historique.mockResolvedValue(page([]));
        monter();
        await screen.findByText("Standard Nuances de Feu");
        fireEvent.change(screen.getByRole("textbox", { name: /Chercher dans les transcriptions/ }), { target: { value: "zzzz" } });
        expect(await screen.findByText(/zzzz/)).toBeTruthy();
        expect(screen.queryByText("Aucun appel encore")).toBeNull();
    });
});
