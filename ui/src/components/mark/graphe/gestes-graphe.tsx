"use client";

/**
 * [.mark] T4 (lot « façon Tala par motif », Evan 05/11) : les gestes du graphe.
 * - la MOLETTE MAINTENUE (bouton du milieu) déplace la vue, où que soit la souris ;
 * - le CLIC GAUCHE MAINTENU sur le fond trace un rectangle de sélection : les étapes touchées sont entourées, le bandeau
 *   dit le nombre ; glisser l'une d'elles déplace tout le groupe (React Flow émet un changement de position par étape :
 *   toutes les positions sont enregistrées) ;
 * - Échap, ou un simple clic sur le fond, annule la sélection ; ouvrir une étape (double-clic, Entrée) ne change pas.
 * Le bouton du rectangle (gauche, convention Figma et n8n) reste à confirmer par Evan (`18-a-exposer.md`).
 * Aucun état d'un parent n'est modifié pendant un rendu : l'annulation passe par un écouteur clavier et un rappel.
 */
import { SelectionMode } from "@xyflow/react";
import { useEffect } from "react";

import { type Texte, useLangue } from "@/components/mark/langue/langue";

/** Boutons de la souris : 0 = gauche, 1 = molette. La molette déplace, le clic gauche sélectionne. */
export const BOUTON_MOLETTE = 1;

/** Les propriétés de React Flow qui font ces gestes ; en lecture seule (version passée), aucun rectangle ne se trace. */
export function gestesDuGraphe(lectureSeule: boolean) {
    return {
        panOnDrag: [BOUTON_MOLETTE] as number[],
        selectionOnDrag: !lectureSeule,
        selectionMode: SelectionMode.Partial,
    };
}

const T = {
    plusieurs: (n: number): Texte => ({
        en: `${n} steps selected · dragging one moves them together · Esc to cancel`,
        fr: `${n} étapes sélectionnées · glisser l'une d'elles les déplace ensemble · Échap pour annuler`,
    }),
};

function enSaisie(cible: EventTarget | null) {
    const el = cible as HTMLElement | null;
    return Boolean(el?.closest?.("input, textarea, select, [contenteditable=true], [role=dialog]"));
}

/** Le bandeau du nombre d'étapes sélectionnées (au moins deux) et l'annulation par Échap. */
export function BandeauSelection({ nombre, onAnnuler }: { nombre: number; onAnnuler: () => void }) {
    const { t } = useLangue();
    useEffect(() => {
        if (nombre === 0) return;
        const echap = (e: KeyboardEvent) => {
            if (e.key === "Escape" && !enSaisie(e.target)) onAnnuler();
        };
        window.addEventListener("keydown", echap);
        return () => window.removeEventListener("keydown", echap);
    }, [nombre, onAnnuler]);
    if (nombre < 2) return null;
    return (
        <p
            role="status"
            data-bandeau-selection
            className="absolute right-4 top-3 z-20 max-w-[60%] rounded-lg border bg-card px-3 py-1.5 text-xs text-muted-foreground shadow-sm"
        >
            {t(T.plusieurs(nombre))}
        </p>
    );
}
