/**
 * [.mark] SE-28 : pour un test, la phrase d'échec attendue d'une action, dans l'une ou l'autre langue de l'écran
 * (`phraseAttendue(ECHECS.outilCreer)`), sans copier le texte dans le test.
 */
import type { Texte } from "@/components/mark/langue/langue";

const echappe = (texte: string) => texte.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");

export const phraseAttendue = (texte: Texte): RegExp => new RegExp(`${echappe(texte.fr)}|${echappe(texte.en)}`);
