"use client";

/**
 * [.mark] One setting as the convention shows it (E5): a readable label, its
 * TECHNICAL NAME in grey next to it, the existing help under the control, and
 * its bounds.
 *
 * The control itself is passed in untouched: this chantier moves settings, it
 * never changes the form of a control (D1). The wrapper carries
 * `data-reglage` so a test can find the setting ON SCREEN (convention § 5,
 * item 8), and the id `reglage-<key>` that « show » scrolls to (E7).
 */
import { createContext, type ReactNode, useContext } from "react";

import { Label } from "@/components/ui/label";
import { Info } from "@/components/mark/studio/marques";
import { cn } from "@/lib/utils";

import { BORNES } from "../bornes-reglages";
import { type Texte, useLangue } from "../langue/langue";
import { PastilleOrigine } from "./heritage";

/** « > 0 · ≤ 10 · optional », from the bounds the server enforces. */
export const texteBornes = (cle: string, facultatif = false): Texte | null => {
    const borne = BORNES[cle];
    const parties: Texte[] = [];
    if (borne) {
        parties.push({
            en: `${borne.minStrict ? ">" : "≥"} ${borne.min} · ≤ ${borne.max}`,
            fr: `${borne.minStrict ? ">" : "≥"} ${borne.min} · ≤ ${borne.max}`,
        });
    }
    if (facultatif) parties.push({ en: "optional", fr: "facultatif" });
    if (parties.length === 0) return null;
    return {
        en: parties.map((p) => p.en).join(" · "),
        fr: parties.map((p) => p.fr).join(" · "),
    };
};

/** A bounds line written by hand, for a Dograh setting whose bounds live in its own control. */
export const bornesDe = (min?: number, max?: number, strict = false): Texte | null => {
    if (min === undefined && max === undefined) return null;
    const bas = min === undefined ? "" : `${strict ? ">" : "≥"} ${min}`;
    const haut = max === undefined ? "" : `≤ ${max}`;
    const texte = [bas, haut].filter(Boolean).join(" · ");
    return { en: texte, fr: texte };
};

/**
 * [.mark] K3 : la fenêtre d'un thème de l'onglet Réglages d'un agent la fournit. Chaque réglage prend alors la ligne de la
 * maquette (`reglages-fenetre.tsx`, `Ligne`) : son nom en gras, la première phrase de l'aide dessous, le reste, les bornes
 * et le nom technique dans un « ! », le contrôle à droite quand c'est une bascule. L'unité d'un libellé « (secondes) »
 * passe à côté de la valeur (voir `ControleNombre`).
 */
export const ContexteLigneMaquette = createContext(false);

/** Le libellé sans son unité entre parenthèses, et l'unité courte (maquette : `decouper`). */
export const decouperUnite = (libelle: string): { nom: string; unite: string } => {
    const m = libelle.match(/^(.*?)\s*\(([^)]*)\)\s*$/);
    if (!m) return { nom: libelle, unite: "" };
    const brut = m[2].toLowerCase();
    const unite = brut === "secondes" || brut === "seconds" || brut === "s" ? "s" : brut === "millisecondes" || brut === "milliseconds" || brut === "ms" ? "ms" : "";
    return { nom: unite ? m[1] : libelle, unite };
};

/** La première phrase d'un texte d'aide ; le reste va dans le « ! ». */
const premierePhrase = (texte: string): [string, string] => {
    const morceaux = texte.split(/(?<=[.!?])\s+/);
    return [morceaux[0] ?? "", morceaux.slice(1).join(" ")];
};

export const ChampReglage = ({
    cle,
    idControle,
    libelle,
    aides = [],
    bornes = null,
    erreur = null,
    disposition = "colonne",
    note = null,
    variante = "reglage",
    sous = null,
    children,
}: {
    /** The technical name of the setting, shown in grey. */
    cle: string;
    /** The id of the control, for the label. */
    idControle?: string;
    libelle: Texte;
    aides?: Texte[];
    bornes?: Texte | null;
    erreur?: Texte | null;
    /** « ligne »: a switch, at the end of the label's line. */
    disposition?: "ligne" | "colonne";
    /** A notice above the help (a setting shown only to be fixed, for instance). */
    note?: Texte | null;
    /**
     * « noeud » (K2b) : la forme de la fenêtre d'un nœud (maquette `modale-noeud.tsx`) : le libellé et, dans un « ! », ses
     * explications, ses bornes et sa note ; ni le nom technique, ni la pastille d'origine. Le repère `data-reglage` reste.
     */
    variante?: "reglage" | "noeud";
    /** K3 : sous la ligne de la fenêtre d'un thème (le curseur d'un nombre borné). Sans effet hors de cette fenêtre. */
    sous?: ReactNode;
    children: ReactNode;
}) => {
    const { t } = useLangue();
    const ligneMaquette = useContext(ContexteLigneMaquette);
    if (variante === "noeud") {
        const explications = [note, ...aides, bornes].filter((x): x is Texte => x !== null);
        const etiquetteNoeud = (
            <Label htmlFor={idControle} className="flex items-center gap-1.5 text-sm">
                {t(libelle)}
                {explications.length > 0 && (
                    <Info>
                        <span className="grid gap-1.5">
                            {explications.map((e, i) => (
                                <span key={i}>{t(e)}</span>
                            ))}
                        </span>
                    </Info>
                )}
            </Label>
        );
        return (
            <div id={`reglage-${cle}`} data-reglage={cle} className="scroll-mt-24 space-y-1.5">
                {disposition === "ligne" ? (
                    <div className="flex items-center justify-between gap-4">
                        {etiquetteNoeud}
                        {children}
                    </div>
                ) : (
                    <>
                        {etiquetteNoeud}
                        {children}
                    </>
                )}
                {erreur && <p className="text-xs text-destructive">{t(erreur)}</p>}
            </div>
        );
    }
    if (ligneMaquette && variante === "reglage") {
        const [premiere, reste] = aides.length > 0 ? premierePhrase(t(aides[0])) : ["", ""];
        const suite = [reste || null, ...aides.slice(1).map((a) => t(a)), bornes ? t(bornes) : null].filter(
            (x): x is string => Boolean(x),
        );
        const nom = sous ? decouperUnite(t(libelle)).nom : t(libelle);
        const etiquetteMaquette = (
            <div className="min-w-0 flex-1">
                <Label htmlFor={idControle} className="flex items-center gap-1.5 text-sm leading-snug font-medium">
                    {nom}
                    <Info>
                        <span className="grid gap-1.5">
                            {suite.map((x, i) => (
                                <span key={i}>{x}</span>
                            ))}
                            <code className="text-[11px] opacity-80" data-cle-technique={cle}>
                                {cle}
                            </code>
                        </span>
                    </Info>
                    <PastilleOrigine cle={cle} />
                </Label>
                {premiere && <p className="mt-0.5 text-xs text-muted-foreground">{premiere}</p>}
            </div>
        );
        return (
            <div id={`reglage-${cle}`} data-reglage={cle} data-aide={aides.map((a) => t(a)).join(" ")} className="scroll-mt-24 space-y-2 py-3.5">
                {disposition === "ligne" ? (
                    <div className="flex items-start gap-4">
                        {etiquetteMaquette}
                        <div className="shrink-0">{children}</div>
                    </div>
                ) : (
                    <>
                        {etiquetteMaquette}
                        {children}
                    </>
                )}
                {sous}
                {note && <p className="text-xs text-foreground">{t(note)}</p>}
                {erreur && <p className="text-xs text-destructive">{t(erreur)}</p>}
            </div>
        );
    }
    const etiquette = (
        <span className="flex flex-wrap items-baseline gap-x-2 gap-y-0.5">
            <Label htmlFor={idControle} className={disposition === "ligne" ? "text-sm" : "text-xs"}>
                {t(libelle)}
            </Label>
            <code className="text-[11px] text-muted-foreground/80" data-cle-technique={cle}>
                {cle}
            </code>
            <PastilleOrigine cle={cle} />
        </span>
    );
    return (
        <div id={`reglage-${cle}`} data-reglage={cle} className="scroll-mt-24 space-y-2">
            {disposition === "ligne" ? (
                <div className="flex items-center justify-between gap-4">
                    {etiquette}
                    {children}
                </div>
            ) : (
                <>
                    {etiquette}
                    {children}
                </>
            )}
            {note && <p className="text-xs text-foreground">{t(note)}</p>}
            {erreur && <p className="text-xs text-destructive">{t(erreur)}</p>}
            {aides.map((aide, i) => (
                <p key={i} className="text-xs text-muted-foreground">
                    {t(aide)}
                </p>
            ))}
            {bornes && <p className={cn("text-[11px] text-muted-foreground/80")}>{t(bornes)}</p>}
        </div>
    );
};
