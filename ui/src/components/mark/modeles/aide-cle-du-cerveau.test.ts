/** [.mark] passages-fiables: the help under « API key » names the brain of its own window; the clerk's words do not move. */
import { describe, expect, it } from "vitest";

import { AIDE_CLE_DU_GREFFIER, aideCleDuCerveau } from "./ChampsFournisseurLlm";

describe("[.mark] help under « API key »", () => {
    it("keeps the clerk's text to the letter", () => {
        expect(AIDE_CLE_DU_GREFFIER.fr).toBe(
            "Une clé de la bibliothèque est nommée, jamais montrée. Vide, le greffier prend la clé de la conversation et partage son quota.",
        );
    });
    it("names the brain of the window, in both languages, and never the clerk", () => {
        const fond = aideCleDuCerveau({ en: "the background brain", fr: "le cerveau de fond" });
        expect(fond.fr).toContain("Vide, le cerveau de fond prend la clé");
        expect(fond.en).toContain("Empty, the background brain uses");
        const garde = aideCleDuCerveau({ en: "the second try", fr: "la seconde tentative" });
        expect(garde.fr).toContain("Vide, la seconde tentative prend la clé");
        for (const aide of [fond, garde]) expect(`${aide.fr}${aide.en}`).not.toMatch(/greffier|clerk/);
    });
});
