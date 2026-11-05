/**
 * [.mark] U8 : les mots de « À améliorer » (l'écran de la boucle), écrits dans les deux langues (T2).
 * Les valeurs envoyées au serveur et lues de lui sont les valeurs techniques (les clés de ces tables).
 */
import type { Texte } from "../langue/langue";
import { TYPES_DE_SIGNALEMENT } from "../tri/libelles";

export type EtatDeLEcran = "a_trier" | "en_cours" | "testee" | "publiee";
export const ETATS: { id: EtatDeLEcran; libelle: Texte }[] = [
    { id: "a_trier", libelle: { en: "To triage", fr: "À trier" } },
    { id: "en_cours", libelle: { en: "In progress", fr: "En cours" } },
    { id: "testee", libelle: { en: "Tested", fr: "Testée" } },
    { id: "publiee", libelle: { en: "Published", fr: "Publiée" } },
];

export const CAUSES: Record<string, Texte> = {
    prompt: { en: "Prompt", fr: "Prompt" },
    outil: { en: "Tool", fr: "Outil" },
    donnee: { en: "Data", fr: "Donnée" },
    voix: { en: "Voice", fr: "Voix" },
    moteur: { en: "Engine", fr: "Moteur" },
};

export const RELEVE_PAR: Record<string, Texte> = {
    juge: { en: "Judge", fr: "Juge" },
    code: { en: "Code", fr: "Code" },
    test: { en: "Test", fr: "Test" },
    equipe: { en: "Team", fr: "Équipe" },
    client: { en: "Client", fr: "Client" },
    deploiement: { en: "Rollout", fr: "Déploiement" },
};

/** Qui écrit le titre d'un problème (le « ! » de la ligne et du détail). */
export const AUTEUR: Record<string, Texte> = {
    juge: {
        en: "Title written by the judge: the criterion of its grid that failed.",
        fr: "Titre écrit par le juge : le critère de sa grille qui a échoué.",
    },
    code: {
        en: "Title given by the check of the code that raised the problem (or by the agent's own flag).",
        fr: "Titre donné par le contrôle du code qui a levé le problème (ou par le signalement de l'agent).",
    },
    test: { en: "Title = the test that failed or that has to be reviewed.", fr: "Titre = le test qui a échoué ou qui est à revoir." },
    equipe: { en: "Title written by the person who flagged it.", fr: "Titre écrit par la personne qui a signalé." },
    client: {
        en: "Flagged by the client from their portal.",
        fr: "Signalé par le client depuis son portail.",
    },
    deploiement: {
        en: "Raised by the progressive rollout: the new version does worse than the old one.",
        fr: "Posé par le déploiement progressif : la nouvelle version fait moins bien que l'ancienne.",
    },
};

export const TEMPS_DE_L_AVANCEMENT: Record<string, Texte> = {
    test_cree: { en: "Test created from the reply", fr: "Test créé depuis la réplique" },
    brouillon: { en: "Correction put in the draft", fr: "Correction posée dans le brouillon" },
    rejoue: { en: "Test suite replayed (N × 3)", fr: "Suite de tests rejouée (N × 3)" },
    publie: { en: "Published by a person", fr: "Publication par une personne" },
};

export const ORIGINES: Record<string, Texte> = {
    client: { en: "The client's sheet", fr: "La fiche du client" },
    recette: { en: "A library recipe", fr: "Une recette de la bibliothèque" },
    code: { en: "The code of the fork", fr: "Le code du fork" },
    // Partie 3, sous-lot 6 : une version qui fait moins bien que la précédente (alerte de déploiement).
    deploiement: { en: "A deployment (a version does worse)", fr: "Un déploiement (une version fait moins bien)" },
    // Partie 3, sous-lot 4 : une attaque de « Attaquer l'agent » qui a cédé.
    attaque: { en: "An attack that got through", fr: "Une attaque qui a cédé" },
};

/** Le titre à montrer : une trace du code connue est traduite, tout autre titre est celui du serveur. */
export function titreLisible(p: { releve_par: string; critere?: string | null; titre: string }): Texte | string {
    if (p.releve_par === "code" && p.critere && TYPES_DE_SIGNALEMENT[p.critere]) return TYPES_DE_SIGNALEMENT[p.critere];
    return p.titre;
}

/** Le message du builder qui ouvre une conversation depuis un problème (rien d'inventé : les données du problème seulement). */
export function demandeAuBuilder(p: { id?: number; titre: string; workflow_nom: string; etape?: string | null; replique?: string | null; frequence: unknown }): string {
    const { n, sur } = p.frequence as { n: number; sur: number };
    const lignes = [
        `Problème relevé sur l'agent « ${p.workflow_nom} » : ${p.titre}.`,
        p.etape ? `Étape : ${p.etape}.` : "",
        p.replique ? `Réplique fautive : « ${p.replique} »` : "",
        `Fréquence : ${n} sur ${sur}.`,
        // SE-17 (F-1) : le numéro du problème permet au builder d'écrire la correction proposée dans sa fiche.
        p.id !== undefined ? `Problème n° ${p.id} : donne ce numéro en amelioration_id quand tu proposes la correction, elle sera écrite dans la fiche du problème.` : "",
        "Analyse la cause, propose la correction en avant / après, puis rejoue la suite de tests.",
    ];
    return lignes.filter(Boolean).join("\n");
}

const FREQUENCE = {
    sur: { en: "of", fr: "sur" },
    appels: { en: "calls", fr: "appels" },
    appel: { en: "call", fr: "appel" },
    essais: { en: "attempts", fr: "essais" },
    essai: { en: "attempt", fr: "essai" },
    aRevoir: { en: "passed, to review", fr: "réussi, à revoir" },
};

/** « N appels sur M » pour un appel ; « k essais sur n » (les essais ratés) pour un test, « réussi, à revoir » s'ils ont tous réussi. */
export function texteDeFrequence(p: { frequence: unknown }, t: (x: Texte) => string): string {
    const { n, sur, genre } = p.frequence as { n: number; sur: number; genre: string };
    // Un seul : le singulier (« 1 appel sur 2 »).
    if (genre === "essais") return n === sur ? t(FREQUENCE.aRevoir) : `${sur - n} ${t(sur - n === 1 ? FREQUENCE.essai : FREQUENCE.essais)} ${t(FREQUENCE.sur)} ${sur}`;
    return `${n} ${t(n === 1 ? FREQUENCE.appel : FREQUENCE.appels)} ${t(FREQUENCE.sur)} ${sur}`;
}
