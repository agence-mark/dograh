/**
 * [.mark] U3 bis (E62, E63) : le texte d'un champ à étiquettes, découpé et recomposé. Pur, sans écran.
 *
 * Le moteur ne change pas : le texte enregistré reste `{{cle}}` ou `{{cle | fallback:repli}}`. Un champ à étiquettes ne
 * fait que montrer ces motifs comme des pastilles atomiques ; `decouper` puis `serialiser` redonnent le texte à
 * l'identique (aller-retour, testé), y compris pour un motif écrit à la main avec d'autres espaces.
 */

/** Le motif du moteur (`utils/template_renderer.py`) : `{{ cle }}`, `{{ cle | repli }}`, `{{ cle | fallback:repli }}`. */
const MOTIF = /\{\{\s*([^|\s}]+)(?:\s*\|\s*([^:}]+)(?::([^}]+))?)?\s*\}\}/g;

export type Source = "entreprise" | "appel" | "fiche" | "campagne";

export interface VariableCatalogue {
    cle: string;
    libelle: string;
    source: string;
    exemple?: string;
    description?: string;
}

export type Segment = { type: "texte"; texte: string } | { type: "variable"; cle: string; repli: string | null; brut: string };

/** Couleur par source (E63) : jeton de mark-theme.css clair et sombre, pastille pleine, texte blanc, contraste >= 4,5:1. Rouge réservé à l'inconnue. */
export const COULEUR_SOURCE: Record<Source | "inconnue", string> = {
    entreprise: "var(--source-entreprise)",
    appel: "var(--source-appel)",
    fiche: "var(--source-fiche)",
    campagne: "var(--source-campagne)",
    inconnue: "var(--source-inconnue)",
};

export const NOM_SOURCE: Record<Source, { en: string; fr: string }> = {
    entreprise: { en: "Company", fr: "Entreprise" },
    appel: { en: "Call", fr: "Appel" },
    fiche: { en: "Record", fr: "Fiche" },
    campagne: { en: "Campaign", fr: "Campagne" },
};

/** Les racines que le moteur lit sans les connaître d'avance (contexte de l'appel, résultats extraits). */
const RACINES_OUVERTES = ["initial_context", "gathered_context"];
const estDuMoteur = (cle: string) =>
    cle === "current_time" || cle === "current_weekday" || cle.startsWith("current_time_") || cle.startsWith("current_weekday_");

export const decouper = (texte: string): Segment[] => {
    const segments: Segment[] = [];
    let curseur = 0;
    for (const m of texte.matchAll(MOTIF)) {
        const debut = m.index ?? 0;
        if (debut > curseur) segments.push({ type: "texte", texte: texte.slice(curseur, debut) });
        const repli = m[2] === undefined ? null : m[3] !== undefined ? m[3].trim() : m[2].trim();
        segments.push({ type: "variable", cle: m[1], repli, brut: m[0] });
        curseur = debut + m[0].length;
    }
    if (curseur < texte.length) segments.push({ type: "texte", texte: texte.slice(curseur) });
    return segments;
};

/** Le texte du motif d'une variable. Un repli s'écrit `{{cle | fallback:repli}}` (la forme que le moteur connaît). */
export const motif = (cle: string, repli: string | null): string => (repli ? `{{${cle} | fallback:${repli}}}` : `{{${cle}}}`);

/** Un motif inchangé garde son écriture d'origine (`brut`) : l'aller-retour ne réécrit rien. */
export const serialiser = (segments: Segment[]): string =>
    segments.map((s) => (s.type === "texte" ? s.texte : s.brut)).join("");

/** Lot 8 : `outil:x`, `bloc:y@v2`… : une étiquette d'OBJET, jugée par son propre contrôle (`etiquettes-objets.ts`), jamais une variable. */
const FAMILLES_OBJETS = ["outil", "etape", "agent", "equipe", "document", "phrase", "bloc"];
const estUneEtiquetteDObjet = (cle: string) => {
    const i = cle.indexOf(":");
    return i > 0 && FAMILLES_OBJETS.includes(cle.slice(0, i)) && cle.length > i + 1;
};

export const estConnue = (cle: string, catalogue: VariableCatalogue[]): boolean => {
    if (estDuMoteur(cle) || estUneEtiquetteDObjet(cle)) return true;
    const racine = cle.split(".")[0];
    return RACINES_OUVERTES.includes(racine) || catalogue.some((v) => v.cle === cle || v.cle === racine);
};

export const parCle = (cle: string, catalogue: VariableCatalogue[]) => catalogue.find((v) => v.cle === cle);

/** Les clés citées que le catalogue ne connaît pas (sans doublon). */
export const clesInconnues = (texte: string, catalogue: VariableCatalogue[]): string[] => {
    const vues: string[] = [];
    for (const s of decouper(texte)) if (s.type === "variable" && !estConnue(s.cle, catalogue) && !vues.includes(s.cle)) vues.push(s.cle);
    return vues;
};

export const sourceDe = (cle: string, catalogue: VariableCatalogue[]): Source | "inconnue" => {
    if (!estConnue(cle, catalogue)) return "inconnue";
    if (estDuMoteur(cle) || RACINES_OUVERTES.includes(cle.split(".")[0])) return "appel";
    const source = parCle(cle, catalogue)?.source;
    return source === "entreprise" || source === "appel" || source === "fiche" || source === "campagne" ? source : "appel";
};

/** « Aperçu avec les valeurs » : chaque étiquette remplacée par son exemple, le repli si l'exemple est vide. Une étiquette d'objet
 * montre ce que le modèle recevra (le nom exact de la fonction d'un outil, le texte d'un bloc…). */
export const apercu = (texte: string, catalogue: VariableCatalogue[], objets?: { cle: string; rendu?: string }[]): string =>
    decouper(texte)
        .map((s) => {
            if (s.type === "texte") return s.texte;
            if (estUneEtiquetteDObjet(s.cle)) return objets?.find((o) => o.cle === s.cle.split("@")[0])?.rendu || `{{${s.cle}}}`;
            const exemple = parCle(s.cle, catalogue)?.exemple;
            return exemple || s.repli || `{{${s.cle}}}`;
        })
        .join("");
