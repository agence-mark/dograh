/**
 * [.mark] V1b : le titre de la page d'une conversation, comme la maquette : « Motif · Issue ». Les deux sont lus dans le
 * contexte recueilli de l'appel, aux champs que lisent aussi les colonnes Motif et Issue de la liste des conversations
 * (`motif_appel` puis `motif` ; `mapped_call_disposition`). Sans l'un ni l'autre : le repli (le nom de l'agent).
 */
import type { Texte } from "../langue/langue";
import { libelleDeLIssue } from "./issue";

type Contexte = Record<string, unknown> | null | undefined;

const texteDe = (valeur: unknown) =>
    typeof valeur === "string" || typeof valeur === "number" ? String(valeur).trim() : "";

export function titreDeLaConversation(contexte: Contexte, repli: string, t?: (texte: Texte) => string) {
    const motif = texteDe(contexte?.motif_appel) || texteDe(contexte?.motif);
    // Point 9 : le libellé de l'issue, jamais le code brut (sans `t`, le code reste tel quel : appel d'avant le correctif).
    const issue = t ? libelleDeLIssue(contexte?.mapped_call_disposition, t) : texteDe(contexte?.mapped_call_disposition);
    return [motif, issue].filter(Boolean).join(" · ") || repli;
}
