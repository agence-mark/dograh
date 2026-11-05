/**
 * [.mark] Partie 3, sous-lot 21 : la condition complète d'une porte, côté écran. Le pendant de
 * `api/services/workflow/conditions_de_porte.py` : mêmes sources, mêmes comparaisons (listes fermées, tenues égales par
 * le test), même forme de donnée (`condition_sur_la_fiche` étendue, jamais une seconde structure).
 *
 * La fenêtre de la transition lit la condition en quatre genres (le modèle juge, des règles, sinon, toujours) ; à
 * l'enregistrement, une seule règle qui s'écrit dans la forme d'avant (« étape complète », « champ = valeur », « champ
 * rempli ») est écrite dans la forme d'avant : un agent qui n'utilise pas les nouveautés garde un JSON identique.
 */
import type { EdgeRecordCondition, RegleDePorte } from "@/components/flow/types";
import type { Texte } from "@/components/mark/langue/langue";

export type SourceRegle = RegleDePorte["source"];
export type GenreCondition = "modele" | "regles" | "sinon" | "toujours";
export type Combien = "toutes" | "au_moins_une";

export const SOURCES: { id: SourceRegle; nom: Texte }[] = [
    { id: "fiche", nom: { en: "The call record", fr: "La fiche de l'appel" } },
    { id: "etape", nom: { en: "The step", fr: "L'étape" } },
    { id: "outil", nom: { en: "A tool's result", fr: "Le résultat d'un outil" } },
    { id: "heure", nom: { en: "The time and day", fr: "L'heure et le jour" } },
    { id: "etablissement", nom: { en: "The establishment", fr: "L'établissement" } },
    { id: "variable", nom: { en: "A call variable", fr: "Une variable de l'appel" } },
];

export const COMPARAISONS: Record<string, Texte> = {
    est: { en: "is", fr: "est" },
    n_est_pas: { en: "is not", fr: "n'est pas" },
    contient: { en: "contains", fr: "contient" },
    est_rempli: { en: "is filled", fr: "est rempli" },
    est_vide: { en: "is empty", fr: "est vide" },
    plus_grand: { en: "is greater than", fr: "est plus grand que" },
    plus_petit: { en: "is less than", fr: "est plus petit que" },
    est_vrai: { en: "is true", fr: "est vrai" },
    est_faux: { en: "is false", fr: "est faux" },
    avant: { en: "is before", fr: "est avant" },
    apres: { en: "is after", fr: "est après" },
    a_reussi: { en: "succeeded", fr: "a réussi" },
    a_echoue: { en: "failed", fr: "a échoué" },
    a_repondu: { en: "answered", fr: "a répondu" },
    n_a_pas_repondu: { en: "never answered", fr: "n'a pas répondu" },
    est_complete: { en: "is complete", fr: "est complète" },
    n_est_pas_complete: { en: "is not complete", fr: "n'est pas complète" },
};

const VALEURS = ["est", "n_est_pas", "contient", "est_rempli", "est_vide", "plus_grand", "plus_petit"];
export const COMPARAISONS_PAR_SOURCE: Record<SourceRegle, string[]> = {
    fiche: VALEURS,
    variable: VALEURS,
    etape: ["est_complete", "n_est_pas_complete"],
    outil: ["a_reussi", "a_echoue", "a_repondu", "n_a_pas_repondu"],
    heure: ["avant", "apres", "est", "n_est_pas"],
    etablissement: ["est_vrai", "est_faux", "est", "n_est_pas", "contient", "est_rempli", "est_vide"],
};

/** Les champs fixes des sources qui ne lisent pas la donnée de l'agent ; les autres se saisissent. */
export const CHAMPS_FIXES: Partial<Record<SourceRegle, { id: string; nom: Texte }[]>> = {
    heure: [
        { id: "heure", nom: { en: "time", fr: "heure" } },
        { id: "jour", nom: { en: "day of the week", fr: "jour de la semaine" } },
    ],
    etablissement: [
        { id: "ouvert", nom: { en: "open now", fr: "ouvert maintenant" } },
        { id: "etat", nom: { en: "opening state", fr: "état d'ouverture" } },
        { id: "nom", nom: { en: "name", fr: "nom" } },
    ],
};

/** Les comparaisons d'un champ fixe (« ouvert maintenant » est vrai ou faux, « état » se compare). */
export function comparaisonsDe(source: SourceRegle, champ: string): string[] {
    if (source === "etablissement" && champ === "ouvert") return ["est_vrai", "est_faux"];
    if (source === "etablissement") return ["est", "n_est_pas", "contient", "est_rempli", "est_vide"];
    if (source === "heure" && champ === "jour") return ["est", "n_est_pas"];
    return COMPARAISONS_PAR_SOURCE[source];
}

const SANS_VALEUR = new Set(["est_rempli", "est_vide", "est_vrai", "est_faux", "a_reussi", "a_echoue", "a_repondu", "n_a_pas_repondu", "est_complete", "n_est_pas_complete"]);
export const sansValeur = (comparaison: string) => SANS_VALEUR.has(comparaison);

export function regleNeuve(source: SourceRegle = "fiche"): RegleDePorte {
    const champ = CHAMPS_FIXES[source]?.[0]?.id ?? "";
    return { source, champ, comparaison: comparaisonsDe(source, champ)[0], valeur: "" };
}

export type EtatCondition = { genre: GenreCondition; regles: RegleDePorte[]; combien: Combien };

/** La condition écrite, lue par la fenêtre. La forme d'avant devient une règle (rien n'est perdu ni deviné). */
export function lireLaCondition(c?: EdgeRecordCondition | null): EtatCondition {
    const combien: Combien = c?.combien === "au_moins_une" ? "au_moins_une" : "toutes";
    if (c?.sinon) return { genre: "sinon", regles: [], combien };
    if (c?.toujours) return { genre: "toujours", regles: [], combien };
    const regles: RegleDePorte[] = [];
    if (c?.etape_complete) regles.push({ source: "etape", champ: "", comparaison: "est_complete", valeur: "" });
    const champ = (c?.champ ?? "").trim();
    if (champ) {
        const vaut = (c?.vaut ?? "").trim();
        regles.push({ source: "fiche", champ, comparaison: vaut ? "est" : "est_rempli", valeur: vaut });
    }
    for (const r of c?.regles ?? []) regles.push({ ...r, champ: r.champ ?? "", valeur: r.valeur ?? "" });
    return regles.length ? { genre: "regles", regles, combien } : { genre: "modele", regles: [], combien };
}

const propre = (r: RegleDePorte): RegleDePorte => {
    const sortie: RegleDePorte = { source: r.source, comparaison: r.comparaison };
    const champ = (r.champ ?? "").trim();
    if (r.source !== "etape" && champ) sortie.champ = champ;
    const valeur = (r.valeur ?? "").trim();
    if (!sansValeur(r.comparaison) && valeur) sortie.valeur = valeur;
    return sortie;
};

/** Ce que la fenêtre enregistre. `undefined` = pas de condition (le modèle juge seul, comme avant). */
export function ecrireLaCondition(e: EtatCondition): EdgeRecordCondition | undefined {
    if (e.genre === "sinon") return { sinon: true };
    if (e.genre === "toujours") return { toujours: true };
    if (e.genre === "modele") return undefined;
    const regles = e.regles.map(propre).filter((r) => r.source === "etape" || r.champ);
    if (!regles.length) return undefined;
    if (regles.length === 1) {
        const [r] = regles;
        // La forme d'avant, quand elle suffit : le JSON d'un agent d'avant ne change pas.
        if (r.source === "etape" && r.comparaison === "est_complete") return { etape_complete: true };
        if (r.source === "fiche" && r.comparaison === "est" && r.valeur) return { champ: r.champ, vaut: r.valeur };
        if (r.source === "fiche" && r.comparaison === "est_rempli") return { champ: r.champ };
    }
    return { regles, combien: e.combien };
}

/** Ce qu'il manque à une règle pour être lue (une phrase sous la règle), ou `null`. */
export function fauteDeLaRegle(r: RegleDePorte): Texte | null {
    if (r.source !== "etape" && !(r.champ ?? "").trim()) return { en: "Name the field to read.", fr: "Nommez le champ à lire." };
    if (!sansValeur(r.comparaison) && !(r.valeur ?? "").trim()) return { en: "Enter the value to compare.", fr: "Saisissez la valeur à comparer." };
    if (r.source === "heure" && r.champ === "heure" && !/^\s*\d{1,2}\s*([:hH]\s*(\d{2})?)?\s*$/.test(r.valeur ?? ""))
        return { en: "A time such as 18:00.", fr: "Une heure comme 18:00." };
    return null;
}

/** Qui décide à l'étape source (`qui_decide_du_passage`) ; vide = le modèle (comportement d'avant). */
export type QuiDecide = "agent" | "collecte" | "choix" | "libre";
export const NOM_DECIDEUR: Record<QuiDecide, Texte> = {
    agent: { en: "The model", fr: "Le modèle" },
    collecte: { en: "The record", fr: "La fiche" },
    choix: { en: "The record, then the arbiter", fr: "La fiche puis l'arbitre" },
    libre: { en: "The arbiter", fr: "L'arbitre" },
};
export const quiDecide = (valeur: unknown): QuiDecide =>
    valeur === "collecte" || valeur === "choix" || valeur === "libre" ? valeur : "agent";

/** Les conditions du code (règles, sinon, toujours) ne jouent que si l'étape laisse le code lire ses portes. */
export const sansEffet = (genre: GenreCondition, qui: QuiDecide) => genre !== "modele" && qui === "agent";
