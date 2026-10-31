/**
 * [.mark] passages-fiables, lot G: the « To triage » and « Alerts » pages of the menu.
 *
 * The questions this file answers:
 *
 *     Does each page show one line per flag / alert, in French by default and in English, with a link to the call?
 *     Does the status change go to the server with the flag's identifier, and show at once?
 *     Does the agent filter ask the server for that agent only? Does an empty list say so?
 *     Does an alert tell whether it was mailed, not mailed (kept here) or already notified?
 *     Do the pages of the menu carry their title, and the sidebar its two entries?
 */
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import PageAlertesDuMenu from "@/app/alertes/page";
import PageATrierDuMenu from "@/app/a-trier/page";

import { FournisseurLangue } from "../langue/langue";
import { PageAlertes } from "./PageAlertes";
import { PageATrier } from "./PageATrier";

const m = vi.hoisted(() => ({
    tri: vi.fn(),
    statut: vi.fn(),
    alertes: vi.fn(),
    taux: vi.fn(),
    personnes: vi.fn(),
}));

vi.mock("@/client", () => ({
    lireLaFileDeTriApiV1TriGet: (options: unknown) => m.tri(options),
    changerLeStatutDUnSignalementApiV1TriRunIdPut: (options: unknown) => m.statut(options),
    lireLesAlertesApiV1AlertesGet: (options: unknown) => m.alertes(options),
    lireLesTauxDeSortieDImpasseApiV1TriTauxGet: (options: unknown) => m.taux(options),
    lireLesPersonnesAssignablesApiV1TriPersonnesGet: () => m.personnes(),
}));
vi.mock("@/lib/auth", () => ({ useAuth: () => ({ user: { id: "u-1" }, loading: false }) }));

const LIGNES = [
    {
        run_id: 12, workflow_id: 3, workflow_nom: "Accueil", cree_le: "2026-10-28T10:15:00+00:00", id: "agent:0", source: "agent",
        type: "agent", categorie: "règle inconnue", motif: "Je ne connais pas la règle de ce cas", etape: "Qualification", tour: 2, statut: "ouvert",
    },
    {
        run_id: 12, workflow_id: 3, workflow_nom: "Accueil", cree_le: "2026-10-28T10:15:00+00:00", id: "desaccord:0", source: "code",
        type: "desaccord", categorie: null, motif: "porte_x", etape: "Qualification", tour: 4, statut: "en cours",
    },
    {
        run_id: 15, workflow_id: 4, workflow_nom: "Rendez-vous", cree_le: "2026-10-27T09:00:00+00:00", id: "impasse:1", source: "code",
        type: "impasse", categorie: null, motif: "impasse", etape: null, tour: 5, statut: "résolu",
    },
];

const ALERTES = [
    { run_id: 20, workflow_id: 3, workflow_nom: "Accueil", cree_le: "2026-10-28T10:15:00+00:00", id: "alerte:0", type: "outil_en_echec", detail: null, etape: "Prise", outil: "agenda", tour: 3, heure: "2026-10-28T10:16:00+00:00", mail: "envoye" },
    { run_id: 20, workflow_id: 3, workflow_nom: "Accueil", cree_le: "2026-10-28T10:15:00+00:00", id: "alerte:1", type: "panne_modele", detail: "modele (modele_lent)", etape: null, outil: null, tour: null, heure: "2026-10-28T10:17:00+00:00", mail: "deja_notifiee" },
    { run_id: 21, workflow_id: 4, workflow_nom: "Rendez-vous", cree_le: "2026-10-28T11:00:00+00:00", id: "alerte:0", type: "transfert_echoue", detail: null, etape: null, outil: null, tour: null, heure: "2026-10-28T11:01:00+00:00", mail: "non_envoye" },
    { run_id: 22, workflow_id: 4, workflow_nom: "Rendez-vous", cree_le: "2026-10-28T12:00:00+00:00", id: "alerte:0", type: "appel_en_erreur", detail: "pipeline_error", etape: null, outil: null, tour: null, heure: null, mail: null },
];

beforeEach(() => {
    m.tri.mockResolvedValue({ data: { lignes: LIGNES, page: 0, a_une_suite: false } });
    m.statut.mockResolvedValue({ data: { run_id: 12, identifiant: "agent:0", statut: "résolu" } });
    m.alertes.mockResolvedValue({ data: { lignes: ALERTES, page: 0, a_une_suite: true } });
    m.taux.mockResolvedValue({ data: { jours: 7, lignes: [] } });
    m.personnes.mockResolvedValue({ data: [{ id: 5, nom: "equipe@exemple.test" }] });
});
afterEach(() => {
    cleanup();
    vi.clearAllMocks();
    window.localStorage.clear();
});

describe("[.mark] the « To triage » page", () => {
    it("shows one line per flag, in French by default, with the link to the call", async () => {
        render(<FournisseurLangue><PageATrier /></FournisseurLangue>);
        expect(await screen.findByText("Signalé par l'agent")).toBeTruthy();
        expect(screen.getByText("Règle inconnue", { exact: false })).toBeTruthy();
        expect(screen.getByText("Je ne connais pas la règle de ce cas")).toBeTruthy();
        expect(screen.getByText("L'agent et l'arbitre en désaccord")).toBeTruthy();
        expect(screen.getByText("Conversation qui tourne en rond")).toBeTruthy();
        const liens = screen.getAllByRole("link", { name: /Ouvrir l'appel/ });
        expect(liens.map((l) => l.getAttribute("href"))).toEqual(["/workflow/3/run/12", "/workflow/3/run/12", "/workflow/4/run/15"]);
        const statuts = screen.getAllByLabelText("Statut") as HTMLSelectElement[];
        expect(statuts.map((s) => s.value)).toEqual(["ouvert", "en cours", "résolu"]);
        expect(screen.getByText(/30 derniers jours/)).toBeTruthy();
    });

    it("speaks English outside the provider", async () => {
        render(<PageATrier />);
        expect(await screen.findByText("Flagged by the agent")).toBeTruthy();
        expect(screen.getAllByText("Open the call", { exact: false }).length).toBe(3);
        expect(screen.getByText(/Last 30 days/)).toBeTruthy();
    });

    it("sends the status change with the flag's identifier and shows it at once", async () => {
        render(<FournisseurLangue><PageATrier /></FournisseurLangue>);
        await screen.findByText("Signalé par l'agent");
        const premier = screen.getAllByLabelText("Statut")[0] as HTMLSelectElement;
        fireEvent.change(premier, { target: { value: "résolu" } });
        await waitFor(() => expect(m.statut).toHaveBeenCalled());
        expect(m.statut).toHaveBeenCalledWith({ path: { run_id: 12 }, body: { identifiant: "agent:0", statut: "résolu" } });
        await waitFor(() => expect((screen.getAllByLabelText("Statut")[0] as HTMLSelectElement).value).toBe("résolu"));
    });

    it("keeps the old status and says so when the server refuses", async () => {
        m.statut.mockResolvedValue({ error: { detail: "Flag not found" } });
        render(<FournisseurLangue><PageATrier /></FournisseurLangue>);
        await screen.findByText("Signalé par l'agent");
        fireEvent.change(screen.getAllByLabelText("Statut")[0], { target: { value: "fusionné" } });
        expect((await screen.findByRole("alert")).textContent).toContain("Flag not found");
        expect((screen.getAllByLabelText("Statut")[0] as HTMLSelectElement).value).toBe("ouvert");
    });

    it("assigns a flag to a person of the organization and sets its origin, then shows where the origin leads (builder, lot 6)", async () => {
        m.statut.mockResolvedValue({ data: { run_id: 12, identifiant: "agent:0", statut: "ouvert" } });
        render(<FournisseurLangue><PageATrier /></FournisseurLangue>);
        await screen.findByText("Signalé par l'agent");
        await screen.findAllByRole("option", { name: "equipe@exemple.test", hidden: true });
        fireEvent.change(screen.getAllByLabelText("Assigné à")[0], { target: { value: "5" } });
        await waitFor(() => expect(m.statut).toHaveBeenCalledWith({ path: { run_id: 12 }, body: { identifiant: "agent:0", assigne: 5 } }));
        expect((screen.getAllByLabelText("Assigné à")[0] as HTMLSelectElement).value).toBe("5");
        fireEvent.change(screen.getAllByLabelText("Origine du signalement")[0], { target: { value: "client" } });
        await waitFor(() => expect(m.statut).toHaveBeenCalledWith({ path: { run_id: 12 }, body: { identifiant: "agent:0", origine: "client" } }));
        expect((await screen.findAllByTestId("suite-de-l-origine"))[0].textContent).toContain("Corriger la fiche du client");
    });

    it("filters by origin and links each flag to the creation of a test from its reply", async () => {
        render(<FournisseurLangue><PageATrier /></FournisseurLangue>);
        await screen.findByText("Signalé par l'agent");
        fireEvent.change(screen.getByLabelText("Filtrer par origine"), { target: { value: "code" } });
        await waitFor(() => expect(m.tri).toHaveBeenLastCalledWith({ query: { page: 0, workflow_id: undefined, origine: "code" } }));
        const liens = screen.getAllByRole("link", { name: "Créer un test" });
        expect(liens.map((l) => l.getAttribute("href"))).toEqual([
            "/workflow/3/run/12?creer_test=2",
            "/workflow/3/run/12?creer_test=4",
            "/workflow/4/run/15?creer_test=5",
        ]);
    });

    it("filters by agent: the server is asked for that agent only, from the first page", async () => {
        render(<FournisseurLangue><PageATrier /></FournisseurLangue>);
        await screen.findByText("Signalé par l'agent");
        fireEvent.change(screen.getByLabelText("Filtrer par agent"), { target: { value: "4" } });
        await waitFor(() => expect(m.tri).toHaveBeenLastCalledWith({ query: { page: 0, workflow_id: 4 } }));
    });

    it("says so when there is nothing to triage, and pages forward only when the server has more", async () => {
        m.tri.mockResolvedValue({ data: { lignes: [], page: 0, a_une_suite: false } });
        render(<FournisseurLangue><PageATrier /></FournisseurLangue>);
        expect((await screen.findByTestId("a-trier-vide")).textContent).toBe("Rien à trier.");
        expect((screen.getByRole("button", { name: "Suivant" }) as HTMLButtonElement).disabled).toBe(true);
        expect((screen.getByRole("button", { name: "Précédent" }) as HTMLButtonElement).disabled).toBe(true);
    });

    it("goes to the next page when there is one", async () => {
        m.tri.mockResolvedValue({ data: { lignes: LIGNES, page: 0, a_une_suite: true } });
        render(<FournisseurLangue><PageATrier /></FournisseurLangue>);
        await screen.findByText("Signalé par l'agent");
        fireEvent.click(screen.getByRole("button", { name: "Suivant" }));
        await waitFor(() => expect(m.tri).toHaveBeenLastCalledWith({ query: { page: 1, workflow_id: undefined } }));
    });
});

describe("[.mark] the reasons written by the code (tri lisible)", () => {
    const ligne = (id: string, type: string, motif: string) => ({
        run_id: 30, workflow_id: 3, workflow_nom: "Accueil", cree_le: "2026-10-28T10:15:00+00:00", id, source: "code",
        type, categorie: null, motif, etape: null, tour: 1, statut: "ouvert",
    });

    it("shows a plain French sentence first and the technical detail second", async () => {
        m.tri.mockResolvedValue({
            data: {
                lignes: [
                    ligne("impasse:1", "impasse", "impasse_repetee"),
                    ligne("retenue_verite:0", "retenue_verite", "date_non_trouvee : reserver : lundi 3 novembre"),
                    ligne("desaccord:0", "desaccord", "porte_x"),
                    ligne("passage_sans_suite:0", "passage_sans_suite", "valeur_jamais_vue"),
                ],
                page: 0,
                a_une_suite: false,
            },
        });
        render(<FournisseurLangue><PageATrier /></FournisseurLangue>);
        expect(await screen.findByText("Action retenue par la vérité des actions")).toBeTruthy();
        const lisibles = screen.getAllByTestId("motif-lisible").map((e) => e.textContent);
        expect(lisibles).toEqual([
            "Deuxième impasse dans le même appel(impasse_repetee)",
            "Une date que la recherche n'a pas donnée(reserver : lundi 3 novembre)",
            "L'arbitre proposait une autre sortie que l'agent(porte_x)",
        ]);
        // a value the table does not know stays visible as it is
        expect(screen.getByText("valeur_jamais_vue")).toBeTruthy();
        expect(screen.queryByText("date_non_trouvee : reserver : lundi 3 novembre")).toBeNull();
    });

    it("says the same in English outside the provider", async () => {
        m.tri.mockResolvedValue({ data: { lignes: [ligne("impasse:1", "impasse", "impasse")], page: 0, a_une_suite: false } });
        render(<PageATrier />);
        expect((await screen.findByTestId("motif-lisible")).textContent).toContain("The agent kept repeating itself");
    });
});

describe("[.mark] the « Alerts » page", () => {
    it("shows each alert with its mail state, in French", async () => {
        render(<FournisseurLangue><PageAlertes /></FournisseurLangue>);
        expect(await screen.findByText("Outil en échec")).toBeTruthy();
        expect(screen.getByText("Panne du modèle")).toBeTruthy();
        expect(screen.getByText("Transfert échoué")).toBeTruthy();
        expect(screen.getByText("Appel terminé en erreur")).toBeTruthy();
        expect(screen.getByText("Mail envoyé")).toBeTruthy();
        expect(screen.getByText("Déjà notifiée par le gardien de panne")).toBeTruthy();
        expect(screen.getByText("Pas de mail (aucun serveur) : gardée ici")).toBeTruthy();
        expect(screen.getByText("Pas de mail (option éteinte)")).toBeTruthy();
        expect(screen.getByText("· agenda")).toBeTruthy();
        expect(screen.getAllByRole("link", { name: /Ouvrir l'appel/ }).map((l) => l.getAttribute("href"))).toContain("/workflow/4/run/21");
    });

    it("speaks English outside the provider", async () => {
        render(<PageAlertes />);
        expect(await screen.findByText("Tool failure")).toBeTruthy();
        expect(screen.getByText("Not mailed (no mail server): kept here")).toBeTruthy();
    });

    it("says so when there is no alert, and pages forward when the server has more", async () => {
        render(<FournisseurLangue><PageAlertes /></FournisseurLangue>);
        await screen.findByText("Outil en échec");
        fireEvent.click(screen.getByRole("button", { name: "Suivant" }));
        await waitFor(() => expect(m.alertes).toHaveBeenLastCalledWith({ query: { page: 1 } }));
        cleanup();
        m.alertes.mockResolvedValue({ data: { lignes: [], page: 0, a_une_suite: false } });
        render(<FournisseurLangue><PageAlertes /></FournisseurLangue>);
        expect((await screen.findByTestId("alertes-vide")).textContent).toBe("Aucune alerte.");
    });

    it("shows the server's refusal instead of an empty list", async () => {
        m.alertes.mockResolvedValue({ error: { detail: "Not allowed" } });
        render(<FournisseurLangue><PageAlertes /></FournisseurLangue>);
        expect((await screen.findByRole("alert")).textContent).toContain("Not allowed");
    });
});

describe("[.mark] the pages of the menu", () => {
    it("carry their title and description in both languages", async () => {
        render(<FournisseurLangue><PageATrierDuMenu /></FournisseurLangue>);
        expect(await screen.findByRole("heading", { name: "À trier" })).toBeTruthy();
        cleanup();
        render(<FournisseurLangue><PageAlertesDuMenu /></FournisseurLangue>);
        expect(await screen.findByRole("heading", { name: "Alertes" })).toBeTruthy();
        cleanup();
        render(<PageAlertesDuMenu />);
        expect(await screen.findByRole("heading", { name: "Alerts" })).toBeTruthy();
    });
});
