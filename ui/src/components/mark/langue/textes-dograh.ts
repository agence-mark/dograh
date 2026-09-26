/**
 * [.mark] The English texts of Dograh's own screens, to translate over the top
 * (chantier reorganisation-ecran-reglages, step 8, convention T3).
 *
 * Dograh's files are never edited to translate. Their texts are read here, with
 * the same parser as our two-language check (`textes-une-langue.ts`), and each
 * one gets its French in `dictionnaire-dograh.json`. The page swaps them at
 * display (`TraductionDograh.tsx`).
 *
 * Used twice:
 *   - by `dictionnaire-dograh.test.ts`, which fails while a text has no French;
 *   - by the fork's tool `socle-agent-vocal/dograh/outils/lister-non-traduits.mjs`,
 *     run at every upgrade on the upstream, which prints what to add.
 *
 * ⛔ No relative import here: Node reads this file directly (type stripping)
 * when the tool runs, and the app's compiler refuses the `.ts` extension that
 * Node would need. The reader is handed in instead.
 */
import { readdirSync, readFileSync, statSync } from "node:fs";
import { join, relative } from "node:path";

/** `textesUneLangue` of `textes-une-langue.ts`, handed in by the caller (see above). */
type Lecteur = (fichier: string, source: string) => Array<{ texte: string; ligne: number }>;

/** Where Dograh's screens live, from `ui/`. Our own screens are checked by T2. */
const RACINES = ["src/app", "src/components", "src/context", "src/hooks", "src/lib"];
const EXCLUS = [/[\\/]components[\\/]mark[\\/]/, /\.test\.tsx?$/, /[\\/]__tests__[\\/]/];

const ENTITES: Record<string, string> = {
    "&apos;": "'",
    "&quot;": '"',
    "&amp;": "&",
    "&lt;": "<",
    "&gt;": ">",
    "&nbsp;": " ",
    "&rarr;": "→",
    "&larr;": "←",
    "&laquo;": "«",
    "&raquo;": "»",
    "&hellip;": "…",
    "&mdash;": "—",
    "&ndash;": "–",
    "&bull;": "•",
    "&middot;": "·",
    "&copy;": "©",
    "&ldquo;": "“",
    "&rdquo;": "”",
    "&lsquo;": "‘",
    "&rsquo;": "’",
};

/**
 * A text the way the page shows it, and the way the dictionary keys it:
 * entities decoded, spaces collapsed, trimmed. The page side applies the same.
 */
export const normaliser = (texte: string): string =>
    texte
        .replace(/&[a-z]+;/g, (entite) => ENTITES[entite] ?? entite)
        .replace(/[\s ]+/g, " ")
        .trim();

const fichiers = (dossier: string): string[] =>
    readdirSync(dossier).flatMap((nom) => {
        const chemin = join(dossier, nom);
        if (statSync(chemin).isDirectory()) return fichiers(chemin);
        return /\.tsx?$/.test(nom) ? [chemin] : [];
    });

export interface TexteDograh {
    texte: string;
    /** Where it is written, « file:line », the first place found. */
    ou: string;
}

/** Every English text of Dograh's screens, once each, sorted. */
export const textesDograh = (racineUi: string, lire: Lecteur): TexteDograh[] => {
    const vus = new Map<string, string>();
    for (const racine of RACINES) {
        for (const chemin of fichiers(join(racineUi, racine))) {
            if (EXCLUS.some((motif) => motif.test(chemin))) continue;
            const nom = relative(racineUi, chemin).replace(/\\/g, "/");
            for (const trouve of lire(nom, readFileSync(chemin, "utf8"))) {
                const texte = normaliser(trouve.texte);
                if (texte && !vus.has(texte)) vus.set(texte, `${nom}:${trouve.ligne}`);
            }
        }
    }
    return [...vus.entries()].map(([texte, ou]) => ({ texte, ou })).sort((a, b) => a.texte.localeCompare(b.texte));
};

/** What the dictionary lacks. */
export const nonTraduits = (racineUi: string, lire: Lecteur, dictionnaire: Record<string, string>): TexteDograh[] =>
    textesDograh(racineUi, lire).filter(({ texte }) => !dictionnaire[texte]?.trim());
