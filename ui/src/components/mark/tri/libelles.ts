/**
 * [.mark] passages-fiables (lot G): the words of the « To triage » and « Alerts » pages, written in both languages (T2).
 * The values sent to and read from the server are the technical ones (the keys of these tables).
 */
import type { Texte } from "../langue/langue";

export const STATUTS: { valeur: "ouvert" | "en cours" | "résolu" | "fusionné"; libelle: Texte }[] = [
    { valeur: "ouvert", libelle: { en: "Open", fr: "Ouvert" } },
    { valeur: "en cours", libelle: { en: "In progress", fr: "En cours" } },
    { valeur: "résolu", libelle: { en: "Resolved", fr: "Résolu" } },
    { valeur: "fusionné", libelle: { en: "Merged", fr: "Fusionné" } },
];

export const TYPES_DE_SIGNALEMENT: Record<string, Texte> = {
    agent: { en: "Flagged by the agent", fr: "Signalé par l'agent" },
    impasse: { en: "Conversation going in circles", fr: "Conversation qui tourne en rond" },
    porte_inconnue: { en: "Unknown exit chosen by the arbiter", fr: "Sortie inconnue choisie par l'arbitre" },
    desaccord: { en: "Agent and arbiter disagreed", fr: "L'agent et l'arbitre en désaccord" },
    passage_sans_suite: { en: "Transition by the code that did not go through", fr: "Passage par le code sans suite" },
    garde_modele: { en: "Model too slow, several times", fr: "Modèle trop lent, plusieurs fois" },
};

export const CATEGORIES: Record<string, Texte> = {
    "demande ambiguë": { en: "Ambiguous request", fr: "Demande ambiguë" },
    "règle inconnue": { en: "Unknown rule", fr: "Règle inconnue" },
    "outil en échec": { en: "Failing tool", fr: "Outil en échec" },
    autre: { en: "Other", fr: "Autre" },
};

export const TYPES_D_ALERTE: Record<string, Texte> = {
    appel_en_erreur: { en: "Call ended in error", fr: "Appel terminé en erreur" },
    outil_en_echec: { en: "Tool failure", fr: "Outil en échec" },
    panne_modele: { en: "Model outage", fr: "Panne du modèle" },
    transfert_echoue: { en: "Transfer failed", fr: "Transfert échoué" },
};

export const ETATS_DU_MAIL: Record<string, Texte> = {
    envoye: { en: "Mail sent", fr: "Mail envoyé" },
    non_envoye: { en: "Not mailed (no mail server): kept here", fr: "Pas de mail (aucun serveur) : gardée ici" },
    deja_notifiee: { en: "Already notified by the outage guard", fr: "Déjà notifiée par le gardien de panne" },
    en_cours: { en: "Mail being sent", fr: "Mail en cours d'envoi" },
};

export const SANS_MAIL: Texte = { en: "No mail (option off)", fr: "Pas de mail (option éteinte)" };
