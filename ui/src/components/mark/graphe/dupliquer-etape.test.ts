/** [.mark] Partie 3, sous-lot 20 : « Dupliquer » de la barre au survol rend une copie neuve, décalée, sans toucher l'originale. */
import { describe, expect, it } from "vitest";

import type { FlowNode } from "@/components/flow/types";

import { copieDeLEtape, DECALAGE_DE_LA_COPIE } from "./dupliquer-etape";

const noeuds = [
    { id: "1", type: "agentNode", position: { x: 100, y: 200 }, data: { name: "Motif", prompt: "p" } },
    { id: "2", type: "startCall", position: { x: 0, y: 0 }, data: { name: "Début" } },
] as unknown as FlowNode[];

describe("copie d'une étape", () => {
    it("rend une copie à identifiant neuf, nommée et décalée", () => {
        const copie = copieDeLEtape(noeuds, "1", "(copie)")!;
        expect(copie.id).not.toBe("1");
        expect(noeuds.some((n) => n.id === copie.id)).toBe(false);
        expect((copie.data as { name: string }).name).toBe("Motif (copie)");
        expect(copie.position).toEqual({ x: 100 + DECALAGE_DE_LA_COPIE.x, y: 200 + DECALAGE_DE_LA_COPIE.y });
        expect((noeuds[0].data as { name: string }).name).toBe("Motif");
        expect(copie.data).not.toBe(noeuds[0].data);
    });
    it("refuse quand le type est limité à une instance déjà posée", () => {
        expect(copieDeLEtape(noeuds, "2", "(copie)", 1)).toBeNull();
    });
    it("ne rend rien pour une étape inconnue", () => {
        expect(copieDeLEtape(noeuds, "9", "(copie)")).toBeNull();
    });
});
