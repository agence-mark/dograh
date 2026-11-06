import { describe, expect, it } from "vitest";

import { libelleEtatDuJuge } from "./etat-du-juge";

describe("libellés de l'état du juge", () => {
    it("dit « allumé mais pas réglé » et « budget atteint » en français et en anglais", () => {
        expect(libelleEtatDuJuge("non_regle")?.fr).toMatch(/allumé sur cet agent mais pas réglé/);
        expect(libelleEtatDuJuge("budget_atteint")?.fr).toMatch(/budget du mois/);
        expect(libelleEtatDuJuge("budget_atteint")?.en).toMatch(/monthly budget/);
    });
    it("ne dit rien d'un appel jugé ni d'un état inconnu", () => {
        expect(libelleEtatDuJuge("juge")).toBeNull();
        expect(libelleEtatDuJuge("autre")).toBeNull();
        expect(libelleEtatDuJuge(undefined)).toBeNull();
    });
});
