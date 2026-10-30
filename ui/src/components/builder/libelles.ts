/**
 * [.mark] builder-agent-vocal (lot 2): the words of the Library page, in both languages (convention T2).
 */
import type { Texte } from "@/components/mark/langue/langue";

export type StatutDeLaBibliotheque = "candidat" | "recette" | "rejete";

export const STATUTS: Record<StatutDeLaBibliotheque, { texte: Texte; classe: string; aide: Texte }> = {
    candidat: {
        texte: { en: "Candidate", fr: "Candidat" },
        classe: "bg-amber-100 text-amber-900 dark:bg-amber-950 dark:text-amber-200",
        aide: { en: "Not proven on a bench yet.", fr: "Pas encore prouvé au banc." },
    },
    recette: {
        texte: { en: "Recipe", fr: "Recette" },
        classe: "bg-emerald-100 text-emerald-900 dark:bg-emerald-950 dark:text-emerald-200",
        aide: { en: "Proven on a bench, accepted by a person.", fr: "Prouvée au banc, acceptée par une personne." },
    },
    rejete: {
        texte: { en: "Rejected", fr: "Rejeté" },
        classe: "bg-red-100 text-red-900 dark:bg-red-950 dark:text-red-200",
        aide: { en: "Kept with its reason, never applied.", fr: "Gardé avec sa raison, jamais appliqué." },
    },
};

export const TYPES_DE_PROPOSITION: Record<"version" | "passage_recette" | "rejet", Texte> = {
    version: { en: "New version", fr: "Nouvelle version" },
    passage_recette: { en: "Move to Recipe", fr: "Passage en Recette" },
    rejet: { en: "Rejection", fr: "Rejet" },
};

export const GROUPES: Record<string, Texte> = {
    construit: { en: "What builds the agent", fr: "Ce qui construit l'agent" },
    travaille: { en: "What makes the agent work", fr: "Ce qui fait travailler l'agent" },
    regle: { en: "What sets the agent", fr: "Ce qui règle l'agent" },
    suit: { en: "What follows the call", fr: "Ce qui suit l'appel" },
    site: { en: "The website", fr: "Le site" },
    prouve: { en: "What proves the agent", fr: "Ce qui prouve l'agent" },
    guide: { en: "What guides the builder", fr: "Ce qui guide le builder" },
};

export const dateCourte = (iso?: string | null) => (iso ? iso.slice(0, 16).replace("T", " ") : "");
