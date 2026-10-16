/**
 * [.mark] Chantier agents-specialises, lot 13 (A10) : chaque clé que l'écran de l'agent expose est
 * COMMUNE (portée par le principal, recopiée dans ses spécialisés, en lecture chez eux) ou PROPRE
 * (réglée par chaque agent), jamais l'une et l'autre, jamais aucune des deux.
 *
 * La liste est écrite en UN seul endroit, ``api/services/groupe/reglages.py`` (``CLES_COMMUNES`` et
 * ``CLES_PROPRES``), lue par la recopie du serveur ; ce test la LIT (comme l'inventaire lit les schémas)
 * et la compare à l'inventaire de l'écran (``inventaire-agent.ts``) : une clé ajoutée à l'écran sans être
 * classée fait échouer ce test, et on ne perd jamais en silence un réglage de la recopie.
 *
 * Il vérifie aussi que l'écran traite en lecture, chez un spécialisé, exactement les thèmes que le serveur
 * dit communs (les thèmes 3 à 8 en entier ; le thème Agent et le thème Briques en partie).
 */
import { readFileSync } from "node:fs";
import { join } from "node:path";

import { describe, expect, it } from "vitest";

import { THEMES_COMMUNS_EN_LECTURE } from "../groupe/contexte-groupe";
import { INVENTAIRE_AGENT } from "./inventaire-agent";

const source = readFileSync(join(process.cwd(), "..", "api/services/groupe/reglages.py"), "utf8");

/** Les constantes ``CLE_X = "valeur"`` du fichier (les tuples s'y réfèrent par leur nom). */
const passations = readFileSync(join(process.cwd(), "..", "api/services/groupe/passations.py"), "utf8");
const CONSTANTES = new Map([...source.matchAll(/^(CLE_[A-Z_]+)\s*=\s*"([a-z_0-9]+)"/gm)].map((m) => [m[1], m[2]]));
// Le lien entre principal et spécialisés est défini dans passations.py (``CLE_AGENT_PRINCIPAL``…).
for (const m of passations.matchAll(/^(CLE_[A-Z_]+)\s*=\s*"([a-z_0-9]+)"/gm)) CONSTANTES.set(m[1], m[2]);

/** Les clés d'un tuple Python ``NOM[: type] = ( ... )`` : chaînes littérales, constantes ``CLE_X``, ou
 * ``*AUTRE_TUPLE`` déplié. */
const tuple = (nom: string): string[] => {
    const debut = source.search(new RegExp(`^${nom}\\b[^=\\n]*=\\s*\\(`, "m"));
    if (debut < 0) throw new Error(`${nom} not found in reglages.py: the file moved, update this test.`);
    const reste = source.slice(debut).replace(/#.*$/gm, "");
    // Le corps s'arrête à la parenthèse fermante qui équilibre la première.
    let profondeur = 0;
    let fin = reste.length;
    for (let i = reste.indexOf("("); i < reste.length; i++) {
        if (reste[i] === "(") profondeur++;
        if (reste[i] === ")" && --profondeur === 0) {
            fin = i;
            break;
        }
    }
    const corps = reste.slice(reste.indexOf("("), fin);
    const cles: string[] = [];
    for (const m of corps.matchAll(/"([a-z_0-9]+)"|\*([A-Z_]+)|(CLE_[A-Z_]+)/g)) {
        if (m[1]) cles.push(m[1]);
        else if (m[2]) cles.push(...tuple(m[2]));
        else if (m[3] && CONSTANTES.has(m[3])) cles.push(CONSTANTES.get(m[3])!);
    }
    return cles;
};

const COMMUNES = new Set(tuple("CLES_COMMUNES"));
const PROPRES = new Set(tuple("CLES_PROPRES"));
const GROUPE = tuple("CLES_DU_GROUPE");

describe("[.mark] clés communes ou propres d'un groupe d'agents", () => {
    it("lit une liste plausible (sinon tout le reste serait vert pour rien)", () => {
        expect(COMMUNES.size).toBeGreaterThan(60);
        expect(PROPRES.size).toBeGreaterThan(3);
    });

    it("ne met aucune clé dans les deux listes", () => {
        expect([...COMMUNES].filter((cle) => PROPRES.has(cle))).toEqual([]);
    });

    it.each(Object.keys(INVENTAIRE_AGENT))("la clé %s de l'écran est commune ou propre", (cle) => {
        expect(COMMUNES.has(cle) || PROPRES.has(cle), `${cle}: ni commune ni propre dans api/services/groupe/reglages.py`).toBe(true);
    });

    it("classe les réglages du groupe comme communs (portés par le principal) et le lien comme propre", () => {
        for (const cle of GROUPE) expect(COMMUNES.has(cle), cle).toBe(true);
        for (const cle of ["agent_principal_id", "agents_specialises", "cerveau_propre", "etablissement_id"]) {
            expect(PROPRES.has(cle), cle).toBe(true);
        }
    });

    it("lit en entier chez un spécialisé les thèmes dont toutes les clés sont communes", () => {
        for (const theme of THEMES_COMMUNS_EN_LECTURE) {
            const cles = Object.entries(INVENTAIRE_AGENT)
                .filter(([, entree]) => "theme" in entree && entree.theme === theme)
                .map(([cle]) => cle);
            expect(cles.length, `theme ${theme}`).toBeGreaterThan(0);
            // Une clé propre dans un thème lu en entier ne pourrait plus se régler : seulement le
            // thème Établissement, dont la fiche, les horaires et l'adresse sont « celui de l'appel ».
            const propres = cles.filter((cle) => PROPRES.has(cle));
            if (theme === "etablissement") {
                expect(propres.sort()).toEqual(["adresse_etablissement", "etablissement_id", "horaires_ouverture"]);
            } else {
                expect(propres, `theme ${theme}`).toEqual([]);
            }
        }
    });
});
