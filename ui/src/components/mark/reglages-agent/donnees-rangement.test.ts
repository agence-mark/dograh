/**
 * [.mark] N2 (rangement laissé par SA-12) : le thème « Données de l'appel » est rangé en sections par ce que chaque réglage FAIT
 * (audit 03 § 1, 01 § 4) ; chaque clé reste ce qu'elle était (même clé, même valeur, même accès du builder).
 *
 *  - Fiche d'appel : ce que l'agent note (fiche, ce qu'il en montre au modèle), issues de l'appel, transcription, compaction ;
 *  - Passages : ce que le code fait quand l'agent prend une porte ou passe la main (mode de prise de notes, portes, ordre, indices des modules,
 *    greffier, arbitre, transfert garanti, mots « c'est fait », question redemandée, outil écrit, préchauffage) ;
 *  - Après l'appel : amélioration de l'agent (signaler, alertes) et la chaîne d'après l'appel ;
 *  - Standard externe : les champs lus et écrits dans un standard.
 *
 * Le découpage reste à l'intérieur d'un seul thème (même identifiant `donnees`, mêmes liens `?theme=donnees`, même enregistrement par
 * parties) : quatre thèmes demanderaient de réécrire les modèles de réglages, les niveaux et la recherche (voir 18).
 */
import { readFileSync } from "node:fs";
import { join } from "node:path";

import { describe, expect, it } from "vitest";

const source = readFileSync(join(process.cwd(), "src/components/mark/reglages-agent/ThemeDonnees.tsx"), "utf8");

const SECTIONS = ["donnees-fiche", "donnees-issue", "donnees-transcription", "donnees-compaction", "donnees-passages", "donnees-amelioration", "donnees-apres-appel", "donnees-pbx"];
const groupeDe = (cle: string): string | null => {
    const i = source.search(new RegExp(`cle="${cle.replace(".", "\.")}"`));
    if (i < 0) return null;
    let retenu: string | null = null;
    let position = -1;
    for (const id of SECTIONS) {
        const p = source.indexOf(`id="${id}"`);
        if (p >= 0 && p <= i && p > position) {
            retenu = id;
            position = p;
        }
    }
    return retenu;
};

const ATTENDU: Record<string, string[]> = {
    "donnees-fiche": ["fiche_au_fil_de_leau", "fiche_deja_connu", "fiche_dans_le_systeme", "fiche_forme_courte"],
    "donnees-passages": [
        "fiche_mode_de_note", "portes_dans_la_reponse", "ordre_de_la_reponse", "indices_des_modules",
        "verite_formulations_d_action", "phrase_sans_redemande", "prechauffer_les_collegues", "reconnaitre_un_outil_ecrit", "greffier_llm", "greffier_consigne", "arbitre_llm",
    ],
    "donnees-amelioration": ["signaler_un_probleme", "alertes_par_mail"],
    "donnees-transcription": ["transcript_configuration.include_end_timestamps"],
    "donnees-compaction": ["context_compaction_enabled"],
    "donnees-pbx": ["external_pbx_field_mappings", "external_pbx_lead_headers"],
};

describe("[.mark] le thème Données est rangé par ce que chaque réglage fait", () => {
    for (const [section, cles] of Object.entries(ATTENDU)) {
        it(`${section} porte ${cles.length} réglage(s)`, () => {
            for (const cle of cles) expect(groupeDe(cle), cle).toBe(section);
        });
    }
    it("les quatre rangements se suivent : fiche, passages, après l'appel, standard externe", () => {
        const ordre = ["donnees-fiche", "donnees-passages", "donnees-apres-appel", "donnees-pbx"].map((id) => source.indexOf(`id="${id}"`));
        expect(ordre.every((p) => p >= 0)).toBe(true);
        expect([...ordre].sort((a, b) => a - b)).toEqual(ordre);
    });
});
