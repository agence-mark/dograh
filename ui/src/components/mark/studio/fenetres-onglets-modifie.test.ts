// @vitest-environment node
/**
 * [.mark] Revue de contrôle, point 4 (M4) : toute fenêtre `FenetreOnglets` qui enregistre dit si elle porte une saisie.
 *
 * Sans `modifie`, Échap et un clic dehors jettent la saisie sans prévenir. Une fenêtre en lecture seule (`valider={null}`)
 * n'a rien à perdre ; toute autre porte `modifie={...}`. Une exemption s'écrit ici avec sa raison.
 */
import { readdirSync, readFileSync, statSync } from "node:fs";
import { join, relative, sep } from "node:path";

import { describe, expect, it } from "vitest";

const RACINE = join(__dirname, "..", "..", "..");
const EXEMPTIONS: Record<string, string> = {};

function fichiers(dossier: string, sortie: string[] = []): string[] {
    for (const nom of readdirSync(dossier)) {
        const chemin = join(dossier, nom);
        if (statSync(chemin).isDirectory()) fichiers(chemin, sortie);
        else if (/\.tsx$/.test(nom) && !/\.test\.tsx$/.test(nom)) sortie.push(chemin);
    }
    return sortie;
}

/** Les balises ouvrantes `<FenetreOnglets …>` d'une source, avec leur ligne. */
export function balises(source: string): { ligne: number; texte: string }[] {
    const trouvees: { ligne: number; texte: string }[] = [];
    for (const m of source.matchAll(/<FenetreOnglets\b([\s\S]*?)\n\s*>/g)) {
        trouvees.push({ ligne: source.slice(0, m.index).split("\n").length, texte: m[0] });
    }
    return trouvees;
}

export const sansModifie = (texte: string): boolean => !/\bmodifie=/.test(texte) && !/\bvalider=\{null\}/.test(texte);

describe("FenetreOnglets : modifie", () => {
    it("le détecteur voit une fenêtre qui enregistre sans modifie", () => {
        expect(sansModifie('<FenetreOnglets\n  fermer={f}\n  valider="Créer"\n>')).toBe(true);
        expect(sansModifie('<FenetreOnglets\n  fermer={f}\n  valider="Créer"\n  modifie={nom !== ""}\n>')).toBe(false);
        expect(sansModifie("<FenetreOnglets\n  fermer={f}\n  valider={null}\n>")).toBe(false);
    });

    it("toutes les fenêtres qui enregistrent portent modifie", () => {
        const fautives = fichiers(RACINE).flatMap((f) => {
            const rel = relative(RACINE, f).split(sep).join("/");
            if (rel in EXEMPTIONS) return [];
            return balises(readFileSync(f, "utf8"))
                .filter((b) => sansModifie(b.texte))
                .map((b) => `${rel}:${b.ligne}`);
        });
        expect(fautives).toEqual([]);
    });
});
