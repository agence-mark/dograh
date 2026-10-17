/**
 * [.mark] Chantier agents-specialises, lot 13 : la trace d'un appel qui a traversé plusieurs agents, telle
 * qu'on la lit sur la page d'un appel.
 *
 * ⛔ Ce qu'on prouve : la carte « Agents de l'appel » est MONTÉE sur la vraie page d'un appel (celle que
 * rend Next, pas seulement un composant isolé), elle lit les deux formes de ``nodes_visited`` (la liste de
 * noms d'aujourd'hui, les entrées ``{ agent, etape }`` du lot 7 et leur champ ``parcours``), elle dit chaque
 * passation et chaque transfert vers un humain, et un appel d'un agent seul garde la page d'avant.
 * Les entrées de test sont ce que les moteurs écrivent (``tracer_passation``, ``transferts_humains``).
 */
import { cleanup, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import type React from "react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { FenetreDuRun } from "../fenetre-du-run/FenetreDuRun";
import type { AnalyseDuRun } from "../fenetre-du-run/types";
import { FournisseurLangue } from "../langue/langue";
import { lireLaTrace } from "./lire-trace";

const enFrancais = (ui: React.ReactElement) => render(<FournisseurLangue>{ui}</FournisseurLangue>);

const { lireAnalyse, lireRun, lireAgent, lireAgents } = vi.hoisted(() => ({
    lireAnalyse: vi.fn(),
    lireRun: vi.fn(),
    lireAgent: vi.fn(),
    lireAgents: vi.fn(),
}));

vi.mock("@/client", () => ({
    getWorkflowRunAnalyseApiV1WorkflowWorkflowIdRunsRunIdAnalyseGet: (...a: unknown[]) => lireAnalyse(...a),
}));
vi.mock("@/client/sdk.gen", async (importOriginal) => (await import("../sdk-factice")).sdkFactice(await importOriginal(), {
    getWorkflowRunApiV1WorkflowWorkflowIdRunsRunIdGet: (...a: unknown[]) => lireRun(...a),
    getWorkflowApiV1WorkflowFetchWorkflowIdGet: (...a: unknown[]) => lireAgent(...a),
    getWorkflowsApiV1WorkflowFetchGet: (...a: unknown[]) => lireAgents(...a),
}));
vi.mock("@/lib/files", () => ({ getSignedUrl: vi.fn(async () => null), downloadFile: vi.fn() }));
vi.mock("sonner", () => ({ toast: { error: vi.fn(), success: vi.fn() } }));
vi.mock("posthog-js", () => ({ default: { capture: vi.fn() } }));
vi.mock("next/navigation", () => ({
    useParams: () => ({ workflowId: "34", runId: "967" }),
    useRouter: () => ({ push: vi.fn(), replace: vi.fn(), back: vi.fn() }),
    usePathname: () => "/workflow/34/run/967",
}));
const AUTH = { isAuthenticated: true, loading: false, user: { id: "u-1" } };
vi.mock("@/lib/auth", () => ({ useAuth: () => AUTH }));
vi.mock("@/hooks/useOrganizationTimezone", () => ({ useOrganizationTimezone: () => "Europe/Paris" }));
vi.mock("@/app/workflow/WorkflowLayout", () => ({
    default: ({ children }: { children: React.ReactNode }) => <div>{children}</div>,
}));
vi.mock("@/components/onboarding/OnboardingTooltip", () => ({ OnboardingTooltip: () => null }));

const NOMS = new Map([
    [1, "Principal"],
    [3, "Spécialisé un"],
]);

const ANALYSE_VIDE = {
    version: 1,
    run_id: 967,
    summary: { status: "ok", agent_id: 34, definition_id: 1, channel: "browser", duration_secs: 10, disposition: null, cost: { status: "not_captured" }, version: { status: "not_captured" }, incident_count: 0 },
    latency: { status: "not_captured" },
    providers: { status: "not_captured" },
    reading_modules: { status: "not_captured" },
    record: { status: "not_captured" },
    path: { status: "not_captured" },
    conversation: { status: "not_captured" },
    incidents: { status: "ok", items: [] },
} as unknown as AnalyseDuRun;

const run = (gathered_context: Record<string, unknown>) => ({
    data: { id: 967, mode: "smallwebrtc", is_completed: true, gathered_context, logs: null },
});

const monterLaPage = async (gathered: Record<string, unknown>) => {
    lireRun.mockResolvedValue(run(gathered));
    lireAgent.mockResolvedValue({ data: { name: "essai" } });
    lireAnalyse.mockResolvedValue({ data: ANALYSE_VIDE });
    lireAgents.mockResolvedValue({
        data: [
            { id: 1, name: "Principal" },
            { id: 3, name: "Spécialisé un" },
        ],
    });
    const { default: PageDuRun } = await import("@/app/workflow/[workflowId]/run/[runId]/page");
    enFrancais(<PageDuRun />);
    await waitFor(() => expect(screen.getByTestId("fenetre-du-run")).toBeTruthy());
};

const texte = (element: Element) => (element.textContent ?? "").replace(/\s+/g, " ");

beforeEach(() => {
    lireAnalyse.mockReset();
    lireRun.mockReset();
    lireAgent.mockReset();
    lireAgents.mockReset();
});
afterEach(cleanup);

describe("[.mark] lire la trace (pur)", () => {
    it("un appel d'un agent seul ne donne rien : sa page reste celle d'avant", () => {
        expect(lireLaTrace({ nodes_visited: ["accueil", "fin"] }, NOMS)).toBeNull();
        expect(lireLaTrace({}, NOMS)).toBeNull();
        expect(lireLaTrace(null)).toBeNull();
        expect(lireLaTrace({ passations: [], transferts_humains: [] })).toBeNull();
    });

    it("lit les passations avec les noms des agents (un identifiant inconnu s'écrit #n)", () => {
        const trace = lireLaTrace(
            {
                passations: [
                    { de: 1, vers: 3, raison: "demande", refusee: false, issue: "completed" },
                    { de: 3, vers: 1, raison: "retour", refusee: false, issue: "completed" },
                    { de: 1, vers: 99, raison: "x", refusee: true, motif_refus: "plafond" },
                ],
            },
            NOMS,
        )!;
        expect(trace.passations.map((p) => [p.de, p.vers, p.refusee, p.motifRefus])).toEqual([
            ["Principal", "Spécialisé un", false, null],
            ["Spécialisé un", "Principal", false, null],
            ["Principal", "#99", true, "plafond"],
        ]);
        expect(trace.agents).toEqual(["Principal", "Spécialisé un", "#99"]);
    });

    it("lit la liste de NOMS d'aujourd'hui sans rien en tirer de plus (le parcours reste dans la section Parcours)", () => {
        const trace = lireLaTrace({ nodes_visited: ["a", "b"], passations: [{ de: 1, vers: 3 }] }, NOMS)!;
        expect(trace.parcours).toEqual([]);
        expect(trace.agents).toEqual(["Principal", "Spécialisé un"]);
    });

    it("lit les ENTRÉES { agent, etape } dans l'ordre : un segment par agent traversé, même nom d'étape compris", () => {
        const trace = lireLaTrace(
            {
                nodes_visited: [
                    { agent: "Principal", etape: "Qualification" },
                    { agent: "Spécialisé un", etape: "Qualification" },
                    { agent: "Spécialisé un", etape: "Coordonnées" },
                    { agent: "Principal", etape: "Fin" },
                ],
            },
            NOMS,
        )!;
        expect(trace.parcours).toEqual([
            { agent: "Principal", etapes: ["Qualification"] },
            { agent: "Spécialisé un", etapes: ["Qualification", "Coordonnées"] },
            { agent: "Principal", etapes: ["Fin"] },
        ]);
        expect(trace.agents).toEqual(["Principal", "Spécialisé un"]);
    });

    it("lit un agent écrit par son identifiant dans les entrées, et le champ parcours écrit par le moteur", () => {
        const trace = lireLaTrace(
            { nodes_visited: [{ agent: 3, etape: "Qualification" }], parcours: "Spécialisé un › Qualification" },
            NOMS,
        )!;
        expect(trace.parcours[0].agent).toBe("Spécialisé un");
        expect(trace.parcoursEcrit).toEqual(["Spécialisé un › Qualification"]);
        expect(lireLaTrace({ parcours: ["a › b", "c › d"] })!.parcoursEcrit).toEqual(["a › b", "c › d"]);
    });

    it("lit les transferts vers un humain, et les ignore s'ils sont illisibles", () => {
        const trace = lireLaTrace(
            { transferts_humains: [{ le: "2026-10-16T08:00:00Z", cible: "numero:***1234", issue: "repondeur" }, "bruit", null] },
            NOMS,
        )!;
        expect(trace.transferts).toEqual([{ le: "2026-10-16T08:00:00Z", cible: "numero:***1234", issue: "repondeur" }]);
    });

    it("lit les travaux de fond (lot 4 d'orchestrateur-trois-cerveaux), seuls ils suffisent à montrer la carte", () => {
        const trace = lireLaTrace(
            { travaux: [{ agent: 7, demande: "Cherche un creneau", statut: "fait", duree_ms: 2400, jetons_entree: 120, jetons_sortie: 30, resultat: "Jeudi 10 h", remis: true }, "bruit"] },
            NOMS,
        )!;
        expect(trace.travaux).toHaveLength(1);
        expect(trace.travaux[0]).toMatchObject({ demande: "Cherche un creneau", statut: "fait", dureeMs: 2400, jetonsEntree: 120, jetonsSortie: 30, resultat: "Jeudi 10 h", remis: true });
        expect(lireLaTrace({ travaux: [] })).toBeNull();
    });
});

describe("[.mark] la carte « Agents de l'appel » sur la page d'un appel", () => {
    it("est MONTÉE sur la vraie page : agents, parcours, passations et transferts", async () => {
        await monterLaPage({
            passations: [
                { de: 1, vers: 3, raison: "demande", refusee: false, issue: "completed" },
                { de: 3, vers: 1, raison: "retour", refusee: false, issue: "completed" },
                { de: 1, vers: 3, raison: "demande", refusee: true, motif_refus: "plafond" },
            ],
            transferts_humains: [{ le: "2026-10-16T08:00:00Z", cible: "numero:***1234", issue: "repondeur" }],
            nodes_visited: [
                { agent: "Principal", etape: "Qualification" },
                { agent: "Spécialisé un", etape: "Qualification" },
                { agent: "Spécialisé un", etape: "Coordonnées" },
                { agent: "Principal", etape: "Fin" },
            ],
        });
        const carte = await screen.findByText("Agents de l'appel").then((el) => el.closest("[data-carte]") as HTMLElement);
        expect(carte).not.toBeNull();
        await waitFor(() => expect(within(carte).getAllByText("Spécialisé un").length).toBeGreaterThan(0));
        const agents = [...carte.querySelectorAll("[data-agent-de-l-appel]")].map((e) => e.getAttribute("data-agent-de-l-appel"));
        expect(agents).toEqual(["Principal", "Spécialisé un"]);
        const lignes = [...carte.querySelectorAll("[data-ligne-de-parcours]")].map(texte);
        expect(lignes).toEqual(["Principal › Qualification", "Spécialisé un › Qualification › Coordonnées", "Principal › Fin"]);
        const passations = [...carte.querySelectorAll("[data-passation]")].map(texte);
        expect(passations).toHaveLength(3);
        expect(passations[0]).toContain("Principal");
        expect(passations[0]).toContain("Spécialisé un");
        expect(passations[0]).toContain("faite");
        expect(passations[2]).toContain("refusée (plafond de passations atteint)");
        expect(texte(carte.querySelector('[data-transfert-humain="repondeur"]')!)).toContain("répondeur");
    });

    it("montre le parcours écrit par le moteur quand il y est", async () => {
        await monterLaPage({
            passations: [{ de: 1, vers: 3, raison: "demande", refusee: false, issue: "completed" }],
            nodes_visited: [{ agent: "Principal", etape: "Qualification" }],
            parcours: "Principal › Qualification › Passé à Spécialisé un",
        });
        const carte = (await screen.findByText("Agents de l'appel")).closest("[data-carte]") as HTMLElement;
        expect([...carte.querySelectorAll("[data-ligne-de-parcours]")].map(texte)).toEqual([
            "Principal › Qualification › Passé à Spécialisé un",
        ]);
    });

    it("ne montre rien pour un appel d'un agent seul : la page est celle d'avant", async () => {
        await monterLaPage({ nodes_visited: ["accueil", "fin"], call_disposition: "ok" });
        expect(screen.queryByText("Agents de l'appel")).toBeNull();
        expect(document.querySelector('[data-carte="agents-de-l-appel"]')).toBeNull();
        // Les autres blocs de la page sont là.
        expect(screen.getByTestId("fenetre-du-run")).toBeTruthy();
        expect(screen.getByText("Mesures de l'appel")).toBeTruthy();
    });

    it("compte les étapes visitées dans « Nodes Visited » pour les deux formes", async () => {
        await monterLaPage({
            nodes_visited: [
                { agent: "Principal", etape: "Qualification" },
                { agent: "Spécialisé un", etape: "Qualification" },
            ],
            passations: [{ de: 1, vers: 3, refusee: false }],
        });
        const metrique = (await screen.findByText("Nodes Visited")).parentElement as HTMLElement;
        expect(texte(metrique)).toContain("2");
    });
});

describe("[.mark] la section Parcours de la fenêtre du run lit aussi les entrées", () => {
    it("écrit « agent › étape » pour une entrée et le nom seul pour une étape d'aujourd'hui", async () => {
        lireAnalyse.mockResolvedValue({
            data: {
                ...ANALYSE_VIDE,
                path: {
                    status: "ok",
                    steps: [{ agent: "Principal", etape: "Qualification" }, { agent: "Spécialisé un", etape: "Coordonnées" }, "Fin"],
                    transitions: [],
                    tools: [],
                },
            },
        });
        enFrancais(<FenetreDuRun workflowId={34} runId={967} />);
        await screen.findByTestId("fenetre-du-run");
        const bloc = screen.getByTestId("bloc-path");
        fireEvent.click(within(bloc).getAllByRole("button")[0]);
        expect(texte(bloc)).toContain("Principal › Qualification → Spécialisé un › Coordonnées → Fin");
    });
});
