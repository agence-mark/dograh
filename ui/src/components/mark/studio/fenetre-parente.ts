"use client";

import { createContext, useContext } from "react";

/**
 * E71 : une fenêtre ouverte depuis une autre fenêtre prend exactement sa taille et son style, et remplace la croix
 * par une flèche retour qui ramène à la première. Réglé UNE fois, dans `components/ui/dialog.tsx` : toute fenêtre
 * pose sa taille ici, toute fenêtre ouverte depuis elle la lit.
 */
export const FenetreParente = createContext<{ classe: string } | null>(null);
export const useFenetreParente = () => useContext(FenetreParente);

/** La taille (largeur, hauteur) lue dans les classes d'une fenêtre, transmise à celles qu'elle ouvre. */
const TAILLE = /^(sm:|md:|lg:)?(w|max-w|h|max-h|min-h)-/;
export const tailleDe = (classes?: string) =>
    (classes ?? "")
        .split(/\s+/)
        .filter((c) => TAILLE.test(c))
        .join(" ");

/** Les classes d'une fenêtre sans sa taille : dans le panneau, la taille est celle du panneau. */
export const sansTaille = (classes?: string) =>
    (classes ?? "")
        .split(/\s+/)
        .filter((c) => c && !TAILLE.test(c))
        .join(" ");
