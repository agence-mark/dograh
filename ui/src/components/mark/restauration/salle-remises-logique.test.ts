/**
 * [.mark] Module Restauration, lot 13 (F6, F7) : la logique pure des écrans Salle et Remises.
 *
 * | Test | Ce qu'il prouve |
 * |---|---|
 * | créneaux | la grille peinte et les créneaux du serveur se répondent (aller et retour sans perte) ; un créneau hors de la grille est gardé tel quel ; les mêmes heures sur plusieurs jours font un seul créneau |
 * | plan | deux tables qui se chevauchent, une table qui sort du plan et des couverts incomplets sont signalés |
 * | remises | les douze mécanismes s'écrivent dans la forme que le comptoir lit et se relisent à l'identique ; ce qui manque est refusé avec une phrase, jamais une remise annoncée et non appliquée |
 */
import { describe, expect, it } from "vitest";

import { MECANISMES, type RemiseLue } from "./donnees-salle";
import { depuisLaBase, versLaBase } from "./remises";
import { grilleDe, problemesDuPlan, servicesDe } from "./salle";

const t = (fr: string) => fr;

describe("[.mark] créneaux de la salle", () => {
    const services = [
        { nom: "Midi", jours: [2, 3, 4, 5, 6], debut: "11:30", fin: "14:00", pas_minutes: 15 },
        { nom: "Soir", jours: [2, 3, 4, 5, 6, 7], debut: "18:30", fin: "22:30", pas_minutes: 30 },
    ];
    it("la grille peinte redonne les mêmes créneaux (noms et pas gardés, jours regroupés)", () => {
        const grille = grilleDe(services);
        expect(grille[0].every((c) => !c)).toBe(true); // lundi : rien
        expect(grille[1][1]).toBe(true); // mardi 11 h 30
        expect(grille[1][0]).toBe(false);
        expect(servicesDe(grille, services)).toEqual(services);
    });
    it("un créneau hors de la grille est gardé tel quel, jamais perdu", () => {
        const tardif = { nom: "Nuit", jours: [5], debut: "23:00", fin: "23:30", pas_minutes: 30 };
        const rendu = servicesDe(grilleDe([...services, tardif]), [...services, tardif]);
        expect(rendu).toContainEqual(tardif);
        expect(rendu).toHaveLength(3);
    });
    it("repeindre une case change le créneau", () => {
        const grille = grilleDe(services);
        grille[1][0] = true; // mardi 11 h
        const rendu = servicesDe(grille, services);
        expect(rendu.find((s) => s.jours.length === 1 && s.jours[0] === 2)).toMatchObject({ debut: "11:00", fin: "14:00" });
    });
});

describe("[.mark] problèmes d'un plan", () => {
    const table = (id: string, x: number, y: number, extra = {}) => ({ id, nom: `T${id}`, forme: "carree" as const, x, y, l: 2, h: 2, couverts_min: 2, couverts_max: 4, assemblable_avec: [], ...extra });
    it("signale le chevauchement, la sortie du plan et les couverts à compléter", () => {
        const salle = { id: "1", nom: "S", elements: [], tables: [table("1", 1, 1), table("2", 2, 1), table("3", 19, 1), table("4", 6, 6, { couverts_min: 5, couverts_max: 2 })] };
        const dits = problemesDuPlan(salle).map((p) => p.fr).join(" | ");
        expect(dits).toContain("se chevauchent");
        expect(dits).toContain("sort du plan");
        expect(dits).toContain("couverts");
    });
    it("un plan net n'a aucun problème", () => {
        expect(problemesDuPlan({ id: "1", nom: "S", elements: [], tables: [table("1", 1, 1), table("2", 4, 1)] })).toEqual([]);
    });
});

describe("[.mark] les douze mécanismes de remise", () => {
    const base = { cible: { categories: [], codes: [] }, cases: [], effetSeuil: "pourcentage" as const };
    const cible = { categories: [], codes: ["PIZ-1"] };
    const cas: Record<string, { a: string; b: string; cible?: typeof cible; cases?: { categorie: string; quantite: number }[]; effetSeuil?: "pourcentage" | "montant" }> = {
        pourcentage: { a: "10", b: "" },
        montant: { a: "3", b: "" },
        x_achetes_y_offert: { a: "3", b: "1", cible },
        deuxieme_moitie_prix: { a: "50", b: "2", cible },
        prix_du_jour: { a: "9", b: "", cible },
        seuil_panier: { a: "30", b: "10", effetSeuil: "pourcentage" },
        passage_en_menu: { a: "12", b: "", cases: [{ categorie: "pizzas", quantite: 1 }, { categorie: "boissons", quantite: 1 }] },
        taille_superieure: { a: "PIZ-M", b: "", cible: { categories: [], codes: ["PIZ-L"] } },
        offre_famille: { a: "35", b: "", cases: [{ categorie: "pizzas", quantite: 2 }, { categorie: "boissons", quantite: 2 }] },
        creneau: { a: "15", b: "" },
        nouveaute: { a: "9", b: "", cible },
        fidelite: { a: "10", b: "100" },
    };
    it("couvre les douze mécanismes du serveur", () => {
        expect(Object.keys(cas).sort()).toEqual([...MECANISMES].sort());
    });
    it.each(MECANISMES)("%s s'écrit puis se relit à l'identique", (mecanisme) => {
        const reglage = { ...base, mecanisme, ...cas[mecanisme] };
        const ligne = versLaBase(reglage, ["emporter"], t);
        const lue: RemiseLue = {
            id: 1, nom: "x", mecanisme, ...ligne, cumul: "exclusive", limite: null, phrase: null, moment: null, debut: null, fin: null, etat: "brouillon", ref_caisse: null,
            source: "portail", maj_le: "2026-11-16T00:00:00Z", utilisations: 0, ca_centimes: 0, remise_centimes: 0,
        };
        const relue = depuisLaBase(lue);
        expect(relue).not.toBeNull();
        expect(relue!.modes).toEqual(["emporter"]);
        expect(relue!.reglage).toMatchObject({ mecanisme, a: reglage.a, b: reglage.b });
        expect(relue!.reglage.cible).toEqual(reglage.cible);
    });
    it("écrit les montants en centimes et les pourcentages tels quels", () => {
        expect(versLaBase({ ...base, mecanisme: "montant", a: "3,50", b: "" }, [], t).effet).toEqual({ montant: 350 });
        expect(versLaBase({ ...base, mecanisme: "pourcentage", a: "12,5", b: "" }, [], t).effet).toEqual({ pourcentage: 12.5 });
        expect(versLaBase({ ...base, mecanisme: "seuil_panier", a: "30", b: "4,5", effetSeuil: "montant" }, [], t)).toMatchObject({ declencheur: { minimum: 3000 }, effet: { montant: 450 } });
    });
    it("refuse avec une phrase ce qui manque", () => {
        expect(() => versLaBase({ ...base, mecanisme: "pourcentage", a: "0", b: "" }, [], t)).toThrow(/pourcentage/);
        expect(() => versLaBase({ ...base, mecanisme: "prix_du_jour", a: "9", b: "" }, [], t)).toThrow(/article/);
        expect(() => versLaBase({ ...base, mecanisme: "passage_en_menu", a: "12", b: "", cases: [{ categorie: "", quantite: 1 }] }, [], t)).toThrow(/Composez/);
        expect(() => versLaBase({ ...base, mecanisme: "fidelite", a: "1", b: "10" }, [], t)).toThrow(/entier/);
    });
    it("une ligne de la caisse ou de .mark (forme inconnue) reste en lecture seule", () => {
        const etrangere: RemiseLue = {
            id: 2, nom: "Caisse", mecanisme: "pourcentage", declencheur: {}, effet: { autre: 1 }, perimetre: {}, cumul: "exclusive", limite: null, phrase: null, moment: null, debut: null, fin: null,
            etat: "active", ref_caisse: "C1", source: "caisse", maj_le: "2026-11-16T00:00:00Z", utilisations: 0, ca_centimes: 0, remise_centimes: 0,
        };
        expect(depuisLaBase(etrangere)).toBeNull();
    });
});
