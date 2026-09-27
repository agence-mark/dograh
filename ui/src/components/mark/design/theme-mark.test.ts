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
    });

    it("mark-theme.css removes the watermark, the card weave and the sidebar scrollbar (D8)", () => {
        const css = sansCommentaires(theme());
        expect(css).toMatch(/--brand-imprint:\s*none/);
        expect(css).toMatch(/\.card-weave[^{]*\{[^}]*background-image:\s*none/);
        expect(css).toMatch(/\[data-slot="sidebar-content"\][^{]*\{[^}]*scrollbar-width:\s*none/);
        expect(css).toMatch(/\[data-slot="sidebar-content"\]::-webkit-scrollbar[^{]*\{[^}]*display:\s*none/);
    });

    it("mark-theme.css writes its rules outside any @layer, so they win over Tailwind (D10)", () => {
        expect(sansCommentaires(theme())).not.toMatch(/@layer\b/);
    });

    it("the orange call to action is gone: --cta is black in light, off-white in dark (D3)", () => {
        const css = sansCommentaires(theme());
        const bloc = (selecteur: RegExp) => css.match(selecteur)?.[0] ?? "";
        expect(bloc(/:root\s*\{[^}]*\}/)).toMatch(/--cta:\s*#0a0a0a/);
        expect(bloc(/\.dark\s*\{[^}]*\}/)).toMatch(/--cta:\s*#f5f5f5/);
    });
});
