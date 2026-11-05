import { describe, expect, it } from "vitest";

import { baseDeEspace } from "./base-espace";

describe("la racine de l'espace d'une flèche retour (T6)", () => {
    it("une adresse de client ou du Labo dit son espace", () => {
        expect(baseDeEspace("/clients/7/campagnes/3", "labo")).toBe("/clients/7");
        expect(baseDeEspace("/labo/campagnes/3", 7)).toBe("/labo");
        expect(baseDeEspace("/relation/clients/4", 7)).toBe("/relation");
    });
    it("une adresse neutre suit l'espace retenu par l'onglet, sinon le Labo", () => {
        expect(baseDeEspace("/conversations/9", 7)).toBe("/clients/7");
        expect(baseDeEspace("/conversations/9", "labo")).toBe("/labo");
        expect(baseDeEspace("/agents/12", null)).toBe("/labo");
    });
});
