/**
 * [.mark] Builder partie 3, lots 8 et 22 (§ 3 bis) : les étiquettes d'OBJETS d'un prompt. Pur, sans écran.
 *
 * Le texte enregistré reste du texte : `{{outil:<uuid>}}`, `{{etape:<id>}}`, `{{agent:<id>}}`, `{{equipe:<code>}}`,
 * `{{document:<uuid>}}`, `{{phrase:<motif>}}`, `{{bloc:<slug>}}` (suit la dernière Recette) ou `{{bloc:<slug>@v2}}` (reste sur
 * la v2). La clé est l'identifiant de l'objet : le renommage est suivi. Le catalogue vient du serveur
 * (`GET /mark/etiquettes-prompt`) ; ici, on dit seulement comment une clé s'affiche et si elle est en erreur.
 */
import type { Texte } from "../langue/langue";

export type Famille = "outil" | "etape" | "agent" | "equipe" | "document" | "phrase" | "bloc";
export const FAMILLES: Famille[] = ["outil", "etape", "agent", "equipe", "document", "phrase", "bloc"];

/** Un objet citable, tel que le serveur le rend (`ObjetCitableVu`). */
export interface ObjetCitable {
    cle: string;
    famille: string;
    libelle: string;
    statut: string;
    resume?: string;
    rendu?: string;
    lignes?: string[][];
    etapes?: string[];
    version?: number | null;
    versions?: { numero?: number; statut?: string }[];
}

/** Couleur par famille (jetons de mark-theme.css, texte blanc, contraste >= 4,5:1, jamais d'orange) et mot de la famille devant la flèche. */
export const STYLE_FAMILLE: Record<Famille, { couleur: string; prefixe: Texte; pluriel: Texte }> = {
    outil: { couleur: "var(--famille-outil)", prefixe: { en: "Tool", fr: "Outil" }, pluriel: { en: "Tools", fr: "Outils" } },
    etape: { couleur: "var(--famille-etape)", prefixe: { en: "Step", fr: "Étape" }, pluriel: { en: "Steps", fr: "Étapes" } },
    agent: { couleur: "var(--famille-agent)", prefixe: { en: "Agent", fr: "Agent" }, pluriel: { en: "Agents", fr: "Agents" } },
    equipe: { couleur: "var(--famille-equipe)", prefixe: { en: "Team", fr: "Équipe" }, pluriel: { en: "Team and subjects", fr: "Équipe et sujets" } },
    document: { couleur: "var(--famille-document)", prefixe: { en: "Document", fr: "Document" }, pluriel: { en: "Documents", fr: "Documents" } },
    phrase: { couleur: "var(--famille-phrase)", prefixe: { en: "Sentence", fr: "Phrase" }, pluriel: { en: "Sentences", fr: "Phrases" } },
    bloc: { couleur: "var(--famille-bloc)", prefixe: { en: "Block", fr: "Bloc" }, pluriel: { en: "Blocks", fr: "Blocs" } },
};

export const famillesDe = (cle: string): Famille | null => {
    const i = cle.indexOf(":");
    if (i < 1) return null;
    const f = cle.slice(0, i) as Famille;
    return FAMILLES.includes(f) && cle.length > i + 1 ? f : null;
};
export const estObjet = (cle: string): boolean => famillesDe(cle) !== null;

/** `bloc:x@v2` -> { base: `bloc:x`, version: 2 } ; `bloc:x` -> { base: `bloc:x`, version: null }. */
export const versionDe = (cle: string): { base: string; version: number | null } => {
    const m = /^(bloc:[^@]+)@v([1-9]\d{0,3})$/.exec(cle);
    return m ? { base: m[1], version: Number(m[2]) } : { base: cle, version: null };
};

export type Motif = "introuvable" | "archive" | "brouillon" | "illisible" | "non_rattache" | "version_disparue" | "rejete" | "sans_recette";

export interface Resolu {
    cle: string;
    famille: Famille;
    libelle: string;
    objet?: ObjetCitable;
    epingle: number | null;
    motif?: Motif;
    message?: Texte;
}

/**
 * Résout une clé d'objet contre le catalogue. `outilsDeLEtape` : les outils rattachés à l'étape qui porte le texte (`null` = le
 * texte n'appartient pas à une étape : pas de contrôle « rattaché »). `lu` faux : rien n'est déclaré en erreur.
 */
export const resoudre = (cle: string, objets: ObjetCitable[], outilsDeLEtape: string[] | null, lu = true): Resolu => {
    const famille = famillesDe(cle) ?? "outil";
    const { base, version } = versionDe(cle);
    const objet = objets.find((o) => o.cle === base);
    const reste = cle.slice(cle.indexOf(":") + 1);
    const r: Resolu = { cle, famille, libelle: objet?.libelle ?? reste, objet, epingle: version };
    if (!lu) return r;
    if (!objet) return { ...r, motif: "introuvable", message: { en: `« ${reste} » does not exist (any more).`, fr: `« ${reste} » n'existe pas (ou plus).` } };
    const nom = objet.libelle;
    if (objet.statut === "archive") return { ...r, motif: "archive", message: { en: `« ${nom} » is archived.`, fr: `« ${nom} » est archivé.` } };
    if (objet.statut === "brouillon")
        return { ...r, motif: "brouillon", message: { en: `The tool « ${nom} » is still a draft.`, fr: `L'outil « ${nom} » est encore en brouillon.` } };
    if (objet.statut === "illisible")
        return { ...r, motif: "illisible", message: { en: `The document « ${nom} » could not be read.`, fr: `Le document « ${nom} » n'a pas pu être lu.` } };
    if (famille === "bloc") {
        const versions = objet.versions ?? [];
        if (version !== null) {
            const v = versions.find((x) => x.numero === version);
            if (!v) return { ...r, motif: "version_disparue", message: { en: `Version ${version} of « ${nom} » is gone.`, fr: `La version ${version} de « ${nom} » n'existe plus.` } };
            if (v.statut === "rejete") return { ...r, motif: "rejete", message: { en: `Version ${version} of « ${nom} » is rejected.`, fr: `La version ${version} de « ${nom} » est rejetée.` } };
        } else if (!objet.version) {
            return { ...r, motif: "sans_recette", message: { en: `« ${nom} » has no version in Recipe: nothing to follow.`, fr: `« ${nom} » n'a aucune version en Recette : rien à suivre.` } };
        }
    }
    if (famille === "outil" && outilsDeLEtape) {
        const uuid = reste.split("/")[0];
        if (!outilsDeLEtape.includes(uuid))
            return {
                ...r,
                motif: "non_rattache",
                message: { en: `The tool « ${nom} » is not attached to this step: the model would not see it.`, fr: `L'outil « ${nom} » n'est pas rattaché à cette étape : le modèle ne le verrait pas.` },
            };
    }
    return r;
};

/** Le texte de la pastille : « Outil › reserver », « Bloc › Politesse · v2 figée ». */
export const affiche = (r: Resolu, t: (x: Texte) => string): string => {
    const base = `${t(STYLE_FAMILLE[r.famille].prefixe)} › ${r.libelle}`;
    if (r.famille !== "bloc") return base;
    if (r.epingle !== null) return `${base} · ${t({ en: `v${r.epingle} kept`, fr: `v${r.epingle} figée` })}`;
    return r.objet?.version ? `${base} · v${r.objet.version}` : base;
};

/** Les clés d'objets citées dans un texte. */
export const clesObjetsDe = (texte: string): string[] => [...texte.matchAll(/\{\{\s*([^|\s}]+)\s*\}\}/g)].map((m) => m[1]).filter(estObjet);

/** Réécrit une étiquette de bloc dans un texte (suivre : `version` null). */
export const figerBloc = (texte: string, cle: string, version: number | null): string => {
    const base = versionDe(cle).base;
    return texte.replace(/\{\{\s*(bloc:[^@\s}|]+)(?:@v\d+)?\s*\}\}/g, (m, b: string) => (b === base ? `{{${base}${version ? `@v${version}` : ""}}}` : m));
};
