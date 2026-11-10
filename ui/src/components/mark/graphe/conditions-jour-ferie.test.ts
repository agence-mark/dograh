/** [.mark] Clôture, lot C : la règle « jour férié » d'une porte, côté écran (sans valeur à saisir ; le serveur calcule le calendrier). */
import { describe, expect, it } from "vitest";

import { CHAMPS_FIXES, comparaisonsDe, fauteDeLaRegle, sansValeur } from "./conditions-de-porte";

describe("la condition « jour férié »", () => {
    it("est un champ de la source heure, avec seulement « est vrai » et « est faux »", () => {
        expect(CHAMPS_FIXES.heure?.map((c) => c.id)).toContain("jour_ferie");
        expect(comparaisonsDe("heure", "jour_ferie")).toEqual(["est_vrai", "est_faux"]);
        expect(comparaisonsDe("heure", "heure")).toEqual(["avant", "apres", "est", "n_est_pas"]);
        expect(comparaisonsDe("heure", "jour")).toEqual(["est", "n_est_pas"]);
    });
    it("ne demande aucune valeur", () => {
        expect(sansValeur("est_vrai")).toBe(true);
        expect(fauteDeLaRegle({ source: "heure", champ: "jour_ferie", comparaison: "est_vrai", valeur: "" })).toBeNull();
    });
});
