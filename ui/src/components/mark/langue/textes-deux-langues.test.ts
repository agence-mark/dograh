/**
 * [.mark] Blocking: no text of our screens in one language only (convention
 * T2; chantier reorganisation-ecran-reglages, step 7).
 *
 * Reads every screen file of `components/mark/` (tests and test references
 * aside) with `textes-une-langue.ts`. A text a person reads that does not go
 * through a `Texte` ({ en, fr }) fails here, with its file and line.
 *
 * ⛔ Exceptions: `SectionLexiqueMetier.tsx`, by decision of the plan (the
 * lexicon chantier rewrites it; its texts are put in two languages when that
 * chantier is merged, and the exception is removed then), and the old Speech
 * Tuning card with its parts, off screen since step 4 (see below).
 */
import { readdirSync, readFileSync, statSync } from "node:fs";
import { join, relative } from "node:path";

import { describe, expect, it } from "vitest";

import { textesUneLangue } from "./textes-une-langue";

const RACINE = join(process.cwd(), "src/components/mark");
const EXCEPTIONS = new Set([
    "SectionLexiqueMetier.tsx",
    // Off screen since step 4: the old Speech Tuning card and its six parts,
    // called only by Dograh's old settings cards, themselves unused. Their
    // deletion is proposed to Evan (A-VALIDER); nothing is deleted without his go.
    "SectionReglagesPipecat.tsx",
    "SectionTranscription.tsx",
    "SectionTourDeParole.tsx",
    "SectionCoupureMicro.tsx",
    "SectionAccueilEtSilence.tsx",
    "SectionRelance.tsx",
    "SectionVoix.tsx",
]);
// The same, for a card that shares its file with what the themes still use.
const COMPOSANTS_HORS_ECRAN = new Set([
    "SectionHorairesOuverture.tsx#SectionHorairesOuverture",
    "SectionAdresseEtablissement.tsx#SectionAdresseEtablissement",
    "SectionFiche.tsx#SectionFiche",
]);

const fichiersEcran = (dossier: string): string[] =>
    readdirSync(dossier).flatMap((nom) => {
        const chemin = join(dossier, nom);
        if (statSync(chemin).isDirectory()) return nom === "references" ? [] : fichiersEcran(chemin);
        return /\.tsx$/.test(nom) && !/\.test\.tsx$/.test(nom) ? [chemin] : [];
    });

describe("[.mark] texts of our screens, in two languages", () => {
    it("finds a one-language text, and leaves code and technical names alone", () => {
        const trouves = textesUneLangue(
            "exemple.tsx",
            `const A = () => (
                <div title={t({ en: "Ok", fr: "Ok" })}>
                    <p>Save the theme</p>
                    <span>{enCours ? "Saving..." : t({ en: "Save", fr: "Enregistrer" })}</span>
                    <code>{"{{adresse_etablissement}}"} 24/12/2026 : fermé</code>
                    <input placeholder="Enter a value" />
                    <input placeholder="+15551234567" />
                    {t({ en: "Two languages", fr: "Deux langues" })}
                </div>
            );
            toast.success("Saved");`,
        );
        expect(trouves.map((t) => t.texte)).toEqual(["Save the theme", "Saving...", "Enter a value", "Saved"]);
    });

    it("finds none in components/mark", () => {
        const trouves = fichiersEcran(RACINE)
            .filter((chemin) => !EXCEPTIONS.has(chemin.split(/[\\/]/).pop()!))
            .flatMap((chemin) => textesUneLangue(relative(RACINE, chemin), readFileSync(chemin, "utf8")))
            .filter((t) => !COMPOSANTS_HORS_ECRAN.has(`${t.fichier.split(/[\\/]/).pop()}#${t.composant}`));
        expect(trouves.map((t) => `${t.fichier}:${t.ligne}  ${t.texte}`)).toEqual([]);
    });
});
