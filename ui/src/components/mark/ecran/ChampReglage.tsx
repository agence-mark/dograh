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
import type { ReactNode } from "react";

import { Label } from "@/components/ui/label";
import { cn } from "@/lib/utils";

import { BORNES } from "../bornes-reglages";
import { type Texte, useLangue } from "../langue/langue";

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

export const ChampReglage = ({
    cle,
    idControle,
    libelle,
    aides = [],
    bornes = null,
    erreur = null,
    disposition = "colonne",
    note = null,
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
    children: ReactNode;
}) => {
    const { t } = useLangue();
    const etiquette = (
        <span className="flex flex-wrap items-baseline gap-x-2 gap-y-0.5">
            <Label htmlFor={idControle} className={disposition === "ligne" ? "text-sm" : "text-xs"}>
                {t(libelle)}
            </Label>
            <code className="text-[11px] text-muted-foreground/80" data-cle-technique={cle}>
                {cle}
            </code>
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
            {note && <p className="text-xs text-amber-600 dark:text-amber-400">{t(note)}</p>}
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
