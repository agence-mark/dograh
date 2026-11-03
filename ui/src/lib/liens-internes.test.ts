/**
 * [.mark] L (fluidité) : un lien vers une page de l'écran passe par `next/link` (changement de page sans rechargement
 * complet, préchargement). Un `<a href="/...">` nu recharge tout le cadre. Seuls restent permis : un lien qui s'ouvre
 * dans un autre onglet (`target`), un fichier ou un point d'accès (`/api/`), une adresse extérieure.
 */
import { readdirSync, readFileSync, statSync } from "node:fs";
import { join } from "node:path";
import { describe, expect, it } from "vitest";

const RACINE = join(__dirname, "..");

function fichiers(dossier: string): string[] {
    return readdirSync(dossier).flatMap((nom) => {
        const chemin = join(dossier, nom);
        if (nom === "client" || nom === "node_modules") return [];
        if (statSync(chemin).isDirectory()) return fichiers(chemin);
        return /\.tsx$/.test(nom) && !/\.test\.tsx$/.test(nom) ? [chemin] : [];
    });
}

/** Les balises `<a ...>` (sur une ou plusieurs lignes) dont l'adresse commence par « / » et qui restent dans l'onglet. */
export function liensNus(source: string): string[] {
    const trouves: string[] = [];
    for (const m of source.matchAll(/<a\b[^>]*>/g)) {
        const balise = m[0];
        if (!/href=(\{\s*`\/|"\/|\{\s*"\/)/.test(balise)) continue;
        if (/target=/.test(balise) || /href=\{?\s*[`"]\/api\//.test(balise)) continue;
        trouves.push(balise.replace(/\s+/g, " ").slice(0, 90));
    }
    return trouves;
}

describe("liens internes", () => {
    it("le détecteur voit un lien nu et laisse passer un lien dans un autre onglet", () => {
        expect(liensNus('<a href="/connexion" className="x">')).toHaveLength(1);
        expect(liensNus("<a href={`/tools/${id}`}\n className=\"x\">")).toHaveLength(1);
        expect(liensNus('<a href={`/workflow/${id}`} target="_blank" rel="noreferrer">')).toHaveLength(0);
        expect(liensNus('<a href="https://docs.dograh.com" target="_blank">')).toHaveLength(0);
    });

    it("aucun lien interne de l'écran ne recharge la page", () => {
        const fautifs = fichiers(RACINE).flatMap((f) => liensNus(readFileSync(f, "utf8")).map((l) => `${f.slice(RACINE.length + 1)} : ${l}`));
        expect(fautifs).toEqual([]);
    });
});
