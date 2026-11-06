"use client";

/**
 * [.mark] U12 (E104) : la source de chaque cerveau, lue et réglée par le serveur (une ligne par brique, Claude Code au départ).
 * Un seul réglage par brique : l'onglet « Sources », l'accueil du builder et la fenêtre d'un chat lisent la même ligne.
 */
import { useCallback, useEffect, useState } from "react";

import {
    lireLeMiroirApiV1BuilderMiroirReglageGet,
    lireLesSourcesApiV1BuilderSourcesGet,
    reglerLeMiroirApiV1BuilderMiroirReglagePut,
    reglerUneSourceApiV1BuilderSourcesBriquePut,
} from "@/client";
import { useAuth } from "@/lib/auth";
import { creerLecturePartagee } from "@/lib/lecture-partagee";

export type Brique = "builder" | "appelant" | "juge_tests" | "juge_appels" | "analyse";
export type Source = "claude_code" | "cle_api";
export const BRIQUES: Brique[] = ["builder", "appelant", "juge_tests", "juge_appels", "analyse"];

/** [.mark] C4 : UNE lecture des sources par page (l'onglet « Sources » et les rappels « Source actuelle » des autres onglets). */
const lectureSources = creerLecturePartagee(() => lireLesSourcesApiV1BuilderSourcesGet());

export function useSources() {
    const { user, loading: authLoading } = useAuth();
    const { valeur, erreur, relire, poser } = lectureSources.useLecture(!authLoading && Boolean(user));
    const sources = valeur ? (valeur.sources as Record<string, Source>) : null;

    const regler = useCallback(async (brique: Brique, source: Source): Promise<unknown> => {
        const r = await reglerUneSourceApiV1BuilderSourcesBriquePut({ path: { brique }, body: { source } });
        if (!r.error && r.data) poser(r.data);
        return r.error;
    }, [poser]);

    return { sources, erreur, regler, relire };
}

/** L'interrupteur du miroir de la personne (éteint par défaut). */
export function useMiroir() {
    const { user, loading: authLoading } = useAuth();
    const [actif, setActif] = useState<boolean | null>(null);

    useEffect(() => {
        if (authLoading || !user) return;
        void lireLeMiroirApiV1BuilderMiroirReglageGet().then((r) => setActif(r.data ? r.data.actif : null));
    }, [authLoading, user]);

    const regler = useCallback(async (valeur: boolean): Promise<unknown> => {
        const r = await reglerLeMiroirApiV1BuilderMiroirReglagePut({ body: { actif: valeur } });
        if (!r.error && r.data) setActif(r.data.actif);
        return r.error;
    }, []);

    return { actif, regler };
}
