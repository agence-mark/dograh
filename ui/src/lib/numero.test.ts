/** [.mark] Partie 3, lot 15 (L-5) : l'affichage à la française d'un numéro ; le reste est montré tel quel. */
import { describe, expect, it } from "vitest";

import { formaterNumero } from "./numero";

describe("formaterNumero (L-5)", () => {
    it("un numéro français, en +33 ou en 0, s'affiche par paires", () => {
        expect(formaterNumero("+33344000002")).toBe("03 44 00 00 02");
        expect(formaterNumero("0344000002")).toBe("03 44 00 00 02");
        expect(formaterNumero("03.44.00.00.02")).toBe("03 44 00 00 02");
        expect(formaterNumero(" +33 6 12 34 56 78 ")).toBe("06 12 34 56 78");
    });

    it("un autre numéro, un texte ou du vide ne sont jamais redécoupés", () => {
        expect(formaterNumero("+442079460958")).toBe("+442079460958");
        expect(formaterNumero("poste 12")).toBe("poste 12");
        expect(formaterNumero("+3334400")).toBe("+3334400");
        expect(formaterNumero("")).toBe("");
        expect(formaterNumero(null)).toBe("");
    });
});
