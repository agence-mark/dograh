// @vitest-environment node
/**
 * [.mark] The .mark look is loaded, on top of Dograh's (chantier
 * refonte-design-dograh, D4, D8, D10, D12).
 *
 * The question this file answers, and only this one:
 *
 *     After an upgrade on upstream Dograh, is the .mark look still there, or
 *     is the screen back to Dograh's own (dark, orange, "dograh" watermark)?
 *
 * Why it exists
 * -------------
 * The whole look hangs on one line of `app/layout.tsx` and one file of ours,
 * `app/mark-theme.css`. A merge that drops the line, or moves it above
 * `globals.css` (so Dograh's rules win), brings Dograh's look back silently:
 * every page still works, nothing else turns red.
 */
import { readFileSync } from "node:fs";
import { join } from "node:path";

import { describe, expect, it } from "vitest";

const APP = join(__dirname, "..", "..", "..", "app");
const layout = () => readFileSync(join(APP, "layout.tsx"), "utf8");
const theme = () => readFileSync(join(APP, "mark-theme.css"), "utf8");

/** The CSS without its comments, so a rule written in a comment does not count. */
const sansCommentaires = (css: string) => css.replace(/\/\*[\s\S]*?\*\//g, "");

describe("[.mark] the .mark look is loaded (D10, D12)", () => {
    it("layout.tsx loads mark-theme.css right after globals.css", () => {
        const imports = [...layout().matchAll(/^import\s+["']([^"']+\.css)["'];?\s*$/gm)].map((m) => m[1]);
        expect(imports).toEqual(["./globals.css", "./mark-theme.css"]);
    });

    it("the screen opens in light by default (D4)", () => {
        const fournisseur = layout().match(/<ThemeProvider\b[^>]*>/)?.[0] ?? "";
        expect(fournisseur).toMatch(/defaultTheme="light"/);
        // The anti-flash script agrees: only a stored 'dark' opts in, never the default.
        const script = layout().match(/__html:\s*`([\s\S]*?)`/)?.[1] ?? "";
        expect(script).toMatch(/theme === 'dark'\)\s*\{\s*document\.documentElement\.classList\.add\('dark'\)/);
        expect(script).not.toMatch(/theme === 'light'/);
        expect(layout()).not.toMatch(/<html[^>]*className="dark"/);
    });

    it("mark-theme.css removes the watermark, the card weave and the sidebar scrollbar (D8)", () => {
        const css = sansCommentaires(theme());
        expect(css).toMatch(/--brand-imprint:\s*none/);
        expect(css).toMatch(/\.card-weave[^{]*\{[^}]*background-image:\s*none/);
        expect(css).toMatch(/\[data-slot="sidebar-content"\][^{]*\{[^}]*scrollbar-width:\s*none/);
        expect(css).toMatch(/\[data-slot="sidebar-content"\]::-webkit-scrollbar[^{]*\{[^}]*display:\s*none/);
    });

    it("aucune surcharge de titres, de champs ni de traits d'icônes : ceux de la maquette (K1, 04/11)", () => {
        const css = sansCommentaires(theme());
        expect(css).not.toMatch(/h1[^{}]*\{/);
        expect(css).not.toMatch(/\[data-slot="input"\][^{]*\{[^}]*height/);
        expect(css).not.toMatch(/svg\.lucide/);
    });

    it("contrast decisions of 27/09 hold, sauf le bouton à bordure, repris de la maquette (K1): dark borders and fields are firmer, node types have colours", () => {
        const css = sansCommentaires(theme());
        const sombre = css.match(/\.dark\s*\{[^}]*\}/)?.[0] ?? "";
        expect(sombre).toMatch(/--border:\s*oklch\(1 0 0 \/ 10%\)/);
        expect(sombre).toMatch(/--input:\s*oklch\(1 0 0 \/ 15%\)/);
        for (const jeton of ["--node-start", "--node-end", "--node-global"]) expect(css).toMatch(new RegExp(`${jeton}:`));
        const bouton = readFileSync(join(APP, "..", "components", "ui", "button.tsx"), "utf8");
        const outline = bouton.match(/outline:\s*"([^"]*)"/)?.[1] ?? "";
        expect(outline).toMatch(/(^|\s)bg-background(\s|$)/);
    });

    it("mark-theme.css writes its rules outside any @layer, so they win over Tailwind (D10)", () => {
        expect(sansCommentaires(theme())).not.toMatch(/@layer\b/);
    });

    it("the orange call to action is gone: --cta is black in light, off-white in dark (D3)", () => {
        const css = sansCommentaires(theme());
        const bloc = (selecteur: RegExp) => css.match(selecteur)?.[0] ?? "";
        expect(bloc(/:root\s*\{[^}]*\}/)).toMatch(/--cta:\s*#0f1c2e/);
        expect(bloc(/\.dark\s*\{[^}]*\}/)).toMatch(/--cta:\s*oklch\(0\.922 0 0\)/);
    });

    it("le mode nuit (N4) déclare chaque jeton du mode clair, et prend ceux de base de la maquette", () => {
        const css = sansCommentaires(theme());
        const jetons = (bloc: string) => new Set([...bloc.matchAll(/(--[a-z0-9-]+):/g)].map((m) => m[1]));
        const clair = jetons(css.match(/:root\s*\{[^}]*\}/g)?.[0] ?? "");
        const sombre = css.match(/\.dark\s*\{[^}]*\}/)?.[0] ?? "";
        const declares = jetons(sombre);
        // --radius ne change pas de thème.
        const manquants = [...clair].filter((j) => j !== "--radius" && !declares.has(j));
        expect(manquants).toEqual([]);
        expect(sombre).toMatch(/--background:\s*oklch\(0\.145 0 0\)/);
        expect(sombre).toMatch(/--card:\s*oklch\(0\.205 0 0\)/);
        expect(sombre).toMatch(/--muted:\s*oklch\(0\.269 0 0\)/);
        expect(sombre).toMatch(/--sidebar:\s*oklch\(0\.205 0 0\)/);
    });

    it("the blue accent exists in both themes, and focus follows it (Evan, 27/09)", () => {
        const css = sansCommentaires(theme());
        const bloc = (selecteur: RegExp) => css.match(selecteur)?.[0] ?? "";
        const clair = bloc(/:root\s*\{[^}]*\}/);
        const sombre = bloc(/\.dark\s*\{[^}]*\}/);
        for (const jeton of ["--acc", "--acc-soft", "--acc-text", "--acc-fill", "--acc-line"]) {
            expect(clair).toMatch(new RegExp(`${jeton}:`));
            expect(sombre).toMatch(new RegExp(`${jeton}:`));
        }
        expect(clair).toMatch(/--acc:\s*#3d8fe6/);
        expect(sombre).toMatch(/--acc:\s*#5b97f5/);
        expect(clair).toMatch(/--ring:\s*#3d8fe6/);
        expect(clair).toMatch(/--sidebar-ring:\s*#3d8fe6/);
        expect(sombre).toMatch(/--ring:\s*#5b97f5/);
    });
});
