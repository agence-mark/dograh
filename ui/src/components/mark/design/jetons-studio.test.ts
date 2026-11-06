// @vitest-environment node
/**
 * [.mark] Les jetons du nouveau design (U1) : bleu #3d8fe6, encre #0f0f10, Switzer hébergée dans ui/public,
 * clair par défaut, aucune police ni script chargé d'un site tiers, jetons des marques dans les deux thèmes.
 */
import { existsSync, readFileSync } from "node:fs";
import { join } from "node:path";

import { describe, expect, it } from "vitest";

const UI = join(__dirname, "..", "..", "..", "..");
const css = () => readFileSync(join(UI, "src", "app", "mark-theme.css"), "utf8").replace(/\/\*[\s\S]*?\*\//g, "");
const bloc = (selecteur: RegExp) => css().match(selecteur)?.[0] ?? "";

describe("[.mark] jetons du studio", () => {
    it("le bleu et l'encre de la maquette", () => {
        const clair = bloc(/:root\s*\{[^}]*--primary:[^}]*\}/);
        expect(clair).toMatch(/--primary:\s*#0f0f10/);
        expect(clair).toMatch(/--acc:\s*#3d8fe6/);
        expect(clair).toMatch(/--radius:\s*0\.625rem/);
    });

    it("Switzer est hébergée dans ui/public/fonts, et aucune police ne vient d'un site tiers", () => {
        const source = css();
        const fichiers = [...source.matchAll(/url\("(\/fonts\/Switzer-\d+\.woff2)"\)/g)].map((m) => m[1]);
        expect(fichiers.length).toBe(4);
        for (const f of fichiers) expect(existsSync(join(UI, "public", f))).toBe(true);
        expect(source).not.toMatch(/https?:\/\/|fontshare|googleapis/);
        const layout = readFileSync(join(UI, "src", "app", "layout.tsx"), "utf8");
        expect(layout).not.toMatch(/fontshare|Geist\b|fonts\.googleapis/);
        expect(source).toMatch(/--font-geist-sans:\s*"Switzer"/);
    });

    it("les jetons des marques existent en clair et en sombre", () => {
        for (const jeton of [
            "--marque-neutre", "--marque-succes", "--marque-attention", "--marque-danger", "--marque-plein",
            "--pastille-urgente", "--point-publie", "--gravite-grave", "--etat-fait",
        ]) {
            expect(bloc(/:root\s*\{[^}]*--primary:[^}]*\}/), jeton).toContain(`${jeton}:`);
            expect(bloc(/\.dark\s*\{[^}]*\}/), jeton).toContain(`${jeton}:`);
        }
    });

    it("jamais d'orange : aucun jeton de marque ne porte la teinte orange", () => {
        for (const m of css().matchAll(/--(?:marque|point|gravite|pastille)[\w-]*:\s*(#[0-9a-f]{6})/gi)) {
            const n = parseInt(m[1].slice(1), 16);
            const [r, g, b] = [n >> 16, (n >> 8) & 255, n & 255];
            const orange = r > 200 && g > 100 && g < 200 && b < 90;
            expect(orange, m[0]).toBe(false);
        }
    });
});
