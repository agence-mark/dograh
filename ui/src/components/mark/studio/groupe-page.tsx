"use client";

import { Info } from "./marques";

/** Un intertitre de page de la maquette : petites capitales grises, son « ! » à côté (`Groupe` de `ecrans-organisation.tsx`). */
export function GroupePage({ titre, info }: { titre: string; info?: string }) {
    return (
        <h2 className="flex items-center gap-1.5 pt-8 -mb-4 text-xs font-medium tracking-wider text-muted-foreground uppercase">
            {titre}
            {info && <Info>{info}</Info>}
        </h2>
    );
}
