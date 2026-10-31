/**
 * [.mark] builder-agent-vocal (lot 6): the words of the « Tests and corrections » page, in both languages (convention T2).
 */
import type { Texte } from "@/components/mark/langue/langue";

import type { StatutDeTest } from "./types";

export const STATUTS_DE_TEST: Record<StatutDeTest, { texte: Texte; classe: string }> = {
    ok: { texte: { en: "Passed", fr: "Réussi" }, classe: "bg-emerald-100 text-emerald-900 dark:bg-emerald-950 dark:text-emerald-200" },
    echec: { texte: { en: "Failed", fr: "Échec" }, classe: "bg-red-100 text-red-900 dark:bg-red-950 dark:text-red-200" },
    erreur: { texte: { en: "Could not run", fr: "Non jouable" }, classe: "bg-amber-100 text-amber-900 dark:bg-amber-950 dark:text-amber-200" },
};

export type ChampDeCritere = "texte" | "nom" | "attendue" | "noms" | "champs" | "max" | "ne_doit_pas_etre_appele";

/** The criteria the code judges (the judge never decides): what each one asks for. */
export const CRITERES: Record<string, { libelle: Texte; champs: ChampDeCritere[] }> = {
    texte_absent: { libelle: { en: "The agent never says…", fr: "L'agent ne dit jamais…" }, champs: ["texte"] },
    texte_present: { libelle: { en: "The agent says…", fr: "L'agent dit…" }, champs: ["texte"] },
    outil: { libelle: { en: "A tool is called", fr: "Un outil est appelé" }, champs: ["nom", "ne_doit_pas_etre_appele"] },
    etape: { libelle: { en: "The call reaches the step", fr: "L'appel arrive à l'étape" }, champs: ["attendue"] },
    issue: { libelle: { en: "The call ends with the outcome", fr: "L'appel se termine par l'issue" }, champs: ["attendue"] },
    appel_clos_par_l_agent: { libelle: { en: "The agent closes the call", fr: "L'agent clôt l'appel" }, champs: [] },
    mecanique_dite: { libelle: { en: "No tool or mechanic name is said", fr: "Aucun nom d'outil ou de mécanique n'est dit" }, champs: ["noms"] },
    merci_en_tete: { libelle: { en: "Replies starting with « Merci »", fr: "Répliques qui commencent par « Merci »" }, champs: ["max"] },
    coordonnees_prises: { libelle: { en: "The sheet holds the fields", fr: "La fiche contient les champs" }, champs: ["champs"] },
    sans_redite: { libelle: { en: "No repetition", fr: "Aucune redite" }, champs: [] },
    sans_rigidite: { libelle: { en: "No rigid re-asking", fr: "Aucune redemande rigide" }, champs: [] },
};

export const CHAMPS: Record<ChampDeCritere, Texte> = {
    texte: { en: "Text", fr: "Texte" },
    nom: { en: "Tool name", fr: "Nom de l'outil" },
    attendue: { en: "Expected", fr: "Attendu" },
    noms: { en: "Names (comma-separated)", fr: "Noms (séparés par des virgules)" },
    champs: { en: "Fields (comma-separated)", fr: "Champs (séparés par des virgules)" },
    max: { en: "At most", fr: "Au plus" },
    ne_doit_pas_etre_appele: { en: "Must NOT be called", fr: "Ne doit PAS être appelé" },
};

export const ORIGINES_DE_TEST: Record<string, Texte> = {
    client: { en: "Client", fr: "Client" },
    recette: { en: "Recipe", fr: "Recette" },
    code: { en: "Code", fr: "Code" },
    manuel: { en: "By hand", fr: "À la main" },
    fiche: { en: "From the sheet", fr: "Depuis la fiche" },
};

export const CAUSES: Record<string, Texte> = {
    agent: { en: "The agent", fr: "L'agent" },
    test: { en: "The test", fr: "Le test" },
    execution: { en: "The run", fr: "L'exécution" },
};

/** What each triage origin leads to (07-boucle-et-coherence § 2). */
export const ORIGINES_DE_TRI: Record<"client" | "recette" | "code", { libelle: Texte; suite: Texte }> = {
    client: {
        libelle: { en: "Client", fr: "Client" },
        suite: { en: "Fix the client sheet, then regenerate the step: this agent only.", fr: "Corriger la fiche du client, puis régénérer l'étape : cet agent seulement." },
    },
    recette: {
        libelle: { en: "Recipe", fr: "Recette" },
        suite: { en: "Propose a change to the library and prove it: every following agent benefits.", fr: "Proposer un changement à la bibliothèque et le prouver : tous les agents suivants en profitent." },
    },
    code: {
        libelle: { en: "Code", fr: "Code" },
        suite: { en: "A work item of the fork: every agent benefits once fixed.", fr: "Un chantier du fork : tous les agents en profitent une fois corrigé." },
    },
};

export const dateCourte = (iso?: string | null) => (iso ? iso.slice(0, 16).replace("T", " ") : "");
