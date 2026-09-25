/**
 * [.mark] Do the screen's bounds still match the ones the server enforces?
 *
 * The question this file answers, and only this one:
 *
 *     If a bound moves in `api/schemas/workflow_configurations.py`, does
 *     anything notice — or does a client's save start failing in silence?
 *
 * Why it exists
 * -------------
 * A bound typed by hand into a JSX attribute is right the day it is written and
 * wrong the day the schema moves, with nothing in between to say so. So the
 * table in `bornes-reglages.ts` is not trusted: it is READ BACK against the
 * Python file. A bound that drifts breaks this test rather than a save.
 *
 * It also asserts the reverse direction, for each of the three kinds of bound:
 * every bounded setting our sections show has a line in the RIGHT table
 * (numeric range, text length, or list size), and each count matches, so a
 * bound the parser cannot read turns red instead of vanishing. A setting added
 * to a section without its bound would otherwise be unchecked, which is exactly
 * the state this whole file was written to leave behind.
 *
 * The third table came from writing the second: Pydantic spells "max_length"
 * for both a `str` and a `list[str]`, and it means characters on one and items
 * on the other. The test caught it; no review did.
 */

import { readFileSync } from "node:fs";
import { join } from "node:path";

import { describe, expect, it } from "vitest";

import {
    BORNES,
    LONGUEURS_MAX,
    messageHorsBornes,
    messagesHorsBornes,
    NOMBRE_MAX_ELEMENTS,
} from "./bornes-reglages";
import {
    CLES_ACCUEIL,
    CLES_RELANCE,
    CLES_TOUR_DE_PAROLE,
    CLES_TRANSCRIPTION,
    CLES_VOIX,
} from "./SectionReglagesPipecat";

// vitest runs with the ui/ package as its working directory; the schema is one
// level up, in the API.
const SCHEMA = readFileSync(
    join(process.cwd(), "..", "api", "schemas", "workflow_configurations.py"),
    "utf8",
);

/** The bounds Pydantic declares for one field, read out of the schema. */
const bornesDuSchema = (cle: string) => {
    const depart = SCHEMA.indexOf(`\n    ${cle}: `);
    if (depart === -1) return null;
    const fin = SCHEMA.indexOf("\n    )", depart);
    const bloc = SCHEMA.slice(depart, fin === -1 ? undefined : fin);

    const lire = (nom: string) => {
        // ⚠️ Deliberately NUMERIC only. A bound written as a named constant
        // (`le=MAX_VAD_STOP_SECS` — the schema already does this elsewhere,
        // `max_length=MAX_CALL_DISPOSITION_CODE_LENGTH`) does NOT match here,
        // and would read as "no bound at all". That is exactly why the count
        // assertions below exist: a bound this parser cannot read has to turn
        // red, not vanish.
        const m = bloc.match(new RegExp(`\\b${nom}=([0-9.]+)`));
        return m ? Number(m[1]) : null;
    };
    return {
        gt: lire("gt"),
        ge: lire("ge"),
        le: lire("le"),
        lt: lire("lt"),
        maxLength: lire("max_length"),
        // ⚠️ Pydantic spells the same keyword for both, but on a `list[...]`
        // it counts ITEMS and on a `str` it counts CHARACTERS. Treating them
        // alike would put a 200-character cap on a 200-ENTRY list.
        estUneListe: /^\s+\w+:\s*list\[/.test(bloc),
    };
};

describe("Les bornes affichees a l'ecran", () => {
    it("trouve bien le schema Python (sinon tout le reste est vide et vert pour rien)", () => {
        expect(SCHEMA).toContain("user_speech_timeout");
        expect(bornesDuSchema("vad_stop_secs")).toEqual({
            gt: 0, ge: null, le: 5, lt: null, maxLength: null, estUneListe: false,
        });
    });

    it.each(Object.keys(BORNES))("correspondent au schema du serveur pour %s", (cle) => {
        const schema = bornesDuSchema(cle);
        expect(schema, `${cle} n'existe pas dans le schema Python`).not.toBeNull();

        const borne = BORNES[cle];
        // The schema never uses `lt` on these fields; if it starts to, this
        // test must learn about it rather than quietly ignore it.
        expect(schema!.lt, `${cle} : borne haute EXCLUSIVE non prevue ici`).toBeNull();
        expect(schema!.le, `${cle} : borne haute`).toBe(borne.max);

        if (borne.minStrict) {
            expect(schema!.gt, `${cle} : borne basse stricte`).toBe(borne.min);
            expect(schema!.ge, `${cle} : ne devrait pas avoir de ge`).toBeNull();
        } else {
            expect(schema!.ge, `${cle} : borne basse inclusive`).toBe(borne.min);
            expect(schema!.gt, `${cle} : ne devrait pas avoir de gt`).toBeNull();
        }
    });

    it("couvrent TOUS les reglages numeriques bornes que nos sections affichent", () => {
        // The other direction: a numeric setting shown without a bound is an
        // unchecked field, and an unchecked field is a save that fails without
        // a word.
        const cles = [...CLES_TRANSCRIPTION, ...CLES_TOUR_DE_PAROLE, ...CLES_VOIX, ...CLES_RELANCE, ...CLES_ACCUEIL] as string[];
        const bornesAuSchema = cles.filter((cle) => {
            const s = bornesDuSchema(cle);
            return s !== null && (s.le !== null || s.lt !== null);
        });

        const nonCouvertes = bornesAuSchema.filter((cle) => !(cle in BORNES));
        expect(nonCouvertes).toEqual([]);

        // 🚨 Signale par la contre-relecture du 14/09, et ce n'etait pas
        // theorique : sans cette ligne, un champ que le parseur n'arrive PAS a
        // lire compte comme « non borne », sort du controle en silence, et on
        // retombe exactement dans le defaut que ce fichier ferme. Avec elle,
        // tout echec d'analyse devient rouge.
        expect(bornesAuSchema.length).toBe(Object.keys(BORNES).length);
    });

    it("couvrent aussi les LONGUEURS de texte que le schema plafonne", () => {
        // Oubliees au premier passage, trouvees par la relecture : les deux
        // consignes de relance sont plafonnees a 2000 caracteres cote serveur
        // et rien ne le disait a l'ecran.
        const cles = [...CLES_TRANSCRIPTION, ...CLES_TOUR_DE_PAROLE, ...CLES_VOIX, ...CLES_RELANCE, ...CLES_ACCUEIL] as string[];
        const textesPlafonnes = cles.filter((cle) => {
            const s = bornesDuSchema(cle);
            return s !== null && s.maxLength !== null && !s.estUneListe;
        });

        expect(textesPlafonnes.filter((cle) => !(cle in LONGUEURS_MAX))).toEqual([]);
        expect(textesPlafonnes.length).toBe(Object.keys(LONGUEURS_MAX).length);

        for (const cle of Object.keys(LONGUEURS_MAX)) {
            expect(bornesDuSchema(cle)?.maxLength, `${cle} : longueur maximale`)
                .toBe(LONGUEURS_MAX[cle]);
        }
    });

    it("couvrent aussi le NOMBRE D'ELEMENTS des listes plafonnees", () => {
        // 🚨 Trouve par le test ecrit pour le point precedent, pas par une
        // relecture : `tts_replacements` porte le MEME mot-cle `max_length`,
        // mais sur une `list[str]` Pydantic compte des ELEMENTS. Les confondre
        // aurait pose un plafond de 200 caracteres sur une liste de 200
        // entrees -- un reglage affiche dans un etat qui n'est pas le sien.
        const cles = [...CLES_TRANSCRIPTION, ...CLES_TOUR_DE_PAROLE, ...CLES_VOIX, ...CLES_RELANCE, ...CLES_ACCUEIL] as string[];
        const listesPlafonnees = cles.filter((cle) => {
            const s = bornesDuSchema(cle);
            return s !== null && s.maxLength !== null && s.estUneListe;
        });

        expect(listesPlafonnees.filter((cle) => !(cle in NOMBRE_MAX_ELEMENTS))).toEqual([]);
        expect(listesPlafonnees.length).toBe(Object.keys(NOMBRE_MAX_ELEMENTS).length);

        for (const cle of Object.keys(NOMBRE_MAX_ELEMENTS)) {
            expect(bornesDuSchema(cle)?.maxLength, `${cle} : nombre maximal d'elements`)
                .toBe(NOMBRE_MAX_ELEMENTS[cle]);
        }
    });
});

describe("Le message affiche sous un champ hors bornes", () => {
    it("se tait sur une valeur acceptable", () => {
        expect(messageHorsBornes("vad_stop_secs", 0.2)).toBeNull();
        expect(messageHorsBornes("vad_confidence", 0)).toBeNull(); // ge=0 : zero est legal
    });

    it("se tait sur un champ vide, qui n'est pas une erreur", () => {
        // Two settings sont legitimement vides : les declarer en erreur ferait
        // croire a un probleme la ou l'absence de valeur EST la bonne reponse.
        expect(messageHorsBornes("user_turn_stop_timeout", null)).toBeNull();
        expect(messageHorsBornes("stt_ttfs_p99_latency", undefined)).toBeNull();
    });

    it("refuse zero quand la borne est STRICTEMENT superieure a zero", () => {
        // Le scenario exact du signalement : une fleche de trop met le champ a
        // 0, le serveur rend 422, et jusqu'ici rien ne le disait.
        expect(messageHorsBornes("vad_stop_secs", 0)).toMatch(/greater than 0/i);
    });

    it("refuse une valeur au-dessus du plafond", () => {
        expect(messageHorsBornes("user_speech_timeout", 11)).toMatch(/at most 10/i);
    });

    it("ne dit rien d'un reglage qui n'a pas de borne", () => {
        expect(messageHorsBornes("turn_wait_for_transcript", 1)).toBeNull();
    });

    it("rend la liste des reglages fautifs d'un bloc entier", () => {
        expect(messagesHorsBornes({ vad_stop_secs: 0.2, vad_confidence: 0.7 })).toEqual({});
        expect(
            Object.keys(messagesHorsBornes({ vad_stop_secs: 0, vad_confidence: 5 })),
        ).toEqual(["vad_confidence", "vad_stop_secs"]);
    });
});
