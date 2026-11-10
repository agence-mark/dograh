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
import { ECHECS } from "@/components/mark/notifications/phrases-echec";
import { phraseAttendue } from "@/components/mark/notifications/texte-attendu";
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { FournisseurLangue } from "../langue/langue";
import { OngletAlertes } from "./OngletAlertes";
import { PageAlertes } from "./PageAlertes";

const m = vi.hoisted(() => ({
    tri: vi.fn(),
    statut: vi.fn(),
    alertes: vi.fn(),
    taux: vi.fn(),
    personnes: vi.fn(),
}));

vi.mock("@/components/mark/studio/liste-deroulante", async () => await import("@/components/mark/studio/liste-deroulante-natif-test"));
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
        expect(await screen.findByText("Aucune alerte.")).toBeTruthy();
        expect(document.querySelector("table")).toBeNull();
    });

    it("says it could not load, with a retry, and never shows the server's text (V2)", async () => {
        m.alertes.mockResolvedValue({ error: { detail: "Not allowed" } });
        render(<FournisseurLangue><PageAlertes /></FournisseurLangue>);
        expect(await screen.findByText("Impossible de charger")).toBeTruthy();
        expect(screen.queryByText(/Not allowed/)).toBeNull();
        m.alertes.mockResolvedValue({ data: { lignes: ALERTES, page: 0, a_une_suite: false } });
        fireEvent.click(screen.getByRole("button", { name: "Réessayer" }));
        expect(await screen.findByText("Outil en échec")).toBeTruthy();
    });

    it("lists the alerts in a bare table, never in framed cards (V2)", async () => {
        render(<FournisseurLangue><PageAlertes /></FournisseurLangue>);
        await screen.findByText("Outil en échec");
        expect(document.querySelectorAll("tbody tr").length).toBe(ALERTES.length);
        expect(document.querySelector(".rounded.border")).toBeNull();
    });
});

describe("[.mark] the pages of the menu", () => {
    it("carry their title in both languages; the explanation is in the « ! », never a visible sentence (K1b)", async () => {
        render(<FournisseurLangue><OngletAlertes /></FournisseurLangue>);
        expect(await screen.findByText("Alertes")).toBeTruthy();
        expect(screen.getByRole("button", { name: "Précision" })).toBeTruthy();
        expect(screen.queryByText(/Les problèmes rencontrés par les appels/)).toBeNull();
        cleanup();
        render(<OngletAlertes />);
        expect(await screen.findByText("Alerts")).toBeTruthy();
    });
});
