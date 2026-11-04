"use client";

/**
 * [.mark] C4 : une lecture partagée par tous les composants d'une page.
 *
 * Plusieurs composants d'une même page lisaient la même donnée à des instants différents (les Réglages du Labo relisaient
 * `sources`, `cerveaux` et `options` à chaque onglet) : le partage des lectures en vol (`fetch-partage.ts`) ne les attrape pas.
 * Ici la valeur est lue UNE fois pour tous les composants montés, mise à jour par les écritures (`poser`) ou sur demande
 * (`relire`). Rien n'est gardé d'une page à l'autre : quand le dernier composant se démonte, la valeur est oubliée (jamais de
 * donnée périmée à l'ouverture suivante). Une erreur ne relance pas toute seule la lecture (pas de boucle) : `relire`.
 */
import { useEffect, useSyncExternalStore } from "react";

import { espaceDeAdresse, espaceRetenu } from "@/lib/espaceCourant";

type Reponse<T> = { data?: T | null; error?: unknown };
interface Instantane<T> {
    valeur: T | null;
    erreur: boolean;
    /** R3 : l'espace (Labo ou client) pour lequel la valeur a été lue ; une valeur d'un autre espace n'est jamais rendue. */
    espace?: string;
}

/** L'espace de l'onglet à cet instant (adresse, sinon mémoire de l'onglet). */
const espaceActuel = (): string => {
    if (typeof window === "undefined") return "";
    return String(espaceDeAdresse(window.location.pathname) ?? espaceRetenu() ?? "");
};

export function creerLecturePartagee<T>(lire: () => Promise<Reponse<T>>) {
    const VIDE: Instantane<T> = { valeur: null, erreur: false };
    let instantane: Instantane<T> = VIDE;
    let enVol: Promise<void> | null = null;
    const abonnes = new Set<() => void>();

    const poserInstantane = (suivant: Instantane<T>) => {
        instantane = suivant;
        abonnes.forEach((rappel) => rappel());
    };
    const relire = (): Promise<void> => {
        if (!enVol) {
            const espace = espaceActuel();
            let changeEnRoute = false;
            enVol = lire()
                .then((reponse) => {
                    if (abonnes.size === 0) return; // plus personne : la réponse est oubliée
                    if (espace !== espaceActuel()) {
                        changeEnRoute = true; // l'onglet a changé d'espace pendant la lecture : cette réponse n'est pas pour lui
                        return;
                    }
                    poserInstantane(reponse.data && !reponse.error ? { valeur: reponse.data, erreur: false, espace } : { valeur: instantane.valeur, erreur: true, espace });
                })
                .catch(() => {
                    if (abonnes.size > 0 && espace === espaceActuel()) poserInstantane({ valeur: instantane.valeur, erreur: true, espace });
                    else changeEnRoute = abonnes.size > 0;
                })
                .finally(() => {
                    enVol = null;
                    if (changeEnRoute && abonnes.size > 0) {
                        poserInstantane(VIDE);
                        void relire();
                    }
                });
        }
        return enVol;
    };
    const poser = (valeur: T) => poserInstantane({ valeur, erreur: false, espace: espaceActuel() });
    const abonner = (rappel: () => void) => {
        abonnes.add(rappel);
        return () => {
            abonnes.delete(rappel);
            if (abonnes.size === 0) instantane = VIDE;
        };
    };
    // Une valeur lue pour un autre espace que celui de l'onglet n'est jamais rendue.
    const lireInstantane = () => (instantane.espace !== undefined && instantane.espace !== espaceActuel() ? VIDE : instantane);

    /** `actif` : la lecture part quand il devient vrai (authentification prête). */
    function useLecture(actif = true) {
        const { valeur, erreur } = useSyncExternalStore(abonner, lireInstantane, lireInstantane);
        useEffect(() => {
            if (actif && valeur === null && !erreur && !enVol) void relire();
        }, [actif, valeur, erreur]);
        return { valeur, erreur, relire, poser };
    }

    return { useLecture, relire, poser };
}
