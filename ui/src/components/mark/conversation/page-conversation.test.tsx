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
    vues: [] as { lue: boolean }[],
    lecteurs: [] as Record<string, unknown>[],
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
    // La Transcription : résumé, tour choisi, fiche, après-appel et la transcription elle-même vivent dans cette vue.
    VueTranscription: ({ lue, avant }: { lue?: unknown; avant?: ReactNode }) => {
        m.vues.push({ lue: Boolean(lue) });
        return <div data-vue-transcription>{avant}</div>;
    },
    LigneNue: ({ libelle, children }: { libelle: ReactNode; children: ReactNode }) => <div>{libelle} {children}</div>,
}));
vi.mock("@/components/mark/conversation/LecteurConversation", () => ({
    LecteurConversation: (p: Record<string, unknown>) => {
        m.lecteurs.push(p);
        return <div data-lecteur />;
    },
}));
vi.mock("@/components/mark/conversation/JournalDesEvenements", () => ({ JournalDesEvenements: () => <div data-testid="journal-des-evenements" /> }));
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
    m.vues.length = 0;
    m.lecteurs.length = 0;
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
        // V1b : le résumé, la conversation, la fiche de l'appel et l'après-appel vivent dans la vue de la Transcription
        // (un seul montage, colonne de droite), les autres blocs restent dans leur onglet.
        expect([...dits].sort()).toEqual(
            ["simulation", "latence", "chrono", "reseau", "fournisseurs", "modules", "fiche", "parcours", "incidents"].sort(),
        );
        expect(m.vues.length).toBeGreaterThanOrEqual(1);
    });

    it("range chaque bloc dans le bon onglet", async () => {
        render(<PageConversation />);
        await attendre();
        const volet = (id: string) => document.querySelector(`[data-onglet-conversation="${id}"]`) as HTMLElement;
        const blocs = (id: string) => [...volet(id).querySelectorAll("[data-fenetre-blocs]")].map((e) => e.getAttribute("data-fenetre-blocs"));
        expect(blocs("transcription")).toEqual([]);
        expect(volet("transcription").querySelector("[data-vue-transcription]")).toBeTruthy();
        expect(blocs("journal")).toEqual(["incidents,latence,chrono,reseau"]);
        expect(blocs("agents")).toEqual(["parcours,modules,fiche"]);
        expect(blocs("couts")).toEqual(["fournisseurs"]);
        expect(within(volet("transcription")).getByTestId("creer-un-test")).toBeTruthy();
        expect(within(volet("journal")).getByTestId("journal-des-evenements")).toBeTruthy();
        expect(within(volet("agents")).getByTestId("trace-des-agents")).toBeTruthy();
        expect(within(volet("phrases")).getByTestId("phrases-du-code")).toBeTruthy();
        expect(within(volet("couts")).getByTestId("bilan-greffier")).toBeTruthy();
        expect(within(volet("couts")).getByText("Run metrics")).toBeTruthy();
        expect(within(volet("qualite")).getByText("Quality results")).toBeTruthy();
        expect(within(volet("contexte")).getByText("Initial context")).toBeTruthy();
        expect(within(volet("contexte")).getByText("Gathered context")).toBeTruthy();
    });

    it("donne l'analyse déjà lue à chaque fenêtre : aucun onglet ne la relit (la page la lit une fois)", async () => {
        render(<PageConversation />);
        await attendre();
        expect(m.fenetres.length).toBeGreaterThanOrEqual(4);
        expect(m.fenetres.every((f) => f.lue)).toBe(true);
        expect(m.vues.every((v) => v.lue)).toBe(true);
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
        expect((await screen.findAllByText(/Agent d'accueil/)).length).toBeGreaterThan(0);
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
        await screen.findByTestId("appel-sans-detail");
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

describe("V1b : la page à la forme de la maquette", () => {
    it("le titre dit « Motif · Issue » lus dans le contexte de l'appel, avec la version et la note du juge", async () => {
        m.run.mockResolvedValue(
            run({ gathered_context: { motif_appel: "Dépannage", mapped_call_disposition: "Demande enregistrée" }, version_number: 3, note_juge: 2.9 }),
        );
        render(<PageConversation />);
        await attendre();
        expect(document.querySelector("[data-titre-conversation]")?.textContent).toBe("Dépannage · Demande enregistrée");
        expect(document.querySelector("[data-page-conversation]")?.textContent).toContain("Agent d'accueil · v3");
        expect(document.querySelector("[data-note-du-juge]")?.textContent).toContain("judge 2.9/5");
    });

    it("sans motif ni issue, le titre est le nom de l'agent ; sans note, aucune note n'est écrite (jamais 0)", async () => {
        render(<PageConversation />);
        await attendre();
        expect(document.querySelector("[data-titre-conversation]")?.textContent).toBe("Agent d'accueil");
        expect(document.querySelector("[data-note-du-juge]")).toBeNull();
    });

    it("le lecteur reçoit l'enregistrement réel ; sans enregistrement, il reçoit du vide (état vide du lecteur)", async () => {
        m.run.mockResolvedValue(run({ recording_url: "enregistrement.wav" }));
        const { unmount } = render(<PageConversation />);
        await attendre();
        expect(m.lecteurs.at(-1)).toMatchObject({ enregistrement: "enregistrement.wav", pisteAppelant: null, pisteAgent: null, ecrit: false });
        unmount();
        m.lecteurs.length = 0;
        m.run.mockResolvedValue(run({ recording_url: null, transcript_url: null }));
        render(<PageConversation />);
        await attendre();
        expect(m.lecteurs.at(-1)).toMatchObject({ enregistrement: null, pisteAppelant: null, pisteAgent: null });
    });

    it("deux pistes séparées : le lecteur les reçoit toutes les deux ; une conversation au clavier est dite écrite", async () => {
        m.run.mockResolvedValue(run({ user_recording_url: "u.wav", bot_recording_url: "b.wav" }));
        const { unmount } = render(<PageConversation />);
        await attendre();
        expect(m.lecteurs.at(-1)).toMatchObject({ pisteAppelant: "u.wav", pisteAgent: "b.wav" });
        unmount();
        m.run.mockResolvedValue(run({ mode: "textchat", recording_url: null }));
        render(<PageConversation />);
        await attendre();
        expect(m.lecteurs.at(-1)).toMatchObject({ ecrit: true });
    });

    it("une lecture de l'appel qui échoue dit l'erreur et propose de réessayer (jamais un écran blanc)", async () => {
        m.run.mockResolvedValue({ error: { detail: "x" }, data: undefined });
        render(<PageConversation />);
        const bouton = await screen.findByRole("button", { name: /Try again|Réessayer/ });
        m.run.mockResolvedValue(run());
        fireEvent.click(bouton);
        await attendre();
    });
});
