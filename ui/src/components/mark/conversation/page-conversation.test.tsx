/**
 * [.mark] La page d'une conversation (U3, carte `10` : `/workflow/[id]/run/[runId]` → onglet Appels → page d'une conversation).
 *
 * Questions de ce fichier :
 *
 *     Les sept onglets sont-ils là, dans l'ordre du plan ? Chaque bloc de ce que montrait la fenêtre du run se retrouve-t-il
 *     dans un onglet (aucune fonction en moins) ? « Créer un test depuis cette réplique » est-il branché sur l'appel (agent,
 *     conversation, rang demandé) ? L'analyse du run n'est-elle lue qu'une fois pour tous les onglets ?
 */
import { cleanup, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import type { ReactNode } from "react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

const m = vi.hoisted(() => ({
    recherche: "agent=12",
    fenetres: [] as { blocs: string[] | undefined; lue: boolean }[],
    analyses: 0,
    creerUnTest: vi.fn(),
    run: vi.fn(),
}));

vi.mock("next/link", () => ({ default: ({ children, href, ...r }: { children: ReactNode; href: string }) => <a href={href} {...r}>{children}</a> }));
vi.mock("next/navigation", () => ({
    useParams: () => ({ runId: "7" }),
    useSearchParams: () => new URLSearchParams(m.recherche),
}));
vi.mock("sonner", () => ({ toast: Object.assign(vi.fn(), { error: vi.fn(), success: vi.fn() }) }));
// Un objet STABLE : la page relit l'appel quand `auth` change, un objet neuf à chaque rendu la ferait boucler.
vi.mock("@/lib/auth", () => {
    const auth = { user: { id: "u" }, loading: false, isAuthenticated: true, redirectToLogin: () => undefined };
    return { useAuth: () => auth };
});
vi.mock("@/hooks/useOrganizationTimezone", () => ({ useOrganizationTimezone: () => "UTC" }));
vi.mock("@/client/sdk.gen", () => ({
    getWorkflowRunApiV1WorkflowWorkflowIdRunsRunIdGet: m.run,
    getWorkflowApiV1WorkflowFetchWorkflowIdGet: async () => ({ data: { name: "Agent d'accueil" } }),
}));
vi.mock("@/components/mark/fenetre-du-run/FenetreDuRun", () => ({
    useAnalyseDuRun: () => {
        m.analyses += 1;
        return { analyse: null, erreur: null };
    },
    FenetreDuRun: ({ blocs, lue }: { blocs?: string[]; lue?: unknown }) => {
        m.fenetres.push({ blocs, lue: Boolean(lue) });
        return <div data-fenetre-blocs={(blocs ?? ["tous"]).join(",")} />;
    },
}));
vi.mock("@/components/builder/tests/BoutonCreerUnTest", () => ({
    BoutonCreerUnTest: (p: { workflowId: number; runId: number; rangInitial?: number }) => {
        m.creerUnTest(p);
        return <div data-testid="creer-un-test" />;
    },
}));
vi.mock("@/components/mark/BilanGreffier", () => ({ BilanGreffier: () => <div data-testid="bilan-greffier" /> }));
vi.mock("@/components/mark/groupe/TraceDesAgents", () => ({ TraceDesAgents: () => <div data-testid="trace-des-agents" /> }));
vi.mock("@/components/mark/groupe/PhrasesDuCode", () => ({ PhrasesDuCode: () => <div data-testid="phrases-du-code" /> }));
vi.mock("@/components/MediaPreviewDialog", () => ({
    MediaPreviewDialog: () => ({ openPreview: vi.fn(), dialog: null }),
    MediaPreviewButton: () => <button type="button">Preview audio</button>,
}));
vi.mock("@/components/onboarding/OnboardingTooltip", () => ({ OnboardingTooltip: () => null }));
vi.mock("@/components/workflow/conversation", () => ({
    ConversationRailFrame: ({ children }: { children: ReactNode }) => <div data-testid="rail">{children}</div>,
    RealtimeFeedback: () => <div data-testid="journal-evenements" />,
}));

const { default: PageConversation } = await import("@/app/workflow/[workflowId]/run/[runId]/page");

const run = (surcharge: Record<string, unknown> = {}) => ({
    data: {
        mode: "smallwebrtc",
        created_at: "2026-11-02T10:00:00Z",
        is_completed: true,
        transcript_url: "t",
        recording_url: "r",
        cost_info: { call_duration_seconds: 65 },
        initial_context: { appelant: "Camille" },
        gathered_context: { nom: "Dupont" },
        logs: { realtime_feedback_events: [] },
        annotations: { qa: { score: 4 } },
        ...surcharge,
    },
});

beforeEach(() => {
    m.recherche = "agent=12";
    m.fenetres.length = 0;
    m.analyses = 0;
    m.creerUnTest.mockClear();
    m.run.mockReset();
    m.run.mockResolvedValue(run());
    window.history.replaceState({}, "", "/conversations/7?agent=12");
});
afterEach(cleanup);

const attendre = async () => {
    await screen.findByRole("tab", { name: "Transcript" });
};

describe("les sept onglets", () => {
    it("sont ceux du plan, dans l'ordre, la Transcription étant la première", async () => {
        render(<PageConversation />);
        await attendre();
        const onglets = within(screen.getByRole("tablist")).getAllByRole("tab");
        expect(onglets.map((o) => o.textContent)).toEqual([
            "Transcript",
            "Event log",
            "Agents and tools",
            "Code sentences",
            "Costs",
            "Quality control",
            "Context",
        ]);
        expect(onglets[0].getAttribute("aria-selected")).toBe("true");
    });

    it("la fenêtre du run n'a perdu aucun bloc : tous se retrouvent dans un onglet, une seule fois", async () => {
        render(<PageConversation />);
        await attendre();
        const dits = m.fenetres.flatMap((f) => f.blocs ?? ["tous"]);
        expect(dits).not.toContain("tous");
        expect([...dits].sort()).toEqual(
            [
                "simulation", "resume", "apres-appel", "latence", "chrono", "reseau", "fournisseurs", "modules",
                "fiche", "parcours", "conversation", "incidents",
            ].sort(),
        );
    });

    it("range chaque bloc dans le bon onglet", async () => {
        render(<PageConversation />);
        await attendre();
        const volet = (id: string) => document.querySelector(`[data-onglet-conversation="${id}"]`) as HTMLElement;
        const blocs = (id: string) => [...volet(id).querySelectorAll("[data-fenetre-blocs]")].map((e) => e.getAttribute("data-fenetre-blocs"));
        expect(blocs("transcription")).toEqual(["conversation"]);
        expect(blocs("journal")).toEqual(["incidents,latence,chrono,reseau"]);
        expect(blocs("agents")).toEqual(["parcours,modules,fiche"]);
        expect(blocs("couts")).toEqual(["fournisseurs"]);
        expect(within(volet("transcription")).getByTestId("creer-un-test")).toBeTruthy();
        expect(within(volet("journal")).getByTestId("journal-evenements")).toBeTruthy();
        expect(within(volet("agents")).getByTestId("trace-des-agents")).toBeTruthy();
        expect(within(volet("phrases")).getByTestId("phrases-du-code")).toBeTruthy();
        expect(within(volet("couts")).getByTestId("bilan-greffier")).toBeTruthy();
        expect(within(volet("couts")).getByText("Run Metrics")).toBeTruthy();
        expect(within(volet("qualite")).getByText("QA Results")).toBeTruthy();
        expect(within(volet("contexte")).getByText("Initial Context")).toBeTruthy();
        expect(within(volet("contexte")).getByText("Gathered Context")).toBeTruthy();
    });

    it("donne l'analyse déjà lue à chaque fenêtre : aucun onglet ne la relit (la page la lit une fois)", async () => {
        render(<PageConversation />);
        await attendre();
        expect(m.fenetres.length).toBeGreaterThanOrEqual(5);
        expect(m.fenetres.every((f) => f.lue)).toBe(true);
    });
});

describe("créer un test depuis cette réplique", () => {
    it("est branché sur l'agent et l'appel de l'adresse, et transmet le rang demandé", async () => {
        m.recherche = "agent=12&creer_test=3";
        render(<PageConversation />);
        await attendre();
        await waitFor(() => expect(m.creerUnTest).toHaveBeenCalled());
        expect(m.creerUnTest.mock.calls.at(-1)![0]).toMatchObject({ workflowId: 12, runId: 7, rangInitial: 3 });
    });

    it("sans rang demandé, aucun rang n'est imposé", async () => {
        render(<PageConversation />);
        await attendre();
        expect(m.creerUnTest.mock.calls.at(-1)![0].rangInitial).toBeUndefined();
    });
});

describe("l'en-tête et le changement d'onglet", () => {
    it("dit l'agent, mène au Parcours de cet agent et change de volet au clic", async () => {
        render(<PageConversation />);
        await attendre();
        expect(await screen.findByText("Agent d'accueil")).toBeTruthy();
        expect(screen.getByRole("link", { name: "Customize the agent" }).getAttribute("href")).toBe("/agents/12");
        const volet = (id: string) => document.querySelector(`[data-onglet-conversation="${id}"]`)?.closest("[role=tabpanel]") as HTMLElement;
        expect(volet("journal").hidden).toBe(true);
        fireEvent.click(screen.getByRole("tab", { name: "Event log" }));
        expect(volet("journal").hidden).toBe(false);
        expect(volet("transcription").hidden).toBe(true);
        // L'onglet est lu dans l'adresse sans perdre l'agent.
        expect(window.location.search).toContain("agent=12");
        expect(window.location.search).toContain("onglet=journal");
    });

    it("une conversation qui n'est pas terminée n'a pas d'onglets (la page garde son message d'avant)", async () => {
        m.run.mockResolvedValue(run({ is_completed: false }));
        render(<PageConversation />);
        await screen.findByText("Run Details Unavailable");
        expect(screen.queryByRole("tablist")).toBeNull();
    });

    it("sans audio (chat écrit) : ni aperçu ni téléchargement, mais les mêmes onglets", async () => {
        m.run.mockResolvedValue(run({ mode: "textchat", recording_url: null, transcript_url: null }));
        render(<PageConversation />);
        await attendre();
        expect(screen.queryByRole("button", { name: "Preview audio" })).toBeNull();
        expect(within(screen.getByRole("tablist")).getAllByRole("tab")).toHaveLength(7);
    });
});
