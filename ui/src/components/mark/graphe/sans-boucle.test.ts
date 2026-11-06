/** [.mark] Partie 3, sous-lot 20 : « empêcher les boucles » ne laisse pas fermer un cycle, et repère ceux qui existent. */
import { describe, expect, it } from "vitest";

import { fermeUnCycle, liensEnBoucle } from "./sans-boucle";

const chaine = [
    { source: "a", target: "b" },
    { source: "b", target: "c" },
];

describe("boucles du graphe", () => {
    it("refuse un lien qui revient en arrière", () => {
        expect(fermeUnCycle(chaine, "c", "a")).toBe(true);
        expect(fermeUnCycle(chaine, "c", "b")).toBe(true);
    });
    it("refuse une étape reliée à elle-même", () => {
        expect(fermeUnCycle([], "a", "a")).toBe(true);
    });
    it("accepte un lien qui va de l'avant, même en diamant", () => {
        expect(fermeUnCycle(chaine, "a", "c")).toBe(false);
        expect(fermeUnCycle([...chaine, { source: "a", target: "d" }], "d", "c")).toBe(false);
    });
    it("repère les liaisons qui ferment un cycle déjà posé", () => {
        expect(liensEnBoucle(chaine)).toEqual([]);
        expect(liensEnBoucle([...chaine, { source: "c", target: "a" }]).length).toBe(3);
    });
});
