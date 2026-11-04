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
// R4 : tout `ui/src`, plus seulement les cinq dossiers de l'écran .mark (M5 hors inventaire : `OrganizationPreferencesSection`,
// les pages d'amont montrées par les adresses du Labo : campagnes, téléphonie, atelier d'un agent).
const DOSSIERS = ["."];
/**
 * Exemptions écrites : fichiers d'amont dont le texte n'est jamais montré. Vide : les fichiers d'amont qui lisaient
 * `detailFromError` sont tous joints par une adresse du Labo ou d'un client (`app/labo/**`, `app/clients/**`, `app/agents/**`)
 * ou par un composant de l'écran .mark, donc convertis. Une entrée = un chemin relatif à `ui/src` + la raison.
 */
const EXEMPTIONS: Record<string, string> = {
    "lib/apiError.ts": "définit detailFromError",
};

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
        // Transport : l'erreur levée est attrapée plus loin ; l'affichage de son message est jugé par `messageAffiche`.
        if (/throw new Error\(\s*detailFromError\(/.test(ligne) || lignes.slice(Math.max(0, i - 3), i).some((l) => /throw new Error\(\s*$/.test(l))) return;
        if (/faute-de-champ/.test(ligne) || (i > 0 && /faute-de-champ/.test(lignes[i - 1]))) return;
        fautives.push(i + 1);
    });
    return fautives;
}

/**
 * Les lignes qui montrent le `message` d'une erreur attrapée : le texte interne de l'erreur serait affiché.
 * Deux formes, sur une ou plusieurs lignes : `set…(e instanceof Error ? e.message : …)` et la forme gardée
 * `e instanceof Error && e.message ? e.message : …` (revue de contrôle, point 2 : celle-ci passait sous l'ancien motif).
 */
export function messagesAffiches(source: string): number[] {
    const lignes = source.split("\n");
    const fautives = new Set<number>();
    const motifs = [
        /\bset[A-Z]\w*\([^)]*instanceof Error \? \w+\.message/g,
        /instanceof Error\s*&&\s*(\w+)\.message\s*\?\s*\1\.message/g,
    ];
    for (const motif of motifs) {
        for (const m of source.matchAll(motif)) {
            const i = source.slice(0, m.index).split("\n").length - 1;
            if (/^\s*(\/\/|\*)/.test(lignes[i])) continue;
            // Exemption écrite : la faute de lecture d'une saisie locale (JSON.parse), pas un texte du serveur.
            if (/message-local/.test(lignes[i]) || (i > 0 && /message-local/.test(lignes[i - 1]))) continue;
            fautives.add(i + 1);
        }
    }
    return [...fautives].sort((x, y) => x - y);
}

describe("aucun texte brut d'erreur serveur à l'écran", () => {
    it("le détecteur voit un affichage brut, pas un motif de notification ni une faute de champ", () => {
        expect(lignesBrutes('setErreur(detailFromError(r.error, "x"));')).toEqual([1]);
        expect(lignesBrutes('notifier.echec(T, { erreur: detailFromError(r.error, "x") });')).toEqual([]);
        expect(lignesBrutes('// faute-de-champ : 422\nconst m = detailFromError(r.error, "");')).toEqual([]);
        expect(lignesBrutes("setErreur(echecAffiche(r.error));")).toEqual([]);
        expect(lignesBrutes('throw new Error(detailFromError(r.error, "x"));')).toEqual([]);
        expect(lignesBrutes('throw new Error(\n  detailFromError(r.error, "x"),\n);')).toEqual([]);
        expect(messagesAffiches("setError(e instanceof Error ? e.message : 'x');")).toEqual([1]);
        expect(messagesAffiches("setError(echecAffiche(e));")).toEqual([]);
        // La forme gardée, sur une ou deux lignes (celle de l'enregistrement des réglages d'agent).
        expect(messagesAffiches("const m = e instanceof Error && e.message ? e.message : echecAffiche(e);")).toEqual([1]);
        expect(messagesAffiches("const m = e instanceof Error && e.message\n    ? e.message\n    : echecAffiche(e);")).toEqual([1]);
        expect(messagesAffiches("const m = phraseEchec(e);")).toEqual([]);
    });

    const tous = () =>
        DOSSIERS.flatMap((d) => fichiers(join(RACINE, d)))
            .map((f) => ({ rel: relative(RACINE, f).split(sep).join("/"), f }))
            .filter(({ rel }) => !rel.startsWith("components/mark/notifications/") && !(rel in EXEMPTIONS) && !rel.startsWith("client/"));

    it("aucun fichier de ui/src n'affiche detailFromError directement", () => {
        const fautifs = tous().flatMap(({ rel, f }) => lignesBrutes(readFileSync(f, "utf8")).map((n) => `${rel}:${n}`));
        expect(fautifs).toEqual([]);
    });

    it("aucun fichier de ui/src ne pose le message d'une erreur attrapée dans l'écran", () => {
        const fautifs = tous().flatMap(({ rel, f }) => messagesAffiches(readFileSync(f, "utf8")).map((n) => `${rel}:${n}`));
        expect(fautifs).toEqual([]);
    });

    it("les exemptions écrites existent encore et disent pourquoi", () => {
        for (const [rel, raison] of Object.entries(EXEMPTIONS)) {
            expect(raison.length).toBeGreaterThan(5);
            expect(() => readFileSync(join(RACINE, rel), "utf8")).not.toThrow();
        }
    });
});
