/**
 * [.mark] Clôture, É36 : les trois colonnes de la page Versions d'un agent, écrites à partir des données NEUTRES du serveur
 * (jamais de phrase côté serveur) : « Ce qui change », « Par » et « Tests ». Une version d'avant l'enregistrement n'a rien : « – ».
 */
import type { WorkflowVersionResponse } from "@/client/types.gen";
import type { Langue } from "@/components/mark/langue/langue";

export const VIDE = "–";

const nombre = (valeur: unknown): number => (typeof valeur === "number" && Number.isFinite(valeur) ? valeur : 0);
const noms = (valeur: unknown): string[] => (Array.isArray(valeur) ? valeur.filter((n): n is string => typeof n === "string") : []);

type Mots = { un: string; plusieurs: string };
const ETAPES = {
    ajoutees: { fr: { un: "étape ajoutée", plusieurs: "étapes ajoutées" }, en: { un: "step added", plusieurs: "steps added" } },
    retirees: { fr: { un: "étape retirée", plusieurs: "étapes retirées" }, en: { un: "step removed", plusieurs: "steps removed" } },
    modifiees: { fr: { un: "étape modifiée", plusieurs: "étapes modifiées" }, en: { un: "step changed", plusieurs: "steps changed" } },
} satisfies Record<string, Record<Langue, Mots>>;
const LIAISONS: Record<Langue, Mots> = { fr: { un: "liaison", plusieurs: "liaisons" }, en: { un: "link", plusieurs: "links" } };
const REGLAGES: Record<Langue, Mots> = { fr: { un: "réglage", plusieurs: "réglages" }, en: { un: "setting", plusieurs: "settings" } };

const accorder = (n: number, mots: Mots) => `${n} ${n > 1 ? mots.plusieurs : mots.un}`;

/** « 2 étapes modifiées (Accueil, Fin), 1 réglage » ; « Aucun changement » si la version ne change rien ; « – » sans résumé. */
export function phraseDesChangements(resume: WorkflowVersionResponse["resume_changements"], langue: Langue): string {
    if (!resume) return VIDE;
    if (nombre(resume.total) === 0) return langue === "fr" ? "Aucun changement" : "No change";
    const morceaux: string[] = [];
    for (const [cle, nomsCle, mots] of [
        ["etapes_ajoutees", "noms_ajoutees", ETAPES.ajoutees],
        ["etapes_retirees", "noms_retirees", ETAPES.retirees],
        ["etapes_modifiees", "noms_modifiees", ETAPES.modifiees],
    ] as const) {
        const n = nombre(resume[cle]);
        if (n === 0) continue;
        const liste = noms(resume[nomsCle]);
        const suite = liste.length ? ` (${liste.join(", ")}${n > liste.length ? "…" : ""})` : "";
        morceaux.push(`${accorder(n, mots[langue])}${suite}`);
    }
    if (nombre(resume.liaisons)) morceaux.push(accorder(nombre(resume.liaisons), LIAISONS[langue]));
    if (nombre(resume.reglages)) morceaux.push(accorder(nombre(resume.reglages), REGLAGES[langue]));
    return morceaux.length ? morceaux.join(", ") : VIDE;
}

/** « Builder », « Evan », « Clé du portail », avec « , accepté par Pierre » quand une personne a accepté. */
export function libelleDeLAuteur(v: Pick<WorkflowVersionResponse, "auteur_type" | "auteur_nom" | "accepte_par" | "accepte_par_nom">, langue: Langue): string {
    const fr = langue === "fr";
    let par: string;
    if (v.auteur_type === "builder") par = "Builder";
    else if (v.auteur_type === "personne") par = v.auteur_nom || (fr ? "Une personne" : "A person");
    else if (v.auteur_type === "cle_api") par = v.auteur_nom || (fr ? "Clé d'API" : "API key");
    else return VIDE;
    if (!v.accepte_par) return par;
    const qui = v.accepte_par_nom || (fr ? "une personne" : "a person");
    return fr ? `${par}, accepté par ${qui}` : `${par}, accepted by ${qui}`;
}

/** « 21/24 », ou « – » quand aucun test gardé n'a joué cette version. */
export function libelleDesTests(v: Pick<WorkflowVersionResponse, "tests_reussis" | "tests_total">): string {
    return typeof v.tests_total === "number" && v.tests_total > 0 && typeof v.tests_reussis === "number" ? `${v.tests_reussis}/${v.tests_total}` : VIDE;
}
