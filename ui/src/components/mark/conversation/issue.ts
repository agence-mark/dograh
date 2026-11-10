/**
 * [.mark] Correctif écran point 9 : l'issue d'un appel dite en clair. Le serveur range l'appel sous un CODE (`mapped_call_disposition` :
 * « qualified », « entretien_reserve »…) ; l'écran n'a pas d'autre libellé que ce code et la description de l'issue, longue. Il n'existe
 * pas de table de libellés dans le code : les six issues de départ (`DEFAULT_CALL_DISPOSITION_OPTIONS`) sont dites ici, une issue propre à
 * l'agent est lue depuis son code (tirets bas en espaces, majuscule en tête). Un code qui n'est pas du texte ne montre rien.
 */
import type { Texte } from "../langue/langue";

const DE_DEPART: Record<string, Texte> = {
    qualified: { en: "Qualified", fr: "Objectif atteint" },
    not_interested: { en: "Not interested", fr: "Pas intéressé" },
    wrong_number: { en: "Wrong number", fr: "Mauvais numéro" },
    voicemail_detected: { en: "Voicemail", fr: "Répondeur" },
    do_not_call: { en: "Do not call again", fr: "Ne plus appeler" },
    callback_requested: { en: "Call back requested", fr: "Rappel demandé" },
};

/** « entretien_reserve » devient « Entretien reserve » : les accents d'un code ne se devinent pas. */
export const lireUnCode = (code: string) => {
    const texte = code.replace(/[_-]+/g, " ").trim();
    return texte ? texte.charAt(0).toUpperCase() + texte.slice(1) : "";
};

export function libelleDeLIssue(code: unknown, t: (texte: Texte) => string): string {
    if (typeof code !== "string" && typeof code !== "number") return "";
    const brut = String(code).trim();
    const connu = DE_DEPART[brut.toLowerCase()];
    return connu ? t(connu) : lireUnCode(brut);
}
