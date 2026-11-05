// @vitest-environment node
/**
 * [.mark] N4 : la palette adoucie (décision 18, validée par Evan le 04/11) et « plus aucun orange » (décision 15).
 *
 * Trois questions, et seulement elles :
 *   1. Un seul rouge d'état (#dd4949) en clair, des jetons d'état pâles, le violet de Claude Code, dans les deux thèmes ?
 *   2. Un fichier de `ui/src` porte-t-il un orange ou un ambre (jeton, classe Tailwind, couleur écrite) ?
 *   3. Les couleurs d'identité (sélecteur d'espace, « Relation client », transitions du graphe, tuiles, étiquettes) sont-elles intactes ?
 */
import { readdirSync, readFileSync, statSync } from "node:fs";
import { join, relative, sep } from "node:path";

import { describe, expect, it } from "vitest";

const RACINE = join(__dirname, "..", "..", "..");
const css = () => readFileSync(join(RACINE, "app", "mark-theme.css"), "utf8").replace(/\/\*[\s\S]*?\*\//g, "");
const clair = () => css().match(/:root\s*\{[^}]*\}/)?.[0] ?? "";
const sombre = () => css().match(/\.dark\s*\{[^}]*\}/)?.[0] ?? "";
const jeton = (bloc: string, nom: string) => bloc.match(new RegExp(`${nom}:\s*([^;]+);`))?.[1].trim();

/** Teinte (0 à 360), saturation et valeur d'un #rrggbb. */
function hsv(hex: string): { h: number; s: number; v: number } {
    const [r, g, b] = [1, 3, 5].map((i) => parseInt(hex.slice(i, i + 2), 16) / 255);
    const max = Math.max(r, g, b);
    const d = max - Math.min(r, g, b);
    let h = 0;
    if (d) h = max === r ? ((g - b) / d) % 6 : max === g ? (b - r) / d + 2 : (r - g) / d + 4;
    return { h: ((h * 60) + 360) % 360, s: max ? d / max : 0, v: max };
}
/** Orange ou ambre : teinte 15 à 50, assez saturée et claire pour se voir (le brun d'une étiquette et le jaune de surlignage restent hors champ). */
export const estOrange = (hex: string) => {
    const { h, s, v } = hsv(hex);
    return h >= 15 && h <= 50 && s > 0.45 && v > 0.6;
};

const PALETTES_ORANGE = /(?<![\w-])(?:bg|text|border|ring|from|to|via|fill|stroke|outline|divide|shadow|decoration|accent)-(?:orange|amber)-/;

function fichiers(dossier: string): string[] {
    return readdirSync(dossier).flatMap((nom) => {
        const chemin = join(dossier, nom);
        if (statSync(chemin).isDirectory()) return nom === "client" ? [] : fichiers(chemin);
        return /\.(ts|tsx|css)$/.test(nom) && !/\.test\.(ts|tsx)$/.test(nom) ? [chemin] : [];
    });
}

/** Les orange et ambres trouvés dans un source : jetons, classes, couleurs écrites (les commentaires ne comptent pas). */
export function orangesDe(source: string): string[] {
    const code = source.replace(/\/\*[\s\S]*?\*\//g, "").replace(/(^|[^:"'`])\/\/.*$/gm, "$1");
    const trouve: string[] = [];
    for (const m of code.matchAll(/#[0-9a-fA-F]{6}\b/g)) if (estOrange(m[0])) trouve.push(m[0]);
    for (const m of code.matchAll(new RegExp(PALETTES_ORANGE.source, "g"))) trouve.push(m[0]);
    return trouve;
}

describe("[.mark] N4 : palette adoucie (décision 18)", () => {
    it("un seul rouge d'état en clair, #dd4949, partout où un rouge plein sert", () => {
        for (const nom of ["--destructive", "--signal-danger", "--pastille-urgente", "--gravite-grave", "--notif-echec", "--source-inconnue", "--demarrage-etincelle"]) {
            expect(jeton(clair(), nom), nom).toBe("#dd4949");
        }
    });

    it("les traits sont des noirs transparents et les états ont leur fond pâle, en clair et en sombre", () => {
        expect(jeton(clair(), "--border")).toBe("rgb(15 15 16 / 0.075)");
        for (const bloc of [clair(), sombre()]) {
            for (const nom of ["--ok", "--ok-soft", "--ok-ink", "--danger-soft", "--danger-ink", "--info-soft", "--info-ink", "--neutral-soft", "--neutral-ink", "--link"]) {
                expect(jeton(bloc, nom), nom).toBeTruthy();
            }
        }
    });

    it("le sigle >_ de Claude Code a son violet : jeton `claude`, en clair et en sombre", () => {
        expect(jeton(clair(), "--claude")).toBe("#6b4fd8");
        expect(jeton(clair(), "--claude-soft")).toBeTruthy();
        expect(jeton(sombre(), "--claude")).toBe("#b3a2f5");
        expect(jeton(sombre(), "--claude-soft")).toBeTruthy();
    });

    it("l'avertissement n'est plus orange : --signal-warn prend le violet, dans les deux thèmes", () => {
        for (const bloc of [clair(), sombre()]) {
            const v = jeton(bloc, "--signal-warn") ?? "";
            expect(v).toMatch(/^#[0-9a-f]{6}$/);
            expect(estOrange(v), v).toBe(false);
            expect(hsv(v).h).toBeGreaterThan(240);
        }
    });

    it("les couleurs d'identité restent intactes (décision 18)", () => {
        const identite: Record<string, string> = {
            "--marque-relation": "#e5486b", // « Relation client » : le framboise du sélecteur d'espace
            "--violet-relation": "#7c5cdb",
            "--node-start": "#15803d", // types de nœud du graphe
            "--node-end": "#c62f35",
            "--node-global": "#7c3aed",
            "--demarrage-agent": "#3d8fe6", // tuiles de démarrage du builder
            "--demarrage-amelioration": "#7c5cdb",
            "--demarrage-test": "#1a9e5c",
            "--demarrage-fichier": "#d6457a",
            "--famille-outil": "#334155", // étiquettes d'objets
            "--famille-etape": "#7e22ce",
            "--famille-agent": "#1d4ed8",
            "--famille-equipe": "#4d7c0f",
            "--famille-document": "#6b4f3a",
            "--famille-phrase": "#a21caf",
            "--acc": "#3d8fe6",
        };
        for (const [nom, valeur] of Object.entries(identite)) expect(jeton(clair(), nom), nom).toBe(valeur);
    });
});

describe("[.mark] N4 : plus aucun orange, nulle part (décision 15)", () => {
    it("le détecteur reconnaît un orange et un ambre, et laisse passer le reste (preuve de l'outil, R7)", () => {
        expect(orangesDe('const c = "#e08a00"; const d = "#f59e0b";')).toEqual(["#e08a00", "#f59e0b"]);
        expect(orangesDe('className="text-amber-500 bg-orange-100/40"')).toEqual(["text-amber-", "bg-orange-"]);
        expect(orangesDe('const v = "#6d3fc0", r = "#dd4949", s = "#fef08a", b = "#6b4f3a", k = "#0f0f10"; // #e08a00 en commentaire')).toEqual([]);
    });

    it("aucun orange ni ambre dans ui/src (jetons, classes Tailwind, couleurs écrites)", () => {
        const trouve = fichiers(RACINE).flatMap((chemin) =>
            orangesDe(readFileSync(chemin, "utf8")).map((o) => `${relative(RACINE, chemin).split(sep).join("/")} : ${o}`),
        );
        expect(trouve).toEqual([]);
    });
});
