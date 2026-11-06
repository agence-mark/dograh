// @vitest-environment node
/**
 * [.mark] Les notifications passent par UN module (`notifier`, `15-notifications.md`).
 *
 * La question de ce fichier, et seulement celle-ci : un fichier de `ui/src` (hors le module et les tests) importe-t-il
 * `sonner` ou appelle-t-il `toast(` / `toast.xxx(` directement ? Si oui, sa notification échappe aux règles de durée,
 * de pile, de regroupement, de bouton et de « Détails » : le test échoue en le nommant.
 */
import { readdirSync, readFileSync, statSync } from "node:fs";
import { join, relative, sep } from "node:path";

import { describe, expect, it } from "vitest";

const RACINE = join(__dirname, "..", "..", "..");


function fichiers(dossier: string, sortie: string[] = []): string[] {
    for (const nom of readdirSync(dossier)) {
        const chemin = join(dossier, nom);
        if (statSync(chemin).isDirectory()) {
            if (nom === "client" || nom === "node_modules") continue;
            fichiers(chemin, sortie);
        } else if (/\.(ts|tsx)$/.test(nom) && !/\.test\.(ts|tsx)$/.test(nom)) {
            sortie.push(chemin);
        }
    }
    return sortie;
}

const sansCommentaires = (s: string) => s.replace(/\/\*[\s\S]*?\*\//g, "").replace(/^\s*\/\/.*$/gm, "");

const APPEL_DIRECT = /from\s+["']sonner["']|\btoast\s*\(|\btoast\.(success|error|warning|info|message|promise|loading|custom|dismiss)\s*\(/;

describe("aucun appel direct à sonner ou à toast", () => {
    const concernes = fichiers(RACINE)
        .map((f) => ({ f, rel: relative(RACINE, f).split(sep).join("/") }))
        .filter(({ rel }) => !rel.startsWith("components/mark/notifications/"));

    it("seul le module des notifications affiche une notification passagère", () => {
        const fautifs = concernes
            .filter(({ f, rel }) => APPEL_DIRECT.test(sansCommentaires(readFileSync(f, "utf8"))))
            .map(({ rel }) => rel);
        expect(fautifs).toEqual([]);
    });

});
