"use client";

/**
 * [.mark] The navigation on the right of a settings page: one entry per theme,
 * with the same two dots as the theme itself (convention E3). Choosing an entry
 * opens the theme and brings it on screen.
 */
import type { LucideIcon } from "lucide-react";

import { cn } from "@/lib/utils";

import { type Texte, useLangue } from "../langue/langue";
import { Pastilles } from "./Theme";

export interface EntreeNavigation {
    id: string;
    titre: Texte;
    icone: LucideIcon;
    modifie: boolean;
    enErreur: boolean;
}

export const NavigationThemes = ({
    entrees,
    actif,
    onChoisir,
}: {
    entrees: EntreeNavigation[];
    actif: string | null;
    onChoisir: (id: string) => void;
}) => {
    const { t } = useLangue();
    return (
        <nav aria-label={t({ en: "Themes", fr: "Thèmes" })} className="hidden w-48 shrink-0 lg:block">
            <div className="sticky top-20 space-y-1">
                <p className="mb-2 text-xs font-medium uppercase tracking-wider text-muted-foreground">
                    {t({ en: "On this page", fr: "Sur cette page" })}
                </p>
                {entrees.map(({ id, titre, icone: Icone, modifie, enErreur }) => (
                    <a
                        key={id}
                        href={`#${id}`}
                        data-navigation={id}
                        onClick={(e) => {
                            e.preventDefault();
                            onChoisir(id);
                        }}
                        className={cn(
                            "flex items-center gap-1.5 rounded-md px-2 py-1 text-sm transition-colors hover:text-foreground",
                            actif === id ? "font-medium text-foreground" : "text-muted-foreground",
                        )}
                    >
                        <Icone className="h-3.5 w-3.5 shrink-0" />
                        <span className="truncate">{t(titre)}</span>
                        <Pastilles modifie={modifie} enErreur={enErreur} />
                    </a>
                ))}
            </div>
        </nav>
    );
};
