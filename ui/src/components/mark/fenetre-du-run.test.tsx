/**
 * [.mark] The run window (chantier langwatch-et-fenetre-du-run, lot 1), as Evan and Pierre see it.
 *
 * The questions this file answers:
 *
 *     Does the window show every block from the server's analysis, turn by turn latency first,
 *     with a turn the measure leaves out SHOWN with its reason? Does a block the server could not
 *     compute say "unavailable", and missing data "not captured", instead of an empty card? Does
 *     a failed request say so? And is the window MOUNTED on the run's page, reached by the real
 *     page component, not only rendered by a test?
 */

import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import type React from "react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { FenetreDuRun } from "./fenetre-du-run/FenetreDuRun";
import type { AnalyseDuRun } from "./fenetre-du-run/types";
import { FournisseurLangue } from "./langue/langue";

const enFrancais = (ui: React.ReactElement) => render(<FournisseurLangue>{ui}</FournisseurLangue>);

const { lireAnalyse, lireRun, lireAgent } = vi.hoisted(() => ({
    lireAnalyse: vi.fn(),
    lireRun: vi.fn(),
    lireAgent: vi.fn(),
}));

vi.mock("@/client", () => ({
    getWorkflowRunAnalyseApiV1WorkflowWorkflowIdRunsRunIdAnalyseGet: (...a: unknown[]) => lireAnalyse(...a),
}));
vi.mock("@/client/sdk.gen", () => ({
    getWorkflowRunApiV1WorkflowWorkflowIdRunsRunIdGet: (...a: unknown[]) => lireRun(...a),
    getWorkflowApiV1WorkflowFetchWorkflowIdGet: (...a: unknown[]) => lireAgent(...a),
}));
vi.mock("@/lib/files", () => ({ getSignedUrl: vi.fn(async () => null), downloadFile: vi.fn() }));
vi.mock("sonner", () => ({ toast: { error: vi.fn(), success: vi.fn() } }));
vi.mock("posthog-js", () => ({ default: { capture: vi.fn() } }));
vi.mock("next/navigation", () => ({
    useParams: () => ({ workflowId: "34", runId: "967" }),
    useRouter: () => ({ push: vi.fn(), replace: vi.fn(), back: vi.fn() }),
    usePathname: () => "/workflow/34/run/967",
}));
// One stable object: the page re-fetches whenever `auth` changes identity.
const AUTH = { isAuthenticated: true, loading: false, user: { id: "u-1" } };
vi.mock("@/lib/auth", () => ({ useAuth: () => AUTH }));
vi.mock("@/hooks/useOrganizationTimezone", () => ({ useOrganizationTimezone: () => "Europe/Paris" }));
vi.mock("@/app/workflow/WorkflowLayout", () => ({
    default: ({ children }: { children: React.ReactNode }) => <div>{children}</div>,
}));
vi.mock("@/components/onboarding/OnboardingTooltip", () => ({ OnboardingTooltip: () => null }));

const ANALYSE: AnalyseDuRun = {
    version: 1,
    run_id: 967,
    summary: {
        status: "ok",
        agent_id: 34,
        definition_id: 144,
        channel: "browser",
        duration_secs: 158,
        disposition: "sav_urgent",
        cost: { status: "not_captured" },
        version: { app_version: "1.0.0", commit: "c3ac9aa65c0e5c47", version_number: 10, definition_status: "published" },
        incident_count: 1,
    },
    latency: {
        status: "ok",
        turns: [
            {
                turn: 2,
                step: "accueil",
                measured: true,
                not_measured_reason: null,
                end_of_turn_wait_secs: 0.4,
                transcription_secs: 0.3,
                passes: [
                    { secs: 1.2, after: "note" },
                    { secs: 0.9, after: "reply" },
                ],
                voice_secs: 0.12,
                silence_secs: 2.3,
                slow: false,
                step_change: false,
            },
            {
                turn: 9,
                step: "coordonnees",
                measured: false,
                not_measured_reason: "no_reply",
                end_of_turn_wait_secs: null,
                transcription_secs: null,
                passes: [],
                voice_secs: null,
                silence_secs: null,
                slow: false,
                step_change: false,
            },
        ],
        stats: {
            measured_turns: 1,
            total_turns: 2,
            median_silence_secs: 2.3,
            worst_silence_secs: 2.3,
            worst_turn: 2,
            share_under_threshold: 0,
            threshold_secs: 0.8,
            median_passes: 2,
        },
    },
    providers: { status: "unavailable", reason: "KeyError" },
    reading_modules: {
        status: "ok",
        modules: ["numbers"],
        items: [
            {
                module: "numbers",
                caller_turn: 5,
                step: "coordonnees",
                heard: "vingt-trois quatre-vingts",
                result: "23080",
                kind: "autre",
                status: null,
                by_sound: null,
                proposals: [],
            },
        ],
    },
    record: {
        status: "ok",
        fields: [
            {
                name: "nom",
                value: "Testeur",
                empty: false,
                declared: true,
                sure: true,
                source: "outil",
                written_at_caller_turn: 4,
                history: [],
            },
            {
                name: "commune",
                value: null,
                empty: true,
                declared: true,
                sure: null,
                source: null,
                written_at_caller_turn: null,
                history: [],
            },
        ],
        refusals: [],
    },
    path: { status: "not_captured" },
    conversation: {
        status: "ok",
        lines: [{ turn: 2, speaker: "caller", text: "Bonjour, un devis", start_secs: 8.1, end_secs: 11.4 }],
    },
    incidents: {
        status: "ok",
        items: [{ turn: 4, kind: "model_rate_limited", fatal: false, processor: "Mistral", detail: "RateLimitError" }],
    },
};

const texte = (element: HTMLElement) => (element.textContent ?? "").replace(/\s+/g, " ");

const ouvrir = (testId: string) => {
    const bloc = screen.getByTestId(testId);
    fireEvent.click(within(bloc).getAllByRole("button")[0]);
    return bloc;
};

describe("Fenêtre du run", () => {
    beforeEach(() => {
        lireAnalyse.mockReset();
        lireRun.mockReset();
        lireAgent.mockReset();
    });

    it("demande l'analyse du bon run et montre la latence tour par tour, tour écarté compris", async () => {
        lireAnalyse.mockResolvedValue({ data: ANALYSE });
        enFrancais(<FenetreDuRun workflowId={34} runId={967} recordingKey="rec/967.wav" />);
        await screen.findByTestId("fenetre-du-run");
        expect(lireAnalyse).toHaveBeenCalledWith({ path: { workflow_id: 34, run_id: 967 } });
        const tours = screen.getAllByTestId("tour-de-latence");
        expect(tours).toHaveLength(2);
        expect(texte(tours[0])).toContain("2.30 s");
        expect(texte(tours[1])).toContain("non mesuré : l'agent n'a pas répondu");
        expect(texte(screen.getByTestId("bloc-latency"))).toContain("1 tours mesurés sur 2");
        expect(texte(screen.getByTestId("fenetre-resume"))).toContain("1 incident(s) sur cet appel");
        expect(texte(screen.getByTestId("fenetre-version"))).toContain("commit déployé : c3ac9aa6");
        expect(texte(screen.getByTestId("fenetre-version"))).toContain("version de l'agent : 10 (published)");
    });

    it("dit « indisponible » pour un bloc en échec et « non capté » pour une donnée absente", async () => {
        lireAnalyse.mockResolvedValue({ data: ANALYSE });
        enFrancais(<FenetreDuRun workflowId={34} runId={967} />);
        await screen.findByTestId("fenetre-du-run");
        expect(texte(ouvrir("bloc-providers"))).toContain("Indisponible : le serveur n'a pas pu calculer ce bloc");
        expect(texte(ouvrir("bloc-path"))).toContain("Non capté pour ce run.");
    });

    it("montre les modules, la fiche avec sa provenance, et les champs restés vides", async () => {
        lireAnalyse.mockResolvedValue({ data: ANALYSE });
        enFrancais(<FenetreDuRun workflowId={34} runId={967} />);
        await screen.findByTestId("fenetre-du-run");
        ouvrir("bloc-reading-modules");
        expect(texte(screen.getByTestId("element-de-module"))).toContain("vingt-trois quatre-vingts");
        expect(texte(screen.getByTestId("element-de-module"))).toContain("23080");
        ouvrir("bloc-record");
        const [nom, commune] = screen.getAllByTestId("champ-de-fiche");
        expect(texte(nom)).toContain("Testeur");
        expect(texte(nom)).toContain("outil");
        expect(texte(commune)).toContain("vide");
        ouvrir("bloc-incidents");
        expect(texte(screen.getByTestId("incident"))).toContain("Modèle refusé : quota");
        ouvrir("bloc-conversation");
        expect(texte(screen.getByTestId("ligne-de-conversation"))).toContain("Bonjour, un devis");
    });

    it("dit qu'une requête refusée a échoué, au lieu d'une fenêtre vide", async () => {
        lireAnalyse.mockResolvedValue({ error: { detail: "Workflow run not found" } });
        enFrancais(<FenetreDuRun workflowId={34} runId={967} />);
        expect(texte(await screen.findByRole("alert"))).toContain("Analyse du run indisponible : Workflow run not found");
    });

    it("est MONTÉE sur la page du run : la vraie page la rend pour un run terminé", async () => {
        lireRun.mockResolvedValue({
            data: { id: 967, mode: "smallwebrtc", is_completed: true, gathered_context: {}, logs: null },
        });
        lireAgent.mockResolvedValue({ data: { name: "essai" } });
        lireAnalyse.mockResolvedValue({ data: ANALYSE });
        const { default: PageDuRun } = await import("@/app/workflow/[workflowId]/run/[runId]/page");
        enFrancais(<PageDuRun />);
        await waitFor(() => expect(screen.getByTestId("fenetre-du-run")).toBeTruthy());
        expect(lireAnalyse).toHaveBeenCalledWith({ path: { workflow_id: 34, run_id: 967 } });
    });
});


describe("Fenêtre du run : refus du modèle", () => {
    it("dit les refus, les nouvelles tentatives silencieuses et le temps perdu", async () => {
        lireAnalyse.mockResolvedValue({
            data: {
                ...ANALYSE,
                providers: {
                    status: "ok",
                    model: { provider: "mistral", model: "mistral-large-2512", usage: [] },
                    model_requests: { refused: 2, retries: 2, lost_secs: 1.4, by_status: { "429": 2 } },
                },
            },
        });
        enFrancais(<FenetreDuRun workflowId={34} runId={967} />);
        await screen.findByTestId("fenetre-du-run");
        ouvrir("bloc-providers");
        expect(texte(screen.getByTestId("requetes-du-modele"))).toContain(
            "Refus du modèle : 2 · nouvelles tentatives silencieuses : 2 · temps perdu : 1.40 s",
        );
    });
});


describe("Fenêtre du run : coupures, interruptions, relances", () => {
    it("dit les coupures par brique et marque interruptions et relances dans la conversation", async () => {
        lireAnalyse.mockResolvedValue({
            data: {
                ...ANALYSE,
                providers: {
                    status: "ok",
                    connections: { transcription: { disconnections: 1, errors: 0 } },
                },
                conversation: {
                    status: "ok",
                    lines: [],
                    marks: [
                        { turn: 3, kind: "caller_interrupted", at_secs: 12.3 },
                        { turn: 6, kind: "idle_reminder", at_secs: 40 },
                    ],
                },
            },
        });
        enFrancais(<FenetreDuRun workflowId={34} runId={967} />);
        await screen.findByTestId("fenetre-du-run");
        ouvrir("bloc-providers");
        expect(texte(screen.getByTestId("connexions-des-fournisseurs"))).toContain("Transcription : 1 coupure(s), 0 erreur(s)");
        ouvrir("bloc-conversation");
        const marques = texte(screen.getByTestId("marques-de-conversation"));
        expect(marques).toContain("12.3 s · Tour 3 · l'appelant a coupé l'agent");
        expect(marques).toContain("relance d'inactivité");
    });
});


describe("Fenêtre du run : silence réellement entendu", () => {
    it("montre la médiane et le pire, ou dit « non capté »", async () => {
        lireAnalyse.mockResolvedValue({
            data: {
                ...ANALYSE,
                latency: { ...ANALYSE.latency, perceived: { status: "ok", count: 7, median_secs: 1.8, worst_secs: 3.1 } },
            },
        });
        const { unmount } = enFrancais(<FenetreDuRun workflowId={34} runId={967} />);
        await screen.findByTestId("fenetre-du-run");
        expect(texte(screen.getByTestId("silence-entendu"))).toContain("médiane 1.80 s · pire 3.10 s · 7 réponses");
        unmount();
        lireAnalyse.mockResolvedValue({ data: ANALYSE });
        enFrancais(<FenetreDuRun workflowId={34} runId={967} />);
        await screen.findByTestId("fenetre-du-run");
        expect(texte(screen.getByTestId("silence-entendu"))).toContain("non capté");
    });
});


describe("Fenêtre du run : coût estimé", () => {
    it("dit le coût, son tarif daté et ce qui n'a pas de prix ; sinon « non capté »", async () => {
        lireAnalyse.mockResolvedValue({
            data: {
                ...ANALYSE,
                summary: {
                    ...ANALYSE.summary,
                    cost: {
                        status: "ok",
                        currency: "USD",
                        total: 0.1234,
                        partial: true,
                        rate_dates: ["2026-10-01"],
                        unpriced: [{ component: "tts", model: "eleven_flash_v2_5" }],
                    },
                },
            },
        });
        const { unmount } = enFrancais(<FenetreDuRun workflowId={34} runId={967} />);
        await screen.findByTestId("fenetre-du-run");
        expect(texte(screen.getByTestId("fenetre-cout"))).toContain(
            "Coût estimé : 0.1234 USD au tarif du 01/10 · partiel : pas de prix pour eleven_flash_v2_5",
        );
        unmount();
        lireAnalyse.mockResolvedValue({ data: ANALYSE });
        enFrancais(<FenetreDuRun workflowId={34} runId={967} />);
        await screen.findByTestId("fenetre-du-run");
        expect(texte(screen.getByTestId("fenetre-cout"))).toContain("Coût estimé : non capté");
    });
});
