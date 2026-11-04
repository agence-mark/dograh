// @vitest-environment node
/**
 * [.mark] Revue de contrôle, point 5 : un échec = une seule notification.
 *
 * `echecAffiche(erreur)` notifie déjà. Le suivre d'un second `notifier.echec(...)` dans les trois lignes qui suivent (ou, dans
 * `CerveauxReglages`, d'un `notifier.suivre` qui notifie l'échec) montre deux alertes pour une panne. Quand une notification
 * est posée à côté, l'état d'erreur prend `phraseEchec(erreur)` (sans notification) et la notification porte `{ erreur }`.
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

/** Les lignes où `echecAffiche(` est suivi, dans les trois lignes d'après, d'un `notifier.echec(`. */
export function doublesNotifications(source: string): number[] {
    const lignes = source.split("\n");
    const fautives: number[] = [];
    lignes.forEach((ligne, i) => {
        if (!ligne.includes("echecAffiche(") || /^\s*(\/\/|\*|import)|function echecAffiche/.test(ligne)) return;
        if (lignes.slice(i + 1, i + 4).some((l) => l.includes("notifier.echec("))) fautives.push(i + 1);
    });
    return fautives;
}

describe("un échec, une notification", () => {
    it("le détecteur voit echecAffiche suivi de notifier.echec, pas phraseEchec", () => {
        expect(doublesNotifications("setErreur(echecAffiche(r.error));\nnotifier.echec(T);")).toEqual([1]);
        expect(doublesNotifications("setErreur(phraseEchec(r.error));\nnotifier.echec(T, { erreur: r.error });")).toEqual([]);
        expect(doublesNotifications("setErreur(echecAffiche(r.error));\nreturn;")).toEqual([]);
    });

    it("aucun fichier de ui/src ne double la notification de echecAffiche", () => {
        const fautifs = fichiers(RACINE).flatMap((f) =>
            doublesNotifications(readFileSync(f, "utf8")).map((n) => `${relative(RACINE, f).split(sep).join("/")}:${n}`),
        );
        expect(fautifs).toEqual([]);
    });

    it("le suivi de CerveauxReglages ne notifie pas l'échec deux fois", () => {
        const source = readFileSync(join(RACINE, "components/mark/reglages/CerveauxReglages.tsx"), "utf8");
        expect(source).not.toContain("echecAffiche(");
    });
});
