/**
 * [.mark] V1b : le titre de la page d'une conversation, comme la maquette : « Motif · Issue ». Les deux sont lus dans le
 * contexte recueilli de l'appel, aux champs que lisent aussi les colonnes Motif et Issue de la liste des conversations
 * (`motif_appel` puis `motif` ; `mapped_call_disposition`). Sans l'un ni l'autre : le repli (le nom de l'agent).
 */
type Contexte = Record<string, unknown> | null | undefined;

const texteDe = (valeur: unknown) =>
    typeof valeur === "string" || typeof valeur === "number" ? String(valeur).trim() : "";

export function titreDeLaConversation(contexte: Contexte, repli: string) {
    const motif = texteDe(contexte?.motif_appel) || texteDe(contexte?.motif);
    const issue = texteDe(contexte?.mapped_call_disposition);
    return [motif, issue].filter(Boolean).join(" · ") || repli;
}
