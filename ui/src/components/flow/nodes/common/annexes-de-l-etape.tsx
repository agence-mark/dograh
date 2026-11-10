"use client";

import { createContext, useContext, useEffect, useRef } from "react";

/**
 * Clôture D1 (coordinateur, 09/11) : un seul « Enregistrer » par fenêtre d'étape. Un bloc de la fenêtre qui porte un réglage de
 * l'AGENT (« Couper l'agent à l'accueil ») s'inscrit ici : le pied de la fenêtre l'enregistre avec l'étape, et « Annuler » ou quitter
 * prévient pour les deux.
 */
export type AnnexeDeLEtape = {
    modifie: boolean;
    /** Une valeur refusée : le pied ne laisse pas enregistrer. */
    invalide: boolean;
    /** Enregistre le bloc (avec sa notification) ; `false` : l'étape n'est pas enregistrée non plus. */
    enregistrer: () => Promise<boolean>;
};

export type RegistreDesAnnexes = (id: string, annexe: AnnexeDeLEtape | null) => void;

export const ContexteAnnexes = createContext<RegistreDesAnnexes | null>(null);

/** Inscrit le bloc au pied de la fenêtre ; sans fenêtre (un test, un composant seul), rien ne se passe. */
export function useAnnexeDeLEtape(id: string, annexe: AnnexeDeLEtape) {
    const inscrire = useContext(ContexteAnnexes);
    const derniere = useRef(annexe);
    derniere.current = annexe;
    useEffect(() => {
        inscrire?.(id, { modifie: annexe.modifie, invalide: annexe.invalide, enregistrer: () => derniere.current.enregistrer() });
    }, [inscrire, id, annexe.modifie, annexe.invalide]);
    useEffect(() => () => inscrire?.(id, null), [inscrire, id]);
}
