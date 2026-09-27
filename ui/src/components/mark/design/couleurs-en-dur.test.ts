// @vitest-environment node
/**
 * [.mark] No colour written by hand on Dograh's screen (chantier
 * refonte-design-dograh, D11 and D12).
 *
 * The question this file answers, and only this one:
 *
 *     Does a file of `ui/src` paint a colour of its own, instead of taking it
 *     from the .mark tokens (`app/mark-theme.css`)?
 *
 * Why it exists
 * -------------
 * The .mark look is black, white and grey, with colour kept for signals only
 * (a dot, an icon). It holds through the tokens alone: one `text-blue-600`
 * or one `bg-[#1a1a1a]` puts Dograh's old palette back on one screen, and no
 * other test notices. At every upgrade on upstream Dograh, this test LISTS the
 * hand-written colours upstream brought back, file by file.
 *
 * What counts as a colour written by hand
 * ---------------------------------------
 *   - a Tailwind class of a named palette with a shade (`text-blue-600`,
 *     `hover:bg-gray-100`, `border-emerald-500/40`);
 *   - a hexadecimal colour in a string or an arbitrary value (`"#3B82F6"`,
 *     `bg-[#1a1a1a]`);
 *   - an `rgb()` / `rgba()` literal that is not a grey (a black shadow is fine),
 *     an `hsl()` with a saturation, an `oklch()` with a chroma.
 *
 * Kept on purpose (D11): the two report charts (series must stay apart), the
 * test files, and hex values that are DATA rather than look (see HEX_DONNEES).
 *
 * Not covered: `.css` files. Dograh's `globals.css` is left untouched on
 * purpose (D10) and keeps its own colours; `mark-theme.css` overrides them.
 */
import { readdirSync, readFileSync, statSync } from "node:fs";
import { join, relative, sep } from "node:path";

import { describe, expect, it } from "vitest";

const RACINE = join(__dirname, "..", "..", "..");

/** The .mark palette (plan D3), light and dark. The only hex values a file may hold. */
export const PALETTE_MARK = new Set(
    [
        "#ffffff", "#0e0e0e", "#0a0a0a", "#f5f5f5", "#141414", "#f4f4f4", "#1f1f1f",
        "#737373", "#9a9a9a", "#1a1a1a", "#ebebeb", "#242424", "#e5e5e5", "#2c2c2c",
        "#a3a3a3", "#5c5c5c", "#d93036", "#f16a6e", "#fafafa", "#efefef", "#222222",
        "#121212", "#d4d4d4", "#3a3a3a", "#22a355", "#3ecf7a", "#e08a00", "#f0a93a",
        "#e5484d", "#b4b4b4", "#2a2a2a",
    ],
);

/** Files left with their colours (D11). Path relative to `ui/src`, forward slashes. */
const FICHIERS_EXCLUS = new Set([
    "app/reports/components/DurationChart.tsx",
    "app/reports/components/DispositionChart.tsx",
]);

const COULEURS_DES_OUTILS = new Set(["#3b82f6", "#ef4444", "#10b981", "#0ea5e9", "#f59e0b", "#8b5cf6", "#6b7280"]);

/**
 * Hex values that are data, not look. Each one is saved somewhere and read back
 * by something that is not this screen; changing it changes the data.
 */
const HEX_DONNEES: Record<string, { valeurs: Set<string>; pourquoi: string }> = {
    "app/workflow/[workflowId]/components/EmbedDialog.tsx": {
        valeurs: new Set(["#10b981"]),
        pourquoi: "default colour of the widget button put on the client's own website, saved in its settings",
    },
    // A tool's `iconColor` is saved as `icon_color` when the tool is created, and
    // read back before anything else: left as Dograh wrote it (decision for Evan).
    "app/tools/config.tsx": { valeurs: COULEURS_DES_OUTILS, pourquoi: "saved as icon_color" },
    "app/tools/page.tsx": { valeurs: COULEURS_DES_OUTILS, pourquoi: "saved as icon_color" },
    "app/tools/[toolUuid]/page.tsx": { valeurs: COULEURS_DES_OUTILS, pourquoi: "fallback of icon_color" },
    "components/flow/ToolSelector.tsx": { valeurs: COULEURS_DES_OUTILS, pourquoi: "fallback of icon_color" },
};

/**
 * Files whose hex values must be hex (a third-party parser) and so are aligned
 * on the .mark palette instead of a token.
 */
const HEX_ALIGNES_SUR_LA_PALETTE = new Set([
    "app/handler/[...stack]/stack-theme.ts", // Stack Auth's theme parser takes hex only
]);

const PALETTES =
    "slate|gray|zinc|neutral|stone|red|orange|amber|yellow|lime|green|emerald|teal|cyan|sky|blue|indigo|violet|purple|fuchsia|pink|rose";
const CLASSE_PALETTE = new RegExp(
    `(?<![\\w-])(?:bg|text|border|border-[trblxyse]|ring|ring-offset|from|to|via|fill|stroke|outline|divide|shadow|decoration|placeholder|caret|accent)-(?:${PALETTES})-(?:50|[1-9]00|950)(?![\\w-])`,
    "g",
);
// A hex colour opens a string, an arbitrary value or a CSS value (`1px solid #fff`);
// never an HTML entity (`&#9888;`). A `#300` in prose is kept out by stripping comments.
const HEX = /(?<=["'`[(:,\s])(?<![&\w])#(?:[0-9a-fA-F]{8}|[0-9a-fA-F]{6}|[0-9a-fA-F]{3,4})(?![0-9a-zA-Z_])/g;
const RGB = /rgba?\(\s*(\d+)[\s,]+(\d+)[\s,]+(\d+)/g;
// hsl() with a saturation, oklch() with a chroma: a colour, not a grey.
const HSL = /hsla?\(\s*[\d.]+(?:deg)?[\s,]+([\d.]+)%/g;
const OKLCH = /oklch\(\s*[\d.]+%?\s+([\d.]+)/g;

export type Trouvaille = { fichier: string; ligne: number; valeur: string };

function fichiers(dossier: string): string[] {
    return readdirSync(dossier).flatMap((nom) => {
        const chemin = join(dossier, nom);
        if (statSync(chemin).isDirectory()) return fichiers(chemin);
        return /\.(ts|tsx)$/.test(nom) ? [chemin] : [];
    });
}

const estUnTest = (chemin: string) => /\.test\.(ts|tsx)$/.test(chemin) || chemin.includes("/__tests__/");

/** Every hand-written colour of one file's source. Exported for the test's own proof. */
export function couleursEnDur(fichier: string, source: string): Trouvaille[] {
    const trouve: Trouvaille[] = [];
    // Windows checkouts end lines with \r\n: a `.` never crosses the \r, so split on both.
    source.split(/\r?\n/).forEach((texte, i) => {
        // A comment is not paint: `// blue-500 when selected`, `{/* issue #300 */}`.
        const code = texte.replace(/\/\*.*?\*\//g, "").replace(/(^|[^:"'`])\/\/.*$/, "$1");
        const noter = (valeur: string) => trouve.push({ fichier, ligne: i + 1, valeur });
        for (const m of code.matchAll(CLASSE_PALETTE)) noter(m[0]);
        for (const m of code.matchAll(HEX)) {
            const hex = m[0].toLowerCase();
            if (HEX_DONNEES[fichier]?.valeurs.has(hex)) continue;
            if (HEX_ALIGNES_SUR_LA_PALETTE.has(fichier) && PALETTE_MARK.has(hex)) continue;
            noter(m[0]);
        }
        for (const m of code.matchAll(RGB)) {
            if (m[1] === m[2] && m[2] === m[3]) continue; // a grey or a black shadow
            noter(m[0] + ")");
        }
        for (const m of code.matchAll(HSL)) if (parseFloat(m[1]) > 0) noter(m[0] + ")");
        for (const m of code.matchAll(OKLCH)) if (parseFloat(m[1]) > 0) noter(m[0] + ")");
    });
    return trouve;
}

function relever(): Trouvaille[] {
    return fichiers(RACINE).flatMap((chemin) => {
        const fichier = relative(RACINE, chemin).split(sep).join("/");
        if (estUnTest(fichier) || FICHIERS_EXCLUS.has(fichier)) return [];
        return couleursEnDur(fichier, readFileSync(chemin, "utf8"));
    });
}

describe("[.mark] no colour written by hand (D11, D12)", () => {
    it("recognises what it is meant to catch, and only that (proof of the tool, R7)", () => {
        const rouge = [
            'className="text-blue-600 hover:bg-gray-100 dark:border-emerald-500/40"',
            'className="bg-[#1a1a1a] border-[#2a2a2a]"',
            "stroke: '#3B82F6',",
            "boxShadow: '0 0 0 2px rgba(59,130,246,0.5)'",
            "iconColor: \"#8B5CF6\",",
            'border: "1px solid #3B82F6"',
            "boxShadow: `0 0 8px #3b82f6`",
            "color: 'hsl(217 91% 60%)'",
            "color: 'oklch(0.6 0.2 250)'",
        ].join("\n");
        expect(couleursEnDur("x.tsx", rouge).map((t) => t.valeur)).toEqual([
            "text-blue-600", "bg-gray-100", "border-emerald-500",
            "#1a1a1a", "#2a2a2a", "#3B82F6", "rgba(59,130,246)", "#8B5CF6",
            "#3B82F6", "#3b82f6", "hsl(217 91%)", "oklch(0.6 0.2)",
        ]);
        const vert = [
            'className="text-muted-foreground bg-(--surface) border-border"',
            "// another tab) its re-render throws React #300",
            "{/* see issue #300 */}",
            "color: 'oklch(0.5 0 0)'",
            "background: 'hsl(var(--sidebar-border))'",
            "&#9888; Off until",
            "? '#3B82F6'  // blue-500 when selected",
            "boxShadow: '0 1px 2px rgb(0 0 0 / 0.1)'",
            'className="text-foreground-400 my-blue-500-thing"',
        ].join("\n");
        // Line 4 holds a real hex before its comment: only the comment is ignored.
        expect(couleursEnDur("x.tsx", vert).map((t) => t.valeur)).toEqual(["#3B82F6"]);
        expect(couleursEnDur("app/handler/[...stack]/stack-theme.ts", 'primary: "#0a0a0a",')).toEqual([]);
        expect(couleursEnDur("app/handler/[...stack]/stack-theme.ts", 'primary: "#fbbf24",')).toHaveLength(1);
        expect(couleursEnDur("app/tools/config.tsx", 'iconColor: "#3B82F6",')).toEqual([]);
        expect(couleursEnDur("app/tools/config.tsx", 'iconColor: "#123456",')).toHaveLength(1);
    });

    it("ui/src holds no colour outside the .mark tokens", () => {
        const trouve = relever();
        const parFichier = new Map<string, string[]>();
        for (const t of trouve) {
            parFichier.set(t.fichier, [...(parFichier.get(t.fichier) ?? []), `${t.ligne}: ${t.valeur}`]);
        }
        const rapport = [...parFichier]
            .sort((a, b) => b[1].length - a[1].length)
            .map(([f, l]) => `${f} (${l.length})\n    ${l.slice(0, 8).join("\n    ")}${l.length > 8 ? "\n    …" : ""}`)
            .join("\n");
        expect(
            trouve.length,
            `${trouve.length} colours written by hand in ${parFichier.size} files. Replace each one by a token ` +
                `(table D11 of the design plan):\n${rapport}`,
        ).toBe(0);
    });
});
