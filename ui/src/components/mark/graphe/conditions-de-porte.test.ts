/** [.mark] Partie 3, sous-lot 21 : la condition d'une porte, lue et écrite par la fenêtre de la transition. */
import { readFileSync } from "node:fs";
import { join } from "node:path";

import { describe, expect, it } from "vitest";

import {
    COMPARAISONS,
    COMPARAISONS_PAR_SOURCE,
    ecrireLaCondition,
    fauteDeLaRegle,
    lireLaCondition,
    quiDecide,
    sansEffet,
    SOURCES,
} from "./conditions-de-porte";

describe("conditions de porte", () => {
    it("la forme d'avant revient telle quelle (un agent d'avant garde un JSON identique)", () => {
        for (const avant of [{ etape_complete: true }, { champ: "objet", vaut: "refusé" }, { champ: "objet" }]) {
            expect(ecrireLaCondition(lireLaCondition(avant))).toEqual(avant);
        }
        expect(lireLaCondition(undefined).genre).toBe("modele");
        expect(ecrireLaCondition(lireLaCondition(undefined))).toBeUndefined();
    });

    it("les nouveautés s'écrivent dans la même condition", () => {
        const regles = [
            { source: "outil" as const, champ: "reserver_creneau", comparaison: "a_reussi" },
            { source: "heure" as const, champ: "heure", comparaison: "apres", valeur: "18:00" },
        ];
        const ecrite = ecrireLaCondition({ genre: "regles", regles, combien: "au_moins_une" });
        expect(ecrite).toEqual({ regles, combien: "au_moins_une" });
        expect(lireLaCondition(ecrite)).toEqual({ genre: "regles", combien: "au_moins_une", regles: regles.map((r) => ({ valeur: "", ...r })) });
        expect(ecrireLaCondition({ genre: "sinon", regles: [], combien: "toutes" })).toEqual({ sinon: true });
        expect(ecrireLaCondition({ genre: "toujours", regles, combien: "toutes" })).toEqual({ toujours: true });
        // Une valeur saisie puis une comparaison qui n'en veut pas : la valeur n'est pas écrite.
        expect(ecrireLaCondition({ genre: "regles", regles: [{ source: "outil", champ: "x", comparaison: "a_echoue", valeur: "reste" }, regles[1]], combien: "toutes" }))
            .toEqual({ regles: [{ source: "outil", champ: "x", comparaison: "a_echoue" }, regles[1]], combien: "toutes" });
    });

    it("une seule règle hors de la forme d'avant reste une règle", () => {
        const une = { source: "fiche" as const, champ: "age", comparaison: "plus_grand", valeur: "18" };
        expect(ecrireLaCondition({ genre: "regles", regles: [une], combien: "toutes" })).toEqual({ regles: [une], combien: "toutes" });
    });

    it("dit ce qu'il manque à une règle, sous la règle", () => {
        expect(fauteDeLaRegle({ source: "fiche", champ: "", comparaison: "est", valeur: "x" })?.fr).toMatch(/champ/);
        expect(fauteDeLaRegle({ source: "fiche", champ: "motif", comparaison: "est", valeur: "" })?.fr).toMatch(/valeur/);
        expect(fauteDeLaRegle({ source: "heure", champ: "heure", comparaison: "apres", valeur: "midi" })?.fr).toMatch(/18:00/);
        expect(fauteDeLaRegle({ source: "etape", comparaison: "est_complete" })).toBeNull();
        expect(fauteDeLaRegle({ source: "outil", champ: "reserver", comparaison: "a_reussi" })).toBeNull();
    });

    it("une condition du code est sans effet quand le modèle décide à l'étape", () => {
        expect(quiDecide(undefined)).toBe("agent");
        expect(quiDecide("choix")).toBe("choix");
        expect(sansEffet("regles", "agent")).toBe(true);
        expect(sansEffet("sinon", "agent")).toBe(true);
        expect(sansEffet("modele", "agent")).toBe(false);
        expect(sansEffet("regles", "collecte")).toBe(false);
    });

    it("mêmes listes fermées que le serveur (conditions_de_porte.py)", () => {
        const serveur = readFileSync(join(process.cwd(), "..", "api", "services", "workflow", "conditions_de_porte.py"), "utf8");
        for (const s of SOURCES) expect(serveur, s.id).toContain(`"${s.id}"`);
        for (const c of Object.keys(COMPARAISONS)) expect(serveur, c).toContain(`"${c}"`);
        for (const [source, cs] of Object.entries(COMPARAISONS_PAR_SOURCE)) for (const c of cs) expect(Object.keys(COMPARAISONS), `${source}:${c}`).toContain(c);
    });
});
