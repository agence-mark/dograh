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

type Reponse<T> = { data?: T | null; error?: unknown };
interface Instantane<T> {
    valeur: T | null;
    erreur: boolean;
}

export function creerLecturePartagee<T>(lire: () => Promise<Reponse<T>>) {
    let instantane: Instantane<T> = { valeur: null, erreur: false };
    let enVol: Promise<void> | null = null;
    const abonnes = new Set<() => void>();

    const poserInstantane = (suivant: Instantane<T>) => {
        instantane = suivant;
        abonnes.forEach((rappel) => rappel());
    };
    const relire = (): Promise<void> => {
        if (!enVol) {
            enVol = lire()
                .then((reponse) => {
                    if (abonnes.size === 0) return; // plus personne : la réponse est oubliée
                    poserInstantane(reponse.data && !reponse.error ? { valeur: reponse.data, erreur: false } : { valeur: instantane.valeur, erreur: true });
                })
                .catch(() => {
                    if (abonnes.size > 0) poserInstantane({ valeur: instantane.valeur, erreur: true });
                })
                .finally(() => {
                    enVol = null;
                });
        }
        return enVol;
    };
    const poser = (valeur: T) => poserInstantane({ valeur, erreur: false });
    const abonner = (rappel: () => void) => {
        abonnes.add(rappel);
        return () => {
            abonnes.delete(rappel);
            if (abonnes.size === 0) instantane = { valeur: null, erreur: false };
        };
    };
    const lireInstantane = () => instantane;

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
