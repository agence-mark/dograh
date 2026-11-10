/**
 * [.mark] Correctifs écran 7 et 12 : une valeur du contexte d'un appel dite en clair. Jamais un objet rendu tel quel dans du JSX
 * (c'est ce qui a planté au point 6) : tout sort en texte.
 */
import { lireUnCode } from "./issue";

export type OuiNon = readonly [string, string];
const FR: OuiNon = ["oui", "non"];

const texteCourt = (v: unknown, [oui, non]: OuiNon = FR): string => {
    if (v == null || v === "") return "";
    if (typeof v === "boolean") return v ? oui : non;
    if (typeof v === "string" || typeof v === "number") return String(v);
    return "";
};

/** Une commune ou une voie arrive en objet : `{ nom, codes_postaux }` devient « Verneuil-en-Halatte (60550) ». */
const objetEnClair = (o: Record<string, unknown>, on: OuiNon): string => {
    const nom = texteCourt(o.nom, on) || texteCourt(o.libelle) || texteCourt(o.label);
    if (nom) {
        const postaux = Array.isArray(o.codes_postaux) ? o.codes_postaux.map((x) => texteCourt(x, on)).filter(Boolean) : [];
        const code = postaux[0] || texteCourt(o.code_postal);
        return code ? `${nom} (${code})` : nom;
    }
    return Object.entries(o)
        .map(([cle, v]) => [lireUnCode(cle), valeurEnClair(v, on)] as const)
        .filter(([, v]) => v)
        .map(([cle, v]) => `${cle} : ${v}`)
        .join(" · ");
};

export function valeurEnClair(v: unknown, on: OuiNon = FR): string {
    if (Array.isArray(v)) return v.map((x) => valeurEnClair(x, on)).filter(Boolean).join(", ");
    if (v && typeof v === "object") return objetEnClair(v as Record<string, unknown>, on);
    return texteCourt(v, on);
}
