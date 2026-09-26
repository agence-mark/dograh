"use client";

/**
 * [.mark] The FR / EN switch, in the footer of the sidebar (decision D10).
 *
 * Two buttons side by side rather than one that flips: the current language is
 * read at a glance, and pressing the one already chosen does nothing.
 */
import { cn } from "@/lib/utils";

import { type Langue, useLangue } from "./langue";

const LANGUES: Array<{ valeur: Langue; libelle: string; nom: string }> = [
    { valeur: "fr", libelle: "FR", nom: "Français" },
    { valeur: "en", libelle: "EN", nom: "English" },
];

export const BoutonLangue = ({ replie = false }: { replie?: boolean }) => {
    const { langue, choisir, t } = useLangue();
    return (
        <div
            role="group"
            aria-label={t({ en: "Language", fr: "Langue" })}
            className={cn(
                "inline-flex items-center gap-0.5 rounded-full border border-border/60 bg-muted/30 p-0.5 text-xs",
                replie && "flex-col",
            )}
        >
            {LANGUES.map(({ valeur, libelle, nom }) => (
                <button
                    key={valeur}
                    type="button"
                    lang={valeur}
                    title={nom}
                    aria-label={nom}
                    aria-pressed={langue === valeur}
                    onClick={() => choisir(valeur)}
                    className={cn(
                        "rounded-full px-2 py-0.5 font-medium transition-colors",
                        langue === valeur
                            ? "bg-background text-foreground shadow-sm"
                            : "text-muted-foreground hover:text-foreground",
                    )}
                >
                    {libelle}
                </button>
            ))}
        </div>
    );
};
