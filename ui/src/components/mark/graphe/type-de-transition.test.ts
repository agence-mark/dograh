/** [.mark] Partie 3, sous-lot 20 : une couleur par type de transition, par jetons, jamais d'orange. */
import { describe, expect, it } from "vitest";

import { STYLE_TRANSITION, typeDeTransition } from "./type-de-transition";

describe("type de transition", () => {
    it("lit le type dans la condition sur la fiche", () => {
        expect(typeDeTransition({})).toBe("modele");
        expect(typeDeTransition({ condition_sur_la_fiche: { etape_complete: true } })).toBe("fiche-complete");
        expect(typeDeTransition({ condition_sur_la_fiche: { champ: "motif", vaut: "devis" } })).toBe("fiche-champ");
    });
    it("trois types, trois traits différents, tous par jetons", () => {
        const traits = Object.values(STYLE_TRANSITION).map((s) => s.trait);
        expect(new Set(traits).size).toBe(3);
        for (const s of Object.values(STYLE_TRANSITION)) {
            expect(s.trait).toMatch(/^var\(--/);
            expect(s.pastille).not.toMatch(/orange|amber|#/);
        }
    });
});
