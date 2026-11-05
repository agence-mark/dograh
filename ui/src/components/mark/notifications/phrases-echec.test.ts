// @vitest-environment node
/**
 * [.mark] SE-28 (sous-lot 16) : une phrase précise par action en échec, en français et en anglais.
 *
 * | Test | La garantie |
 * |---|---|
 * | aucune phrase générique | tout `echecAffiche(` / `phraseEchec(` de l'écran nomme sa phrase (`ECHECS.<action>` ou un texte écrit) |
 * | les phrases | chacune existe dans les deux langues, dit quoi faire, n'est pas la phrase générique, et sert quelque part |
 * | les écritures | tout fichier qui écrit (POST, PUT, PATCH, DELETE de l'API) dit son échec par une phrase choisie, ou est exempté avec sa raison |
 */
import { readdirSync, readFileSync, statSync } from "node:fs";
import { join, relative, sep } from "node:path";

import { describe, expect, it } from "vitest";

import { ECHEC_GENERIQUE } from "./echec-affiche";
import { ECHECS } from "./phrases-echec";

const SRC = join(__dirname, "..", "..", "..");

function fichiers(dossier: string, sortie: string[] = []): string[] {
    for (const nom of readdirSync(dossier)) {
        const chemin = join(dossier, nom);
        if (statSync(chemin).isDirectory()) {
            if (nom !== "client" || dossier !== SRC) fichiers(chemin, sortie);
        } else if (/\.(ts|tsx)$/.test(nom) && !/\.test\.(ts|tsx)$/.test(nom)) sortie.push(chemin);
    }
    return sortie;
}
const chemin = (f: string) => relative(SRC, f).split(sep).join("/");
const SOURCES = fichiers(SRC).map((f) => ({ f: chemin(f), texte: readFileSync(f, "utf8") }));

/** Les appels `nom(` d'un texte, avec le nombre d'arguments de plus haut niveau (parenthèses, accolades, crochets et chaînes comptés). */
export function appels(texte: string, nom: string): { ligne: number; arguments: number }[] {
    const trouves: { ligne: number; arguments: number }[] = [];
    const re = new RegExp(`(?<![\\w.])${nom}\\(`, "g");
    for (let m = re.exec(texte); m; m = re.exec(texte)) {
        let i = m.index + m[0].length;
        let prof = 1;
        let args = 0;
        let segment = false;
        let chaine = "";
        for (; i < texte.length && prof > 0; i++) {
            const c = texte[i];
            if (chaine) {
                if (c === "\\") i++;
                else if (c === chaine) chaine = "";
                continue;
            }
            if (c === '"' || c === "'" || c === "`") chaine = c;
            else if ("([{".includes(c)) prof++;
            else if (")]}".includes(c)) prof--;
            else if (c === "," && prof === 1) {
                if (segment) args++;
                segment = false;
                continue;
            }
            if (!/\s/.test(c) && prof >= 1) segment = true;
        }
        trouves.push({ ligne: texte.slice(0, m.index).split("\n").length, arguments: args + (segment ? 1 : 0) });
    }
    return trouves;
}

describe("[.mark] SE-28 : aucune phrase générique par défaut", () => {
    it("chaque echecAffiche / phraseEchec de l'écran nomme sa phrase", () => {
        const generiques: string[] = [];
        for (const { f, texte } of SOURCES) {
            if (f === "components/mark/notifications/echec-affiche.ts") continue;
            for (const nom of ["echecAffiche", "phraseEchec"]) {
                for (const a of appels(texte, nom)) if (a.arguments < 2) generiques.push(`${f}:${a.ligne} ${nom}`);
            }
        }
        expect(generiques).toEqual([]);
    });

    it("le compteur d'arguments lit un appel sur plusieurs lignes et une phrase écrite", () => {
        expect(appels("a(echecAffiche(r.error));", "echecAffiche")).toEqual([{ ligne: 1, arguments: 1 }]);
        expect(appels("x = echecAffiche(\n  e,\n  { fr: 'a, b', en: 'c' },\n);", "echecAffiche")).toEqual([{ ligne: 1, arguments: 2 }]);
        expect(appels("setErreur(phraseEchec(f(a, b)))", "phraseEchec")).toEqual([{ ligne: 1, arguments: 1 }]);
    });
});

describe("[.mark] SE-28 : les phrases d'échec", () => {
    const cles = Object.keys(ECHECS) as (keyof typeof ECHECS)[];
    const tout = SOURCES.filter((s) => s.f !== "components/mark/notifications/phrases-echec.ts")
        .map((s) => s.texte)
        .join("\n");

    it("il y en a environ cent vingt", () => {
        expect(cles.length).toBeGreaterThanOrEqual(120);
    });

    it("chacune existe en français et en anglais, dit quoi faire, et n'est pas la phrase générique", () => {
        for (const cle of cles) {
            const { fr, en } = ECHECS[cle];
            expect(fr.length, cle).toBeGreaterThan(15);
            expect(en.length, cle).toBeGreaterThan(15);
            expect(fr, cle).not.toBe(en);
            expect(fr, cle).not.toBe(ECHEC_GENERIQUE.fr);
            expect(en, cle).not.toBe(ECHEC_GENERIQUE.en);
            // Le français est du français, l'anglais de l'anglais (une phrase copiée dans l'autre langue se voit à l'accent ou au mot).
            expect(en, cle).not.toMatch(/[éèêàçùâîôû]|Réessayez|Vérifiez/);
            expect(fr, cle).not.toMatch(/\b(Try again|did not|not saved|Check the)\b/);
            // Elles finissent par un point : une phrase, pas un fragment.
            expect(fr, cle).toMatch(/[.]$/);
            expect(en, cle).toMatch(/[.]$/);
        }
    });

    it("chacune sert quelque part (aucune phrase morte)", () => {
        const mortes = cles.filter((cle) => !new RegExp(`ECHECS\\.${cle}\\b`).test(tout));
        expect(mortes).toEqual([]);
    });

    it("aucun appel ne nomme une phrase qui n'existe pas", () => {
        const connues = new Set<string>(cles);
        const inconnues = [...tout.matchAll(/ECHECS\.(\w+)/g)].map((m) => m[1]).filter((c) => !connues.has(c));
        expect(inconnues).toEqual([]);
    });
});

/** Un fichier qui écrit dit son échec par une phrase choisie. */
const ECRITURE = /\b[a-z][A-Za-z0-9]*Api[A-Za-z0-9]*(?:Post|Put|Patch|Delete)\s*\(/;
const PHRASE_CHOISIE = /ECHECS\.|notifier\.(?:echec|suivre)\(|echecAffiche\([^)]*,\s*[\w{]|ECHEC_/;

/** Les fichiers qui écrivent sans poser eux-mêmes la phrase, avec la raison écrite. Une entrée = un chemin + pourquoi. */
const EXEMPTIONS: Record<string, string> = {
    "components/flow/mcpRefresh.ts": "rend le motif à son appelant (la fenêtre de l'outil), qui l'écrit dans sa propre phrase",
    "components/mark/connaissances/deposer.ts": "rend un code (`upload_url`, `analyse`) ; la page de la base de connaissances écrit la phrase de chaque code",
    "components/mark/groupe/reglages-groupe.tsx": "porte sa propre phrase, `sonEchec`, sous le champ du son d'attente",
    "components/mark/parametres-organisation/DonneesClientMaquette.tsx": "ses gestes passent par `poser` du parent (PageBase), qui écrit la phrase et la montre sous le titre",
    "components/mark/reglages-agent/EtablissementsServis.tsx": "montre une ligne d'erreur fixe (`erreur`) à la place de la liste, pas une écriture de l'utilisateur",
    "components/mark/sources/useSources.ts": "rend l'erreur à l'appelant, qui la montre avec sa phrase (`FenetreService`, `CerveauxReglages`)",
    "components/workflow/UploadWorkflowButton.tsx": "écrit déjà sa phrase fixe « L'agent n'a pas pu être importé » sous la zone de dépôt",
    "context/OnboardingContext.tsx": "mémoire de la visite guidée : un échec se journalise, rien n'est à dire à la personne",
    "lib/espaces.ts": "lève une erreur que l'écran de l'espace attrape et rend par `echecAffiche`",
    "lib/organizationMembership.ts": "lève une erreur que l'écran d'accueil attrape ; page d'amont",
    "lib/utils.ts": "l'usurpation d'identité lève une erreur que la page superadmin rend par `echecAffiche`",
};

describe("[.mark] SE-28 : toute écriture dit son échec", () => {
    it("chaque fichier qui écrit pose une phrase choisie, ou est exempté avec sa raison", () => {
        const sans = SOURCES.filter(({ f, texte }) => ECRITURE.test(texte) && !PHRASE_CHOISIE.test(texte) && !(f in EXEMPTIONS)).map((s) => s.f);
        expect(sans).toEqual([]);
    });

    it("une exemption qui n'a plus de raison d'être se retire", () => {
        const inutiles = Object.keys(EXEMPTIONS).filter((f) => {
            const s = SOURCES.find((x) => x.f === f);
            return !s || !ECRITURE.test(s.texte) || PHRASE_CHOISIE.test(s.texte);
        });
        expect(inutiles).toEqual([]);
    });
});
