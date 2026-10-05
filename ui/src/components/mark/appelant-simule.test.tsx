/**
 * [.mark] The simulated caller on screen (chantier langwatch-et-fenetre-du-run, lot 3, L11, L18, Q3),
 * as Evan and Pierre see it.
 *
 * The questions this file answers:
 *
 *     Is the « Simulated caller » tab MOUNTED in Dograh's real tester panel? Can one pick scenarios,
 *     read the estimated cost and the cap, run a series, follow it and stop it? Do the modals
 *     (scenarios, settings, report) work on a copy, name their faults and send what was typed?
 *     Are keys picked among saved credentials, never typed? Does the run window show the
 *     simulation's verdict?
 */

import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import type React from "react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { WorkflowTesterPanel } from "@/app/workflow/[workflowId]/components/WorkflowTesterPanel";

import { AppelantSimule, estimation } from "./appelant-simule/AppelantSimule";
import { bilanDeSerie, exportCsv, ModaleRapportSeries } from "./appelant-simule/ModaleRapportSeries";
import { ModaleReglagesAppelantSimule } from "./appelant-simule/ModaleReglagesAppelantSimule";
import { ModaleScenarios } from "./appelant-simule/ModaleScenarios";
import { FenetreDuRun } from "./fenetre-du-run/FenetreDuRun";
import { FournisseurLangue } from "./langue/langue";

const m = vi.hoisted(() => ({
    getScenarios: vi.fn(),
    saveScenarios: vi.fn(),
    getReglages: vi.fn(),
    saveReglages: vi.fn(),
    getSeries: vi.fn(),
    getRapport: vi.fn(),
    lancer: vi.fn(),
    arreter: vi.fn(),
    credentials: vi.fn(),
    analyse: vi.fn(),
}));

vi.mock("@/client", () => ({
    getScenariosSimulesApiV1AppelSimuleAgentsWorkflowIdScenariosGet: (...a: unknown[]) => m.getScenarios(...a),
    saveScenariosSimulesApiV1AppelSimuleAgentsWorkflowIdScenariosPut: (...a: unknown[]) => m.saveScenarios(...a),
    getReglagesAppelantSimuleApiV1AppelSimuleReglagesGet: (...a: unknown[]) => m.getReglages(...a),
    saveReglagesAppelantSimuleApiV1AppelSimuleReglagesPut: (...a: unknown[]) => m.saveReglages(...a),
    getSeriesSimuleesApiV1AppelSimuleSeriesGet: (...a: unknown[]) => m.getSeries(...a),
    getRapportSerieApiV1AppelSimuleSeriesSerieIdGet: (...a: unknown[]) => m.getRapport(...a),
    lancerSerieSimuleeApiV1AppelSimuleAgentsWorkflowIdSeriesPost: (...a: unknown[]) => m.lancer(...a),
    arreterSerieSimuleeApiV1AppelSimuleSeriesSerieIdArreterPost: (...a: unknown[]) => m.arreter(...a),
    listCredentialsApiV1CredentialsGet: (...a: unknown[]) => m.credentials(...a),
    getWorkflowRunAnalyseApiV1WorkflowWorkflowIdRunsRunIdAnalyseGet: (...a: unknown[]) => m.analyse(...a),
}));
vi.mock("@/client/sdk.gen", () => ({ createWorkflowRunApiV1WorkflowWorkflowIdRunsPost: vi.fn() }));
vi.mock("sonner", () => ({ toast: { error: vi.fn(), success: vi.fn() } }));
vi.mock("posthog-js", () => ({ default: { capture: vi.fn() } }));
const AUTH = { isAuthenticated: true, loading: false, user: { id: "u-1" }, getAccessToken: async () => "jeton" };
vi.mock("@/lib/auth", () => ({ useAuth: () => AUTH }));
vi.mock("@/context/OnboardingContext", () => ({ useOnboarding: () => ({ markActionCompleted: vi.fn() }) }));
vi.mock("@/components/onboarding/OnboardingTooltip", () => ({ OnboardingTooltip: () => null }));

const enFrancais = (ui: React.ReactElement) => render(<FournisseurLangue>{ui}</FournisseurLangue>);
const texte = (el: Element) => (el.textContent ?? "").replace(/\s+/g, " ").trim();
const bouton = (nom: string) => screen.getByRole("button", { name: nom }) as HTMLButtonElement;

const SCENARIO = {
    id: "s1",
    workflow_id: 34,
    nom: "Panne urgente",
    role: "Un particulier dont la chaudière est en panne.",
    consigne: "",
    comportements: { presse: true, coupe_la_parole: false, hesite: false, se_tait: false },
    criteres: ["L'agent demande le nom"],
    tours_max: 12,
    renvoi: "refuse",
    latence_max_s: null,
};
const REGLAGES = {
    format: "appelant-simule-mark",
    version: 1,
    appelant: { modele: "mistral/mistral-small-latest", identifiant: null, consigne: "Joue un appelant.", temperature: 0.5 },
    juge: { modele: "mistral/mistral-small-latest", identifiant: null, consigne: "Juge l'appel.", temperature: 0 },
    voix: { voix: "", identifiant: null },
    simultanes: 1,
    taille_max_serie: 2,
    plafond: 5,
};
const SERIE = {
    id: "serie-1",
    workflow_id: 34,
    lancee_le: "2026-10-05T18:00:00Z",
    lancee_par: 3,
    etat: "en_cours",
    plafond: 5,
    devise: "USD",
    cout: 0.12,
    cout_partiel: true,
    appels: [
        { scenario_id: "s1", scenario_nom: "Panne urgente", run_id: 990, etat: "joue", reussi: true, cout: 0.12 },
        { scenario_id: "s2", scenario_nom: "Devis", run_id: null, etat: "a_jouer", reussi: null, cout: null },
    ],
};
const RAPPORT = {
    serie: SERIE,
    appels: SERIE.appels.map((a) => ({
        ...a,
        erreur: null,
        resultat:
            a.run_id === 990
                ? {
                      success: true,
                      passed_criteria: ["L'agent demande le nom"],
                      failed_criteria: ["L'agent propose un créneau"],
                      worst_silence_secs: 2.5,
                      median_silence_secs: 1.2,
                      incidents: 1,
                  }
                : null,
    })),
};

beforeEach(() => {
    vi.clearAllMocks();
    m.getScenarios.mockResolvedValue({ data: [SCENARIO, { ...SCENARIO, id: "s2", nom: "Devis" }, { ...SCENARIO, id: "s3", nom: "Horaires" }] });
    m.getReglages.mockResolvedValue({ data: REGLAGES });
    m.getSeries.mockResolvedValue({ data: [] });
    m.getRapport.mockResolvedValue({ data: RAPPORT });
    m.lancer.mockResolvedValue({ data: SERIE });
    m.arreter.mockResolvedValue({ data: { stopping: true } });
    m.saveScenarios.mockResolvedValue({ data: [] });
    m.saveReglages.mockResolvedValue({ data: REGLAGES });
    m.credentials.mockResolvedValue({
        data: [
            { uuid: "c-mistral", name: "Mistral organisation 2", description: null },
            { uuid: "c-eleven", name: "ElevenLabs", description: null },
        ],
    });
});

describe("[.mark] the « Simulated caller » tab, mounted in Dograh's tester panel", () => {
    it("is a third tab next to audio and chat, and opens the simulated caller", async () => {
        render(<WorkflowTesterPanel workflowId={34} disabled={false} disabledReason={null} />);
        const onglet = await screen.findByRole("tab", { name: /Simulated caller/ });
        fireEvent.mouseDown(onglet);
        await screen.findByTestId("appelant-simule");
        await screen.findByText("Panne urgente");
    });
});

describe("[.mark] running a series", () => {
    it("shows the cap before the first call, runs the picked scenarios, follows and stops the series", async () => {
        render(<AppelantSimule workflowId={34} />);
        await screen.findByText("Panne urgente");
        expect(texte(screen.getByTestId("estimation"))).toContain("unknown until the first call · cap 5");
        expect(bouton("Run 0 call(s)").disabled).toBe(true);

        fireEvent.click(screen.getByLabelText("Panne urgente"));
        fireEvent.click(screen.getByLabelText("Devis"));
        m.getSeries.mockResolvedValue({ data: [SERIE] });
        fireEvent.click(bouton("Run 2 call(s)"));
        await waitFor(() => expect(m.lancer).toHaveBeenCalledTimes(1));
        expect(m.lancer.mock.calls[0][0]).toEqual({ path: { workflow_id: 34 }, body: { scenario_ids: ["s1", "s2"] } });

        const suivie = await screen.findByTestId("serie-suivie");
        await waitFor(() => expect(within(suivie).getAllByTestId("appel-suivi")).toHaveLength(2));
        const [premier] = within(suivie).getAllByTestId("appel-suivi");
        expect([...premier.children].map(texte)).toEqual(["✓", "Panne urgente", "played", "run window"]);
        expect(premier.querySelector("a")?.getAttribute("href")).toBe("/workflow/34/run/990");

        fireEvent.click(bouton("Stop"));
        await waitFor(() => expect(m.arreter).toHaveBeenCalledWith({ path: { serie_id: "serie-1" } }));
    });

    it("refuses a series larger than the settings allow", async () => {
        render(<AppelantSimule workflowId={34} />);
        await screen.findByText("Horaires");
        for (const nom of ["Panne urgente", "Devis", "Horaires"]) fireEvent.click(screen.getByLabelText(nom));
        expect(screen.getByText("A series is 2 calls at most.")).toBeTruthy();
        expect(bouton("Run 3 call(s)").disabled).toBe(true);
    });

    it("estimates from the calls already played", () => {
        expect(estimation([SERIE as never], 4)).toBe(0.48);
        expect(estimation([], 4)).toBeNull();
    });

    it("says it in French", async () => {
        enFrancais(<AppelantSimule workflowId={34} />);
        await screen.findByText("Panne urgente");
        expect(texte(screen.getByTestId("estimation"))).toContain("Coût estimé : inconnu avant le premier appel · plafond 5");
    });
});

describe("[.mark] the scenario library (L10, L18)", () => {
    it("names the faults, then sends the agent's scenarios cleaned", async () => {
        const fermer = vi.fn();
        render(<ModaleScenarios workflowId={34} ouverte onFermer={fermer} />);
        await screen.findByTestId("liste-scenarios");
        fireEvent.click(bouton("New scenario"));
        expect(texte(screen.getByTestId("fautes-scenarios"))).toContain("New scenario: caller role missing");
        expect(bouton("Save").disabled).toBe(true);

        fireEvent.change(screen.getByLabelText("Caller role"), { target: { value: "Quelqu'un qui demande les horaires." } });
        fireEvent.change(screen.getByLabelText("Criterion 1"), { target: { value: "  L'agent donne les horaires  " } });
        fireEvent.click(bouton("Add a criterion"));
        await waitFor(() => expect(bouton("Save").disabled).toBe(false));
        fireEvent.click(bouton("Save"));
        await waitFor(() => expect(m.saveScenarios).toHaveBeenCalledTimes(1));
        const envoye = m.saveScenarios.mock.calls[0][0];
        expect(envoye.path).toEqual({ workflow_id: 34 });
        expect(envoye.body).toHaveLength(4);
        expect(envoye.body[3]).toMatchObject({
            workflow_id: 34,
            nom: "New scenario",
            criteres: ["L'agent donne les horaires"],
        });
        expect(fermer).toHaveBeenCalledWith(true);
    });

    it("duplicates a scenario under a new name and a new id", async () => {
        render(<ModaleScenarios workflowId={34} ouverte onFermer={vi.fn()} />);
        await screen.findByTestId("liste-scenarios");
        fireEvent.click(bouton("Duplicate Devis"));
        fireEvent.click(bouton("Save"));
        await waitFor(() => expect(m.saveScenarios).toHaveBeenCalledTimes(1));
        const copie = m.saveScenarios.mock.calls[0][0].body[3];
        expect(copie.nom).toBe("Devis (copy)");
        expect(copie.id).not.toBe("s2");
    });
});

describe("[.mark] the simulated caller's settings (L18, Q1 to Q3)", () => {
    it("picks keys among saved credentials, refuses a cap out of bounds, and sends what was set", async () => {
        render(<ModaleReglagesAppelantSimule ouverte onFermer={vi.fn()} />);
        const modele = (await screen.findByLabelText("Model credential (caller and judge)")) as HTMLSelectElement;
        expect([...modele.options].map((o) => o.textContent)).toContain("Mistral organisation 2");
        fireEvent.change(modele, { target: { value: "c-mistral" } });
        fireEvent.change(screen.getByLabelText("ElevenLabs credential (voice and transcription)"), {
            target: { value: "c-eleven" },
        });
        fireEvent.change(screen.getByLabelText("ElevenLabs voice id"), { target: { value: "voix-fr" } });
        fireEvent.change(screen.getByLabelText("Spending cap"), { target: { value: "500" } });
        expect(texte(screen.getByTestId("fautes-appelant-simule"))).toContain("plafond: between 0.01 and 200");
        expect(bouton("Save").disabled).toBe(true);
        fireEvent.change(screen.getByLabelText("Spending cap"), { target: { value: "8" } });
        await waitFor(() => expect(bouton("Save").disabled).toBe(false));
        fireEvent.click(bouton("Save"));
        await waitFor(() => expect(m.saveReglages).toHaveBeenCalledTimes(1));
        const corps = m.saveReglages.mock.calls[0][0].body;
        expect(corps.appelant.identifiant).toBe("c-mistral");
        expect(corps.juge.identifiant).toBe("c-mistral");
        expect(corps.voix).toEqual({ voix: "voix-fr", identifiant: "c-eleven" });
        expect(corps.plafond).toBe(8);
        expect(JSON.stringify(corps)).not.toMatch(/api_key|token/);
    });
});

describe("[.mark] the series report (L18)", () => {
    it("sums up a series and compares two side by side", async () => {
        const autre = { ...RAPPORT, serie: { ...SERIE, id: "serie-0", etat: "terminee", lancee_le: "2026-10-04T18:00:00Z" } };
        m.getSeries.mockResolvedValue({ data: [SERIE, autre.serie] });
        m.getRapport.mockImplementation(({ path }: { path: { serie_id: string } }) =>
            Promise.resolve({ data: path.serie_id === "serie-0" ? autre : RAPPORT }),
        );
        render(<ModaleRapportSeries workflowId={34} ouverte onFermer={vi.fn()} />);
        await screen.findByTestId("rapport-serie");
        fireEvent.change(screen.getByLabelText("Compare with"), { target: { value: "serie-0" } });
        await waitFor(() => expect(screen.getAllByTestId("rapport-serie")).toHaveLength(2));
        const bilan = texte(screen.getAllByTestId("bilan-serie")[0]);
        expect(bilan).toContain("Scenarios passed: 1 / 1");
        expect(bilan).toContain("Criteria met: 1 / 2");
        expect(bilan).toContain("Median latency 1.20 s · worst turn 2.50 s");
        expect(bilan).toContain("Cost 0.12 USD (partial) · cap 5");
    });

    it("exports one CSV line per call, quotes escaped", () => {
        const lignes = exportCsv({
            ...RAPPORT,
            appels: [{ ...RAPPORT.appels[0], scenario_nom: 'Panne "urgente"' }],
        } as never).split("\n");
        expect(lignes).toHaveLength(2);
        expect(lignes[1]).toContain('"Panne ""urgente"""');
        expect(bilanDeSerie(RAPPORT as never).incidents).toBe(1);
    });
});

describe("[.mark] the run window of a simulated call", () => {
    it("shows the scenario, the criteria met and failed, and the judge's reasoning", async () => {
        m.analyse.mockResolvedValue({
            data: {
                version: 1,
                run_id: 990,
                summary: { status: "ok", channel: "simulated", cost: { status: "not_captured" } },
                latency: { status: "not_captured" },
                providers: { status: "not_captured" },
                reading_modules: { status: "not_captured" },
                record: { status: "not_captured" },
                path: { status: "not_captured" },
                conversation: { status: "not_captured" },
                incidents: { status: "ok", items: [] },
                simulation: {
                    scenario_nom: "Panne urgente",
                    resultat: {
                        success: false,
                        error: null,
                        reasoning: "Le créneau n'a pas été proposé.",
                        passed_criteria: ["L'agent demande le nom"],
                        failed_criteria: ["L'agent propose un créneau"],
                        messages: [],
                        worst_silence_secs: 2.5,
                        median_silence_secs: 1.2,
                        incidents: 0,
                        agent_cost: 0.03,
                        agent_cost_partial: false,
                        caller_cost: 0.01,
                        caller_unpriced: [],
                        total_time: 60,
                    },
                },
            },
        });
        render(<FenetreDuRun workflowId={34} runId={990} />);
        const bloc = await screen.findByTestId("bloc-simulation");
        expect(texte(bloc)).toContain("failed");
        const simulation = within(bloc).getByTestId("simulation");
        expect(texte(simulation)).toContain("Scenario : Panne urgente");
        expect(texte(simulation)).toContain("Judge : Le créneau n'a pas été proposé.");
        expect([...within(simulation).getByTestId("criteres").children].map(texte)).toEqual([
            "✓ L'agent demande le nom",
            "✗ L'agent propose un créneau",
        ]);
    });
});
