import { readdirSync, readFileSync, statSync } from "node:fs";
import { join, relative, sep } from "node:path";

import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { Curseur } from "./curseur";

const RACINE = join(__dirname, "..", "..");

function fichiers(dossier: string): string[] {
    return readdirSync(dossier).flatMap((nom) => {
        const chemin = join(dossier, nom);
        if (nom === "client" || nom === "node_modules") return [];
        return statSync(chemin).isDirectory() ? fichiers(chemin) : /\.(tsx|ts)$/.test(nom) && !/\.test\./.test(nom) ? [chemin] : [];
    });
}

describe("le curseur à glisser commun (T5)", () => {
    it("donne la part remplie au rail, bornée aux limites", () => {
        const { rerender } = render(<Curseur aria-label="vitesse" min={0} max={200} value={50} onChange={() => {}} />);
        const c = screen.getByLabelText("vitesse") as HTMLInputElement;
        expect(c.type).toBe("range");
        expect(c.classList.contains("curseur")).toBe(true);
        expect(c.style.getPropertyValue("--pct")).toBe("25%");
        rerender(<Curseur aria-label="vitesse" min={0} max={200} value={500} onChange={() => {}} />);
        expect(c.style.getPropertyValue("--pct")).toBe("100%");
    });

    it("un seul composant : aucun curseur à glisser n'est écrit ailleurs que dans components/ui/curseur.tsx", () => {
        const hors = fichiers(RACINE)
            .filter((f) => /type\s*[=:]\s*\{?\s*["']range["']/.test(readFileSync(f, "utf8")))
            .map((f) => relative(RACINE, f).split(sep).join("/"))
            .filter((f) => f !== "components/ui/curseur.tsx");
        expect(hors).toEqual([]);
    });
});
