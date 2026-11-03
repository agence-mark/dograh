"use client";

/**
 * [.mark] K6 (gestes sûrs) : un onglet d'agent qui porte une saisie non enregistrée le dit ici. Quand l'agent est modifié
 * ailleurs (Claude Code, le builder, un collègue), l'écran ne se relit plus par-dessus la saisie : il la garde, prévient, et
 * ne recharge que sur demande (ou une fois la saisie enregistrée).
 */
import { createContext, useCallback, useContext, useEffect, useId, useRef } from "react";

type Declarer = (id: string, nonEnregistre: boolean) => void;

export const ContexteBrouillonLocal = createContext<Declarer>(() => {});

/** À appeler par tout écran d'onglet qui garde une saisie locale ; se retire seul au démontage. */
export function useBrouillonLocal(nonEnregistre: boolean) {
    const declarer = useContext(ContexteBrouillonLocal);
    const id = useId();
    useEffect(() => {
        declarer(id, nonEnregistre);
    }, [declarer, id, nonEnregistre]);
    useEffect(() => () => declarer(id, false), [declarer, id]);
}

/** Le registre des saisies non enregistrées d'une page d'agent ; `vide` est appelé quand la dernière est enregistrée. */
export function useRegistreBrouillons(vide: () => void) {
    const sales = useRef(new Set<string>());
    const rappel = useRef(vide);
    rappel.current = vide;
    const declarer = useCallback<Declarer>((id, nonEnregistre) => {
        const avant = sales.current.size;
        if (nonEnregistre) sales.current.add(id);
        else sales.current.delete(id);
        if (avant > 0 && sales.current.size === 0) rappel.current();
    }, []);
    return { declarer, aUneSaisie: () => sales.current.size > 0 };
}
