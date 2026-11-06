/**
 * [.mark] builder-agent-vocal (lot 2): the words of the Library page, in both languages (convention T2).
 */
import type { Texte } from "@/components/mark/langue/langue";

export type StatutDeLaBibliotheque = "candidat" | "recette" | "rejete";

export const STATUTS: Record<StatutDeLaBibliotheque, { texte: Texte; classe: string; aide: Texte }> = {
    candidat: {
        texte: { en: "Candidate", fr: "Candidat" },
        classe: "bg-(--signal-warn)/15 text-(--signal-warn)",
        aide: { en: "Not proven on a bench yet.", fr: "Pas encore prouvé au banc." },
    },
    recette: {
        texte: { en: "Recipe", fr: "Recette" },
        classe: "bg-(--signal-ok)/15 text-(--signal-ok)",
        aide: { en: "Proven on a bench, accepted by a person.", fr: "Prouvée au banc, acceptée par une personne." },
    },
    rejete: {
        texte: { en: "Rejected", fr: "Rejeté" },
        classe: "bg-(--signal-danger)/15 text-(--signal-danger)",
        aide: { en: "Kept with its reason, never applied.", fr: "Gardé avec sa raison, jamais appliqué." },
    },
};

export const TYPES_DE_PROPOSITION: Record<"version" | "passage_recette" | "rejet" | "fiche" | "famille", Texte> = {
    version: { en: "New version", fr: "Nouvelle version" },
    fiche: { en: "Sheet of a family", fr: "Fiche d'une famille" },
    famille: { en: "New family", fr: "Nouvelle famille" },
    passage_recette: { en: "Move to Recipe", fr: "Passage en Recette" },
    rejet: { en: "Rejection", fr: "Rejet" },
};

export const GROUPES: Record<string, Texte> = {
    construit: { en: "Build the agent", fr: "Construire l'agent" },
    travaille: { en: "Make the agent work", fr: "Faire travailler l'agent" },
    regle: { en: "Set the agent", fr: "Régler l'agent" },
    suit: { en: "Follow the call", fr: "Suivre l'appel" },
    site: { en: "The website", fr: "Le site" },
    prouve: { en: "Prove the agent", fr: "Prouver l'agent" },
    guide: { en: "Guide the builder", fr: "Guider le builder" },
};

export const dateCourte = (iso?: string | null) => (iso ? iso.slice(0, 16).replace("T", " ") : "");
