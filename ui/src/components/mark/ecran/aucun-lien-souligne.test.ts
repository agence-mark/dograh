/**
 * [.mark] Clôture, point 2 : « survol en gras, jamais souligné » (règle d'Evan, bonnes-pratiques-ecran). Aucun lien ni texte de
 * l'écran ne porte la classe `underline` (ni `hover:underline`, ni `underline-offset-*`). Le repère d'un lien est la graisse
 * (`font-medium`, `hover:font-semibold`) ; les champs `.lead-form-underline` (nom de classe du formulaire du site) ne sont pas des liens.
 */
import { readdirSync, readFileSync, statSync } from "node:fs";
import { join, relative, resolve } from "node:path";

import { describe, expect, it } from "vitest";

const RACINE = resolve(__dirname, "../../..");
const SOULIGNE = /(?<![\w-])(?:[\w-]+:)*(?:no-)?underline(?:-offset-[\w[\].]+)?(?![\w-])/g;

function fichiers(dossier: string): string[] {
    return readdirSync(dossier).flatMap((nom) => {
        const chemin = join(dossier, nom);
        if (statSync(chemin).isDirectory()) return nom === "client" ? [] : fichiers(chemin);
        return /\.(tsx|ts)$/.test(nom) && !/\.test\.tsx?$/.test(nom) ? [chemin] : [];
    });
}

describe("aucun lien souligné", () => {
    it("ne laisse aucune classe `underline` dans les composants et les pages de l'écran", () => {
        const trouves: string[] = [];
        for (const fichier of fichiers(RACINE)) {
            readFileSync(fichier, "utf8")
                .split("\n")
                .forEach((ligne, i) => {
                    if (ligne.replace(/lead-form-underline/g, "").match(SOULIGNE)) trouves.push(`${relative(RACINE, fichier)}:${i + 1}`);
                });
        }
        expect(trouves).toEqual([]);
    });

    it("garde la variante `link` du bouton sans soulignement au survol", () => {
        const bouton = readFileSync(join(RACINE, "components/ui/button.tsx"), "utf8");
        expect(bouton).toMatch(/link:\s*"[^"]*hover:font-semibold/);
    });
});
