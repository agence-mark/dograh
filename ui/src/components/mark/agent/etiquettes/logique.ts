/**
 * [.mark] Les étiquettes des agents (U3, E30), la partie pure : ce que le filtre propose, ce qu'il garde, et la
 * sélection de la fenêtre « Étiquettes ». Les données viennent de `GET /etiquettes` ; aucune étiquette n'est écrite ici.
 */
import type { EtiquettesResponse } from "@/client/types.gen";

export const NOM_MAX = 40;

const cle = (nom: string) => nom.trim().replace(/\s+/g, " ").toLocaleLowerCase();

/** Ce que le filtre de la liste propose : une étiquette sans aucun agent actif en DISPARAÎT (elle reste à cocher à la pose). */
export const etiquettesDuFiltre = (donnees: EtiquettesResponse | null): string[] =>
    (donnees?.etiquettes ?? []).filter((e) => e.nb_agents > 0).map((e) => e.nom);

/** Les agents qui portent au moins une des étiquettes choisies ; aucune étiquette choisie = la liste entière. */
export function filtrerLesAgents<A extends { id: number }>(
    agents: A[],
    parAgent: EtiquettesResponse["par_agent"] | undefined,
    choisies: string[],
): A[] {
    if (choisies.length === 0) return agents;
    const voulues = new Set(choisies.map(cle));
    return agents.filter((a) => (parAgent?.[String(a.id)] ?? []).some((nom) => voulues.has(cle(nom))));
}

/** Coche ou décoche une étiquette de la sélection (la casse et les espaces ne font pas une autre étiquette). */
export function basculer(selection: string[], nom: string): string[] {
    const k = cle(nom);
    return selection.some((s) => cle(s) === k) ? selection.filter((s) => cle(s) !== k) : [...selection, nom];
}

export type AjoutRefuse = "vide" | "trop-long";

/**
 * Ajoute une étiquette tapée : une étiquette qui existe déjà (même écrite autrement) est simplement cochée avec sa
 * graphie d'origine ; une nouvelle est créée. Rend la nouvelle sélection et la liste des étiquettes connues.
 */
export function ajouter(
    saisie: string,
    selection: string[],
    connues: string[],
): { selection: string[]; connues: string[] } | AjoutRefuse {
    const nom = saisie.trim().replace(/\s+/g, " ");
    if (!nom) return "vide";
    if (nom.length > NOM_MAX) return "trop-long";
    const existante = connues.find((c) => cle(c) === cle(nom));
    const retenue = existante ?? nom;
    return {
        selection: selection.some((s) => cle(s) === cle(retenue)) ? selection : [...selection, retenue],
        connues: existante ? connues : [...connues, retenue],
    };
}
