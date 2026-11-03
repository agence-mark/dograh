/**
 * [.mark] U3 ter (E64) : les six GENRES du créateur de variable et la façon dont chacun se range dans les formes
 * EXISTANTES d'un objet (`mark_objets`) : aucun changement du moteur, aucune colonne de plus en base.
 *
 *   mot (texte) · nombre (nombre ou montant) · oui ou non · date  ->  forme « valeur », son type
 *   liste (puces)                                                  ->  forme « liste », UNE colonne
 *   tableau                                                        ->  forme « liste », une colonne ou plus
 *
 * Un tableau d'une seule colonne et une liste sont la même donnée : relu, il s'affiche en liste.
 */
import type { ObjetAgent, ObjetEnvoye } from "@/client/types.gen";

export type Genre = "mot" | "nombre" | "oui_non" | "date" | "liste" | "tableau";
export const GENRES: Genre[] = ["mot", "nombre", "oui_non", "date", "liste", "tableau"];

type TypeObjet = NonNullable<ObjetEnvoye["type"]>;

export const TYPE_DU_GENRE: Record<"mot" | "nombre" | "oui_non" | "date", TypeObjet> = {
    mot: "texte",
    nombre: "nombre",
    oui_non: "oui_non",
    date: "date",
};

/** Le nom de la colonne unique d'une liste à puces. */
export const COLONNE_DE_LISTE = "Élément";

export const genreDe = (objet: Pick<ObjetAgent, "forme" | "type" | "colonnes">): Genre => {
    if (objet.forme === "liste") return (objet.colonnes ?? []).length <= 1 ? "liste" : "tableau";
    switch (objet.type) {
        case "nombre":
        case "montant":
            return "nombre";
        case "oui_non":
            return "oui_non";
        case "date":
            return "date";
        default:
            return "mot";
    }
};

export const formeDuGenre = (genre: Genre): ObjetEnvoye["forme"] => (genre === "liste" || genre === "tableau" ? "liste" : "valeur");

/** Le nom technique calculé depuis le libellé : minuscules, sans accent, soulignés, commence par une lettre. */
export const nomTechnique = (libelle: string): string => {
    const base = libelle
        .normalize("NFD")
        .replace(/[̀-ͯ]/g, "")
        .toLowerCase()
        .replace(/[^a-z0-9]+/g, "_")
        .replace(/^_+|_+$/g, "")
        .slice(0, 60);
    return /^[a-z]/.test(base) ? base : base ? `v_${base}` : "";
};

/** Une phrase de prompt d'exemple, par genre, qui nomme l'étiquette. */
export const phraseDePrompt = (genre: Genre, nom: string): { en: string; fr: string } => {
    const v = `{{${nom || "nom"}}}`;
    switch (genre) {
        case "nombre":
            return { en: `The amount is ${v}.`, fr: `Le montant est de ${v}.` };
        case "oui_non":
            return { en: `Answer according to: ${v}.`, fr: `Réponds selon : ${v}.` };
        case "date":
            return { en: `The date to give is ${v}.`, fr: `La date à donner est le ${v}.` };
        case "liste":
            return { en: `Offer one of these choices:\n${v}`, fr: `Propose l'un de ces choix :\n${v}` };
        case "tableau":
            return { en: `Read the answer in this table:\n${v}`, fr: `Lis la réponse dans ce tableau :\n${v}` };
        default:
            return { en: `Say: ${v}.`, fr: `Dis : ${v}.` };
    }
};
