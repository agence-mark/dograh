/** [.mark] Lot 26, M35 : « carte à la livraison » est proposée parmi les moyens de paiement du fork, en français et en anglais. */
import { describe, expect, it } from "vitest";

import { MOYENS } from "./reglages-restaurant";

describe("M35 : moyens de paiement du fork", () => {
    it("propose la carte à la livraison, avec ses deux langues", () => {
        const m = MOYENS.find((x) => x.code === "carte_livraison");
        expect(m).toEqual({ code: "carte_livraison", fr: "Carte à la livraison", en: "Card on delivery" });
    });
    it("garde les cinq moyens d'avant, sans doublon", () => {
        const codes = MOYENS.map((x) => x.code);
        expect(codes).toEqual(expect.arrayContaining(["carte", "especes", "titre_restaurant", "cheque", "en_ligne"]));
        expect(new Set(codes).size).toBe(codes.length);
    });
});
