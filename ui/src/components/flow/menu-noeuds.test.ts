import { existsSync } from "node:fs";
import { join } from "node:path";

import { describe, expect, it } from "vitest";

import type { NodeSpec } from "@/client/types.gen";

import { specsDuMenu, specsProposees } from "./menu-noeuds";

const spec = (name: string) => ({ name, display_name: name, properties: [] }) as unknown as NodeSpec;

describe("menu Nœud (K2b)", () => {
    it("range les types dans l'ordre de la maquette et retire le début et les intégrations retirées", () => {
        const noms = specsDuMenu(["webhook", "startCall", "qa", "noveum", "endCall", "agentNode", "trigger", "globalNode"].map(spec)).map((s) => s.name);
        expect(noms).toEqual(["agentNode", "endCall", "globalNode", "trigger"]);
    });

    it("RA-B R5 (05 § 1 et 15) : ni le webhook de Dograh ni « Contrôle qualité » ne sont proposés, le code reste", () => {
        const noms = specsDuMenu(["webhook", "qa", "agentNode"].map(spec)).map((s) => s.name);
        expect(noms).toEqual(["agentNode"]);
        // Les types existent toujours côté serveur : un agent qui en porte déjà un continue de l'afficher (GenericNode).
        expect(specsProposees(["webhook", "qa"].map(spec)).map((s) => s.name)).toEqual([]);
    });

    it("garde après les autres un type que la maquette ne connaît pas", () => {
        expect(specsDuMenu(["autre", "agentNode"].map(spec)).map((s) => s.name)).toEqual(["agentNode", "autre"]);
    });

    it("le panneau latéral d'ajout n'existe plus (il n'était plus monté)", () => {
        expect(existsSync(join(process.cwd(), "src/components/flow/AddNodePanel.tsx"))).toBe(false);
    });
});
