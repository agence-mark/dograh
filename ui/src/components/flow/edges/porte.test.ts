/**
 * [.mark] L6+ (audit 01 A8) : renommer une liaison dans l'écran garde le nom de sa porte.
 *
 * | Test | La garantie |
 * |---|---|
 * | renommage | un nouveau libellé pose l'identifiant manquant : le nom d'avant |
 * | identifiant posé | il ne change jamais, quel que soit le libellé |
 * | sans renommage | rien n'est posé : l'ancien graphe reste tel quel |
 */
import { describe, expect, it } from "vitest";

import { identifiantGarde, nomDuLibelle } from "./porte";

describe("la porte à identifiant stable", () => {
    it("pose le nom d'avant quand le libellé change", () => {
        expect(identifiantGarde({ label: "Prendre rendez-vous" }, "Réserver")).toBe("prendre_rendez_vous");
    });
    it("garde un identifiant déjà posé", () => {
        expect(identifiantGarde({ label: "Réserver", identifiant: "prendre_rendez_vous" }, "Autre chose")).toBe("prendre_rendez_vous");
    });
    it("ne pose rien sans renommage", () => {
        expect(identifiantGarde({ label: "Fini" }, "Fini")).toBeUndefined();
        expect(identifiantGarde(undefined, "Nouveau")).toBeUndefined();
    });
    it("suit la règle du serveur", () => {
        expect(nomDuLibelle("Ça va ?")).toBe("_a_va__");
    });
});
