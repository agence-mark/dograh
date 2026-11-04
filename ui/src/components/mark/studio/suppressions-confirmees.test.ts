// @vitest-environment node
/**
 * [.mark] R3 M3 : aucune suppression en un clic (`bonnes-pratiques-ecran.md`, « Gestes sûrs »).
 *
 * La question de ce fichier : un fichier de l'écran .mark qui appelle une route `*Delete` porte-t-il, pour CHAQUE appel, une
 * confirmation (`<SuppressionConfirmee`, `<ConfirmerSuppression`) ou un « Annuler » différé (`notifier.annulable`,
 * `notifier.reversible`), ou une exemption écrite `// suppression-confirmee : <où se trouve la confirmation>` ?
 * Sinon le test échoue en nommant le fichier.
 */
import { readdirSync, readFileSync, statSync } from "node:fs";
import { join, relative, sep } from "node:path";

import { describe, expect, it } from "vitest";

const RACINE = join(__dirname, "..", "..", "..");
const DOSSIERS = ["components/mark", "components/builder", "app/labo", "app/clients", "app/relation"];

function fichiers(dossier: string, sortie: string[] = []): string[] {
    let noms: string[];
    try {
        noms = readdirSync(dossier);
    } catch {
        return sortie;
    }
    for (const nom of noms) {
        const chemin = join(dossier, nom);
        if (statSync(chemin).isDirectory()) fichiers(chemin, sortie);
        else if (/\.(ts|tsx)$/.test(nom) && !/\.test\.(ts|tsx)$/.test(nom)) sortie.push(chemin);
    }
    return sortie;
}

const sansImports = (s: string) => s.replace(/^import[\s\S]*?from\s+["'][^"']+["'];?$/gm, "");
const sansCommentaires = (s: string) => s.replace(/\/\*[\s\S]*?\*\//g, "").replace(/^\s*\/\/.*$/gm, "");

export const APPELS = /\b[a-zA-Z]\w*Delete\s*\(/g;
export const GARDES = /<SuppressionConfirmee\b|<ConfirmerSuppression\b|notifier\.annulable\(|notifier\.reversible\(|\/\/\s*suppression-confirmee\s*:/g;

export const compter = (source: string) => ({
    appels: (sansCommentaires(sansImports(source)).match(APPELS) ?? []).length,
    gardes: (source.match(GARDES) ?? []).length,
});

describe("aucune suppression en un clic", () => {
    it("le compteur voit un appel sans garde, et un appel gardé", () => {
        expect(compter("await supprimerUnTrucApiV1TrucDelete({})")).toEqual({ appels: 1, gardes: 0 });
        expect(compter("<SuppressionConfirmee onConfirmer={() => supprimerUnTrucApiV1TrucDelete({})}>")).toEqual({ appels: 1, gardes: 1 });
    });

    it("chaque appel `*Delete` de l'écran .mark a sa confirmation, son « Annuler » différé ou son exemption écrite", () => {
        const fautifs = DOSSIERS.flatMap((d) => fichiers(join(RACINE, d)))
            .map((f) => ({ rel: relative(RACINE, f).split(sep).join("/"), ...compter(readFileSync(f, "utf8")) }))
            .filter(({ appels, gardes }) => appels > gardes)
            .map(({ rel, appels, gardes }) => `${rel} : ${appels} suppression(s), ${gardes} garde(s)`);
        expect(fautifs).toEqual([]);
    });
});
