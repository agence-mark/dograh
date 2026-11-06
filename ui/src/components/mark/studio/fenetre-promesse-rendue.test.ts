// @vitest-environment node
/**
 * [.mark] R4 M4 : une fenêtre à champs (`FenetreChamps`, `SectionLue`, `BlocLu`) ne se ferme qu'au succès de l'enregistrement
 * et garde la saisie sinon. Cela suppose que son `onValider` RENDE la promesse : `onValider={() => void enregistrer()}` la jette
 * et la fenêtre se ferme toujours. Ce test interdit `void` devant l'enregistrement dans un `onValider`.
 */
import { readdirSync, readFileSync, statSync } from "node:fs";
import { join, relative, sep } from "node:path";

import { describe, expect, it } from "vitest";

const RACINE = join(__dirname, "..", "..", "..");

function fichiers(dossier: string, sortie: string[] = []): string[] {
    for (const nom of readdirSync(dossier)) {
        const chemin = join(dossier, nom);
        if (statSync(chemin).isDirectory()) fichiers(chemin, sortie);
        else if (/\.(ts|tsx)$/.test(nom) && !/\.test\.(ts|tsx)$/.test(nom)) sortie.push(chemin);
    }
    return sortie;
}

export function onValiderJetes(source: string): number[] {
    const fautives: number[] = [];
    source.split("\n").forEach((ligne, i) => {
        if (/onValider\s*[=:]\s*\{?\s*(\([^)]*\)|\w+)\s*=>\s*void\s/.test(ligne)) fautives.push(i + 1);
    });
    return fautives;
}

describe("onValider d'une fenêtre à champs rend sa promesse", () => {
    it("le détecteur voit un void devant l'enregistrement", () => {
        expect(onValiderJetes("onValider={(v) => void enregistrer(v)}")).toEqual([1]);
        expect(onValiderJetes("onValider: () => void enregistrer(),")).toEqual([1]);
        expect(onValiderJetes("onValider={(v) => enregistrer(v)}")).toEqual([]);
    });

    it("aucun appelant de FenetreChamps, SectionLue ou BlocLu ne jette la promesse", () => {
        const fautifs = fichiers(RACINE)
            .filter((f) => /FenetreChamps|SectionLue|BlocLu/.test(readFileSync(f, "utf8")))
            .flatMap((f) => onValiderJetes(readFileSync(f, "utf8")).map((n) => `${relative(RACINE, f).split(sep).join("/")}:${n}`));
        expect(fautifs).toEqual([]);
    });
});
