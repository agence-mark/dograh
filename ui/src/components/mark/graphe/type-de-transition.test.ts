/** [.mark] Partie 3, sous-lots 20 et 21 : une couleur par type de transition, par jetons, jamais d'orange ; l'indicateur code ou modèle. */
import { describe, expect, it } from "vitest";

import { STYLE_TRANSITION, typeDeTransition } from "./type-de-transition";

describe("type de transition", () => {
    it("lit le type dans la condition sur la fiche", () => {
        expect(typeDeTransition({})).toBe("modele");
        expect(typeDeTransition({ condition_sur_la_fiche: { etape_complete: true } })).toBe("fiche-complete");
        expect(typeDeTransition({ condition_sur_la_fiche: { champ: "motif", vaut: "devis" } })).toBe("fiche-champ");
    });
    it("sous-lot 21 : règles, toujours et sinon", () => {
        expect(typeDeTransition({ condition_sur_la_fiche: { regles: [{ source: "outil", champ: "reserver", comparaison: "a_reussi" }] } })).toBe("regles");
        expect(typeDeTransition({ condition_sur_la_fiche: { toujours: true } })).toBe("toujours");
        expect(typeDeTransition({ condition_sur_la_fiche: { sinon: true } })).toBe("sinon");
        expect(typeDeTransition({ condition_sur_la_fiche: { regles: [] } })).toBe("modele");
    });
    it("le code, le modèle, toujours et sinon se distinguent au trait ; tout par jetons", () => {
        const signature = (s: (typeof STYLE_TRANSITION)[keyof typeof STYLE_TRANSITION]) => `${s.trait}|${s.pointille ? "pointille" : "plein"}`;
        const { modele, regles, toujours, sinon } = STYLE_TRANSITION;
        expect(new Set([modele, regles, toujours, sinon, STYLE_TRANSITION["fiche-complete"], STYLE_TRANSITION["fiche-champ"]].map(signature)).size).toBe(6);
        expect(sinon.pointille).toBe(true);
        for (const s of Object.values(STYLE_TRANSITION)) {
            expect(s.trait).toMatch(/^var\(--/);
            expect(s.pastille).not.toMatch(/orange|amber|#/);
        }
    });
    it("l'indicateur : le code vérifie les conditions de la fiche et les règles, le modèle juge le reste", () => {
        expect(STYLE_TRANSITION.modele.decide).toBe("modele");
        expect(STYLE_TRANSITION["fiche-complete"].decide).toBe("code");
        expect(STYLE_TRANSITION["fiche-champ"].decide).toBe("code");
        expect(STYLE_TRANSITION.regles.decide).toBe("code");
        expect(STYLE_TRANSITION.toujours.decide).toBe("toujours");
        expect(STYLE_TRANSITION.sinon.decide).toBe("sinon");
    });
});
