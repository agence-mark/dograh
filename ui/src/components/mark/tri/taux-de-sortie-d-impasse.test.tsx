/**
 * [.mark] agent-facon-tala, lot D3: the dead-end rates table at the top of the « To triage » page.
 *
 *     One line per agent with its calls and its two shares, in French by default and in English?
 *     A share without anything to divide shows a dash, never 0 %? The nudges are counted, never lines to triage?
 *     The 7 / 30 days choice asks the server for that period? A click on an agent sets the filter of the queue?
 */
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { FournisseurLangue } from "../langue/langue";
import { PageATrier } from "./PageATrier";

const m = vi.hoisted(() => ({ tri: vi.fn(), taux: vi.fn(), statut: vi.fn() }));

vi.mock("@/client", () => ({
    lireLaFileDeTriApiV1TriGet: (options: unknown) => m.tri(options),
    changerLeStatutDUnSignalementApiV1TriRunIdPut: (options: unknown) => m.statut(options),
    lireLesTauxDeSortieDImpasseApiV1TriTauxGet: (options: unknown) => m.taux(options),
}));
vi.mock("@/lib/auth", () => ({ useAuth: () => ({ user: { id: "u-1" }, loading: false }) }));

const LIGNES_DE_TAUX = [
    { workflow_id: 3, workflow_nom: "Accueil", appels: 20, avec_impasse: 2, part_impasse: 0.1, appels_avec_compteur: 10, avec_reprise_sans_impasse: 3, part_reprise: 0.3 },
    { workflow_id: 4, workflow_nom: "Panne", appels: 5, avec_impasse: 0, part_impasse: 0, appels_avec_compteur: 0, avec_reprise_sans_impasse: 0, part_reprise: null },
];

beforeEach(() => {
    m.tri.mockResolvedValue({ data: { lignes: [], page: 0, a_une_suite: false } });
    m.taux.mockResolvedValue({ data: { jours: 7, lignes: LIGNES_DE_TAUX } });
});
afterEach(() => {
    cleanup();
    vi.clearAllMocks();
    window.localStorage.clear();
});

const monter = (langue?: "en") => {
    if (langue) window.localStorage.setItem("mark.langue", langue);
    return render(
        <FournisseurLangue>
            <PageATrier />
        </FournisseurLangue>,
    );
};

describe("[.mark] the dead-end rates table", () => {
    it("shows one line per agent with its shares, a dash when there is nothing to divide", async () => {
        monter();
        await waitFor(() => expect(screen.getByTestId("taux-3")).toBeTruthy());
        expect(screen.getByText("Impasses par agent")).toBeTruthy();
        expect(screen.getByTestId("part-impasse-3").textContent).toContain("10 %");
        expect(screen.getByTestId("part-reprise-3").textContent).toContain("30 %");
        expect(screen.getByTestId("part-reprise-3").textContent).toContain("3 / 10");
        expect(screen.getByTestId("part-impasse-4").textContent).toContain("0 %");
        expect(screen.getByTestId("part-reprise-4").textContent).toContain("—");
        expect(screen.getByTestId("part-reprise-4").textContent).not.toContain("0 %");
    });

    it("asks the server for 7 days first, then for 30 days on a click", async () => {
        monter();
        await waitFor(() => expect(m.taux).toHaveBeenCalledWith({ query: { jours: 7 } }));
        fireEvent.click(screen.getByText("30 jours"));
        await waitFor(() => expect(m.taux).toHaveBeenCalledWith({ query: { jours: 30 } }));
    });

    it("a click on an agent sets the filter of the queue; a second click clears it", async () => {
        monter();
        await waitFor(() => expect(screen.getByTestId("taux-4")).toBeTruthy());
        fireEvent.click(screen.getByText("Panne", { selector: "button" }));
        await waitFor(() => expect(m.tri).toHaveBeenLastCalledWith({ query: { page: 0, workflow_id: 4 } }));
        fireEvent.click(screen.getByText("Panne", { selector: "button" }));
        await waitFor(() => expect(m.tri).toHaveBeenLastCalledWith({ query: { page: 0, workflow_id: undefined } }));
    });

    it("never turns the nudges into lines of the queue", async () => {
        monter();
        await waitFor(() => expect(screen.getByTestId("taux-3")).toBeTruthy());
        expect(screen.getByTestId("a-trier-vide")).toBeTruthy();
        expect(screen.queryByTestId(/^ligne-/)).toBeNull();
    });

    it("is written in English too", async () => {
        monter("en");
        await waitFor(() => expect(screen.getByText("Dead ends by agent")).toBeTruthy());
        expect(screen.getByText("With a dead end")).toBeTruthy();
        expect(screen.getByText("30 days")).toBeTruthy();
    });

    it("says so when there is no call over the period", async () => {
        m.taux.mockResolvedValue({ data: { jours: 7, lignes: [] } });
        monter();
        await waitFor(() => expect(screen.getByTestId("taux-vide")).toBeTruthy());
    });
});
