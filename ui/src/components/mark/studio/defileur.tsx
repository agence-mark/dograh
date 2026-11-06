"use client";

import { ChevronLeft, ChevronRight } from "lucide-react";
import { useCallback, useEffect, useRef, useState } from "react";

import { useLangue } from "@/components/mark/langue/langue";

/**
 * [.mark] Partie 3, sous-lot 19 : toute rangée d'onglets passe par ici (règle d'Evan, 04/11), jamais un onglet caché ni
 * inaccessible. Des flèches apparaissent d'elles-mêmes dès que les onglets débordent (fondu léger), la molette fait
 * défiler de côté, et l'onglet cliqué est ramené dans la vue. Repris de `components/studio/barre-onglets.tsx` de la maquette.
 */
export function Defileur({ className = "", interieur = "", children }: { className?: string; interieur?: string; children: React.ReactNode }) {
    const { t } = useLangue();
    const zone = useRef<HTMLDivElement>(null);
    const [debord, setDebord] = useState({ gauche: false, droite: false });
    const mesurer = useCallback(() => {
        const z = zone.current;
        if (!z) return;
        const gauche = z.scrollLeft > 2;
        const droite = z.scrollLeft + z.clientWidth < z.scrollWidth - 2;
        setDebord((d) => (d.gauche === gauche && d.droite === droite ? d : { gauche, droite }));
    }, []);
    useEffect(() => {
        const z = zone.current;
        if (!z) return;
        mesurer();
        if (typeof ResizeObserver === "undefined") return;
        const ro = new ResizeObserver(mesurer);
        ro.observe(z);
        Array.from(z.children).forEach((c) => ro.observe(c));
        // L'onglet actif reste visible quand la largeur change.
        const actif = z.querySelector<HTMLElement>('[aria-selected="true"]');
        if (actif) {
            const a = actif.getBoundingClientRect();
            const b = z.getBoundingClientRect();
            if (a.left < b.left || a.right > b.right) z.scrollLeft += a.left - b.left - 24;
        }
        return () => ro.disconnect();
    }, [mesurer, children]);
    const defiler = (sens: number) => zone.current?.scrollBy?.({ left: sens * Math.max(160, (zone.current?.clientWidth ?? 300) * 0.6), behavior: "smooth" });
    const fleche = "absolute inset-y-0 z-10 flex cursor-pointer items-center px-1 text-muted-foreground hover:text-foreground";
    return (
        <div className={`relative flex min-w-0 ${className}`}>
            {debord.gauche && (
                <button type="button" aria-label={t({ en: "Previous tabs", fr: "Onglets précédents" })} onClick={() => defiler(-1)} className={`${fleche} left-0 bg-gradient-to-r from-card via-card to-transparent pr-4`}>
                    <ChevronLeft className="size-4" />
                </button>
            )}
            <div
                ref={zone}
                data-defileur=""
                onScroll={mesurer}
                onWheel={(e) => {
                    if (zone.current && Math.abs(e.deltaY) > Math.abs(e.deltaX)) zone.current.scrollLeft += e.deltaY;
                }}
                onClickCapture={(e) => (e.target as HTMLElement).closest("button, [role=tab]")?.scrollIntoView?.({ block: "nearest", inline: "nearest", behavior: "smooth" })}
                className={`flex min-w-0 flex-1 items-center gap-1 overflow-x-auto whitespace-nowrap [scrollbar-width:none] [&::-webkit-scrollbar]:hidden [&>*]:shrink-0 ${interieur}`}
            >
                {children}
            </div>
            {debord.droite && (
                <button type="button" aria-label={t({ en: "Next tabs", fr: "Onglets suivants" })} onClick={() => defiler(1)} className={`${fleche} right-0 bg-gradient-to-l from-card via-card to-transparent pl-4`}>
                    <ChevronRight className="size-4" />
                </button>
            )}
        </div>
    );
}
