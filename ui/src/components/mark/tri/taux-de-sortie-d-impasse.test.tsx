/**
 * [.mark] agent-facon-tala, lot D3: the dead-end rates table, an tab of « To improve ».
 *
 *     One line per agent with its calls and its two shares, in French by default and in English?
 *     A share without anything to divide shows a dash, never 0 %? The nudges are counted, never lines to triage?
 *     The 7 / 30 days choice asks the server for that period? A click on an agent sets the filter of the queue?
 */
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { FournisseurLangue } from "../langue/langue";
import { TauxDeSortieDImpasse } from "./TauxDeSortieDImpasse";

const m = vi.hoisted(() => ({ taux: vi.fn() }));

vi.mock("@/client", () => ({
    lireLesTauxDeSortieDImpasseApiV1TriTauxGet: (options: unknown) => m.taux(options),
}));
vi.mock("next/navigation", () => ({ useRouter: () => ({ push: vi.fn() }) }));
vi.mock("@/lib/auth", () => ({ useAuth: () => ({ user: { id: "u-1" }, loading: false }) }));

const LIGNES_DE_TAUX = [
    { workflow_id: 3, workflow_nom: "Accueil", appels: 20, avec_impasse: 2, part_impasse: 0.1, appels_avec_compteur: 10, avec_reprise_sans_impasse: 3, part_reprise: 0.3 },
    { workflow_id: 4, workflow_nom: "Panne", appels: 5, avec_impasse: 0, part_impasse: 0, appels_avec_compteur: 0, avec_reprise_sans_impasse: 0, part_reprise: null },
];

beforeEach(() => {
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
            <TauxDeSortieDImpasse />
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

    it("ignores a late answer for a period that is no longer the chosen one", async () => {
        let rendre7: (v: unknown) => void = () => {};
        let rendre30: (v: unknown) => void = () => {};
        m.taux.mockImplementation((o: { query: { jours: number } }) =>
            new Promise((resolve) => {
                if (o.query.jours === 7) rendre7 = resolve;
                else rendre30 = resolve;
            }),
        );
        monter();
        await waitFor(() => expect(m.taux).toHaveBeenCalledWith({ query: { jours: 7 } }));
        fireEvent.click(screen.getByText("30 jours"));
        await waitFor(() => expect(m.taux).toHaveBeenCalledWith({ query: { jours: 30 } }));
        // la réponse de 30 jours arrive d'abord, celle de 7 jours (périmée) ensuite
        rendre30({ data: { jours: 30, lignes: [{ ...LIGNES_DE_TAUX[0], workflow_nom: "Trente", appels: 30 }] } });
        await waitFor(() => expect(screen.getByText("Trente", { selector: "span" })).toBeTruthy());
        rendre7({ data: { jours: 7, lignes: [{ ...LIGNES_DE_TAUX[0], workflow_nom: "Sept", appels: 7 }] } });
        await new Promise((r) => setTimeout(r, 30));
        expect(screen.queryByText("Sept", { selector: "span" })).toBeNull();
        expect(screen.getByText("Trente", { selector: "span" })).toBeTruthy();
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
