/**
 * [.mark] R3 M5 : une erreur du serveur ne s'affiche jamais telle quelle.
 *
 * `echecAffiche(erreur)` pose le motif dans la notification (`notifier.echec(..., { erreur })`, lu par l'équipe seulement,
 * dans « Détails ») et rend la phrase fixe, dans la langue de l'écran, à mettre dans l'état d'erreur du composant.
 *
 * Seule exception : la faute d'un champ (422, `detail` en liste) : sa phrase de validation se lit sous le champ, sans
 * notification. Le test `aucune-erreur-brute.test.ts` échoue sur tout `detailFromError(` qui n'est pas un motif de `notifier`.
 */
import { langueActive, type Texte } from "@/components/mark/langue/langue";
import { detailFromError } from "@/lib/apiError";

import { notifier } from "./notifier";

export const ECHEC_GENERIQUE: Texte = { fr: "Cela n'a pas abouti. Réessayez.", en: "That did not work. Try again." };
/** Une erreur annoncée par le flux d'une conversation du builder : seule cette phrase se voit dans le fil. */
export const ECHEC_DU_FIL: Texte = { fr: "La conversation a rencontré une erreur. Réessayez.", en: "The conversation hit an error. Try again." };

/** Vrai pour une faute de validation de champ (422) : une liste de fautes, pas un texte interne du serveur. */
export const estFauteDeChamp = (erreur: unknown): boolean => Array.isArray((erreur as { detail?: unknown } | null | undefined)?.detail);

export function echecAffiche(erreur: unknown, texte: Texte = ECHEC_GENERIQUE): string {
    if (estFauteDeChamp(erreur)) return detailFromError(erreur, texte[langueActive()]);
    notifier.echec(texte, { erreur, groupe: "echec-ecran" });
    return texte[langueActive()];
}

/**
 * Comme `echecAffiche`, sans notification : pour un sondage répété (une alerte toutes les dix secondes serait pire que le mal)
 * ou un état d'erreur dont le motif est déjà posé ailleurs. Rend la phrase fixe, ou la faute d'un champ.
 */
export function phraseEchec(erreur: unknown, texte: Texte = ECHEC_GENERIQUE): string {
    return estFauteDeChamp(erreur) ? detailFromError(erreur, texte[langueActive()]) : texte[langueActive()];
}
