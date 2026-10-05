/**
 * [.mark] The clerk's account on a call's page (plan mode-prise-de-notes, part 2):
 * passes, failures and tokens added up from `greffier_passes`; nothing without a clerk.
 */
import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it } from "vitest";

import { bilanDuGreffier, BilanGreffier } from "./BilanGreffier";
import { FournisseurLangue } from "./langue/langue";

afterEach(cleanup);

const PASSES = [
    { tour: 1, etat: "ecrit", champs: ["nom"], jetons_entree: 800, jetons_sortie: 12 },
    { tour: 2, etat: "rien", champs: [], jetons_entree: 900, jetons_sortie: 5 },
    { tour: 3, etat: "echec", champs: [], erreur: "AuthenticationError" },
    { tour: 4, etat: "saute", champs: [] },
    { tour: 5, etat: "illisible", champs: [], jetons_entree: 950, jetons_sortie: 3 },
];

describe("the clerk's account of a call", () => {
    it("adds up passes, failures and tokens", () => {
        expect(bilanDuGreffier({ greffier_passes: PASSES })).toEqual({
            passes: 5,
            ecrites: 1,
            sansRien: 1,
            echecs: 1,
            illisibles: 1,
            sautees: 1,
            tardives: 0,
            jetonsEntree: 2650,
            jetonsSortie: 20,
            erreurs: ["AuthenticationError"],
        });
    });

    it("draws nothing for a call without a clerk", () => {
        expect(bilanDuGreffier({ nom: "Dupont" })).toBeNull();
        expect(bilanDuGreffier(null)).toBeNull();
        const { container } = render(
            <FournisseurLangue>
                <BilanGreffier fiche={{ nom: "Dupont" }} />
            </FournisseurLangue>,
        );
        expect(container.innerHTML).toBe("");
    });

    it("shows the failures where they can be seen, with the error's name", () => {
        render(
            <FournisseurLangue>
                <BilanGreffier fiche={{ greffier_passes: PASSES }} />
            </FournisseurLangue>,
        );
        const alerte = screen.getByRole("alert");
        expect(alerte.textContent).toMatch(/2/);
        expect(alerte.textContent).toContain("AuthenticationError");
        expect(screen.getByTestId("bilan-greffier").textContent).toMatch(/2650/);
    });

    it("raises no alert when every pass went through", () => {
        render(
            <FournisseurLangue>
                <BilanGreffier fiche={{ greffier_passes: PASSES.slice(0, 2) }} />
            </FournisseurLangue>,
        );
        expect(screen.queryByRole("alert")).toBeNull();
    });
});
