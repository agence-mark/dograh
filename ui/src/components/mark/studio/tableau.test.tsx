/**
 * Clôture D2 : un tableau masque ses colonnes les moins utiles quand la place manque (panneau de droite ouvert), puis défile
 * en lui-même ; aucune colonne n'est coupée à moitié. jsdom ne mesure rien : la largeur est simulée (150 px par colonne visible).
 */
import { cleanup, render } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it } from "vitest";

import { Cellule, Ligne, Tableau } from "./tableau";

const COLONNES = [
    { titre: "Outil" },
    { titre: "Type" },
    { titre: "Branché sur", secondaire: 2 },
    { titre: "Réussite", secondaire: 3 },
    { titre: "Modifié", secondaire: 1 },
];

let place = 700;
beforeEach(() => {
    Object.defineProperty(HTMLElement.prototype, "clientWidth", { configurable: true, get: () => place });
    Object.defineProperty(HTMLTableElement.prototype, "scrollWidth", {
        configurable: true,
        get(this: HTMLTableElement) {
            const entetes = Array.from(this.tHead!.rows[0].cells);
            return entetes.filter((c) => c.style.display !== "none").length * 150;
        },
    });
});
afterEach(() => cleanup());

const monter = () =>
    render(
        <Tableau colonnes={COLONNES}>
            <Ligne>
                <Cellule principale>nom</Cellule>
                <Cellule>type</Cellule>
                <Cellule>cible</Cellule>
                <Cellule>90 %</Cellule>
                <Cellule>9 nov.</Cellule>
            </Ligne>
        </Tableau>,
    );

const visibles = (c: HTMLElement) => Array.from(c.querySelectorAll("thead th")).filter((th) => (th as HTMLElement).style.display !== "none").map((th) => th.textContent);

describe("Tableau : colonnes de repli", () => {
    it("tout tient : aucune colonne masquée", () => {
        place = 800;
        const { container } = monter();
        expect(visibles(container)).toEqual(["Outil", "Type", "Branché sur", "Réussite", "Modifié"]);
    });

    it("la place manque : la moins utile part d'abord, l'en-tête et les cellules ensemble, la première colonne reste", () => {
        place = 500;
        const { container } = monter();
        expect(visibles(container)).toEqual(["Outil", "Type", "Réussite"]);
        const cellules = Array.from(container.querySelectorAll("tbody td")) as HTMLElement[];
        expect(cellules.map((c) => c.style.display === "none")).toEqual([false, false, true, false, true]);
    });

    it("très peu de place : seules les colonnes sans rang restent, le tableau défile en lui-même", () => {
        place = 200;
        const { container } = monter();
        expect(visibles(container)).toEqual(["Outil", "Type"]);
        expect(container.querySelector("[data-tableau]")!.className).toContain("overflow-x-auto");
    });
});
