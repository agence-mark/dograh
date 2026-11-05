/**
 * [.mark] Partie 3, sous-lot 20 : les statistiques par étape LISENT `nodes_visited` de chaque appel, elles ne comptent pas
 * autre chose. Une étape traversée deux fois dans le même appel compte une fois ; les deux formes de la trace sont lues.
 */
import { describe, expect, it } from "vitest";

import { lireLesEtapes, partDesAppels } from "./statistiques-etapes";

describe("statistiques par étape", () => {
    it("compte, par étape, les appels qui l'ont traversée", () => {
        const stats = lireLesEtapes([
            { gathered_context: { nodes_visited: ["Accueil", "Motif"] } },
            { gathered_context: { nodes_visited: ["Accueil"] } },
            { gathered_context: {} },
        ]);
        expect(stats.appels).toBe(3);
        expect(stats.parEtape).toEqual({ Accueil: 2, Motif: 1 });
    });

    it("une étape répétée dans un même appel compte une fois", () => {
        const stats = lireLesEtapes([{ gathered_context: { nodes_visited: ["Accueil", "Motif", "Accueil"] } }]);
        expect(stats.parEtape.Accueil).toBe(1);
    });

    it("lit aussi la forme par entrées { agent, etape }", () => {
        const stats = lireLesEtapes([{ gathered_context: { nodes_visited: [{ agent: "Principal", etape: "Accueil" }, { step: "Fin" }] } }]);
        expect(stats.parEtape).toEqual({ Accueil: 1, Fin: 1 });
    });

    it("donne la part en pour cent, ou rien sans appel lu", () => {
        const stats = lireLesEtapes([{ gathered_context: { nodes_visited: ["A"] } }, { gathered_context: null }, { gathered_context: null }, { gathered_context: null }]);
        expect(partDesAppels(stats, "A")).toBe(25);
        expect(partDesAppels(stats, "Inconnue")).toBe(0);
        expect(partDesAppels(lireLesEtapes([]), "A")).toBeNull();
    });
});
