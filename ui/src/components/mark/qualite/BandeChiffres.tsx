"use client";

/** [.mark] U8 : la bande de chiffres de la maquette (`components/portail/accueil-blocs.tsx`), reprise telle quelle. */
import type { LucideIcon } from "lucide-react";

const COLONNES: Record<number, string> = { 2: "lg:grid-cols-2", 3: "lg:grid-cols-3", 4: "lg:grid-cols-4", 5: "lg:grid-cols-5" };

export function BandeChiffres({
    chiffres,
    colonnes = 5,
}: {
    chiffres: { icone: LucideIcon; libelle: string; valeur: string; phrase: React.ReactNode }[];
    colonnes?: number;
}) {
    return (
        <div className="rounded-xl border bg-card text-card-foreground">
            <div className={`grid grid-cols-1 divide-y border-border sm:grid-cols-2 lg:divide-x lg:divide-y-0 ${COLONNES[colonnes]}`}>
                {chiffres.map((c) => (
                    <div key={c.libelle} className="space-y-3 p-4 sm:p-5">
                        <div className="flex items-center gap-1.5 text-muted-foreground">
                            <c.icone className="size-4" />
                            <span className="text-xs font-medium sm:text-sm">{c.libelle}</span>
                        </div>
                        <p className="text-2xl font-semibold tracking-tight sm:text-[28px]">{c.valeur}</p>
                        <p className="text-xs leading-snug text-muted-foreground sm:text-sm">{c.phrase}</p>
                    </div>
                ))}
            </div>
        </div>
    );
}
