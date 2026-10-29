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
    retenue_verite: { en: "Action held back by the truth check", fr: "Action retenue par la vérité des actions" },
};

/**
 * What the code wrote as a reason, in plain words (the technical value stays shown second). Keyed by the technical value;
 * the line of a held-back action starts with its kind (`date_non_trouvee : <tool> : <detail>`). An unknown value is shown
 * as it is.
 */
export const MOTIFS_DU_CODE: Record<string, Texte> = {
    // impasse (phrase reasons)
    impasse: { en: "The agent kept repeating itself", fr: "L'agent tournait en rond" },
    impasse_repetee: { en: "Second dead end in the same call", fr: "Deuxième impasse dans le même appel" },
    // transitions by the code that did not go through
    refusee: { en: "The exit was refused", fr: "La sortie a été refusée" },
    inconnue: { en: "The exit does not exist", fr: "La sortie n'existe pas" },
    greffier_sans_reponse: { en: "The clerk did not answer", fr: "Le greffier n'a pas répondu" },
    // actions held back by the truth check
    date_non_trouvee: { en: "A date the search never gave", fr: "Une date que la recherche n'a pas donnée" },
    ecriture_qui_tient: {
        en: "An action of the same tool already holds: replace or add?",
        fr: "Une action du même outil tient déjà : remplacer ou ajouter ?",
    },
    action_sans_resultat: { en: "Said an action was done, no tool did it", fr: "A dit une action faite, aucun outil ne l'a faite" },
    jour_faux: { en: "The weekday does not match the date", fr: "Le jour ne correspond pas à la date" },
};

/** For the types whose reason is a free value (a door name, a count): the words that introduce it. */
export const INTRODUCTION_DU_MOTIF: Record<string, Texte> = {
    desaccord: { en: "The arbiter proposed an exit other than the agent's", fr: "L'arbitre proposait une autre sortie que l'agent" },
    porte_inconnue: { en: "The arbiter chose an exit the step does not have", fr: "L'arbitre a choisi une sortie que l'étape n'a pas" },
    garde_modele: { en: "Delay overruns of the model in this call", fr: "Dépassements du délai du modèle dans cet appel" },
};

/** The plain label of a reason and what stays technical: `{ lisible, technique }`, `lisible` null when unknown. */
export function motifLisible(motif: string, type = ""): { lisible: Texte | null; technique: string } {
    const [premier, ...reste] = motif.split(" : ");
    const connu = MOTIFS_DU_CODE[premier.trim()];
    if (connu) return { lisible: connu, technique: reste.join(" : ") || premier };
    const introduction = INTRODUCTION_DU_MOTIF[type];
    if (introduction) return { lisible: introduction, technique: motif };
    return { lisible: null, technique: motif };
}
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
