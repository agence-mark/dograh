// @vitest-environment node
/**
 * [.mark] R3 M5 : le texte brut d'une erreur du serveur n'est jamais affiché hors du module des notifications.
 *
 * La question de ce fichier : un fichier de l'écran .mark appelle-t-il `detailFromError(` autrement que pour passer le motif à
 * `notifier.echec(..., { erreur: detailFromError(...) })` ? Les composants posent `echecAffiche(erreur)` (phrase fixe dans la
 * langue de l'écran, motif dans « Détails »). Seule exception, écrite sur la ligne d'avant ou sur la ligne : un commentaire
 * `faute-de-champ` (faute de validation 422, lue sous son champ).
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

/** Les lignes qui affichent ou transportent le texte brut : `detailFromError(` hors motif de notification et hors exemption. */
export function lignesBrutes(source: string): number[] {
    const lignes = source.split("\n");
    const fautives: number[] = [];
    lignes.forEach((ligne, i) => {
        if (!ligne.includes("detailFromError(")) return;
        if (/^\s*import\b/.test(ligne) || /^\s*(\/\/|\*)/.test(ligne)) return;
        if (/\{\s*erreur:\s*detailFromError\(/.test(ligne)) return; // le motif part dans « Détails »
        if (/faute-de-champ/.test(ligne) || (i > 0 && /faute-de-champ/.test(lignes[i - 1]))) return;
        fautives.push(i + 1);
    });
    return fautives;
}

describe("aucun texte brut d'erreur serveur à l'écran", () => {
    it("le détecteur voit un affichage brut, pas un motif de notification ni une faute de champ", () => {
        expect(lignesBrutes('setErreur(detailFromError(r.error, "x"));')).toEqual([1]);
        expect(lignesBrutes('notifier.echec(T, { erreur: detailFromError(r.error, "x") });')).toEqual([]);
        expect(lignesBrutes('// faute-de-champ : 422\nconst m = detailFromError(r.error, "");')).toEqual([]);
        expect(lignesBrutes("setErreur(echecAffiche(r.error));")).toEqual([]);
    });

    it("aucun fichier de l'écran .mark n'affiche detailFromError directement", () => {
        const fautifs = DOSSIERS.flatMap((d) => fichiers(join(RACINE, d)))
            .map((f) => ({ rel: relative(RACINE, f).split(sep).join("/"), f }))
            .filter(({ rel }) => !rel.startsWith("components/mark/notifications/"))
            .flatMap(({ rel, f }) => lignesBrutes(readFileSync(f, "utf8")).map((n) => `${rel}:${n}`));
        expect(fautifs).toEqual([]);
    });
});
