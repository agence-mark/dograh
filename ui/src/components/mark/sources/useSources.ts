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

export type Brique = "builder" | "appelant" | "juge_tests" | "juge_appels" | "analyse";
export type Source = "claude_code" | "cle_api";
export const BRIQUES: Brique[] = ["builder", "appelant", "juge_tests", "juge_appels", "analyse"];

const EVENEMENT = "mark-sources-modifiees";
const prevenir = () => window.dispatchEvent(new Event(EVENEMENT));

export function useSources() {
    const { user, loading: authLoading } = useAuth();
    const [sources, setSources] = useState<Record<string, Source> | null>(null);
    const [erreur, setErreur] = useState(false);

    const lire = useCallback(async () => {
        const r = await lireLesSourcesApiV1BuilderSourcesGet();
        if (r.error || !r.data) {
            setErreur(true);
            return;
        }
        setErreur(false);
        setSources(r.data.sources as Record<string, Source>);
    }, []);

    useEffect(() => {
        if (authLoading || !user) return;
        void lire();
        window.addEventListener(EVENEMENT, lire);
        return () => window.removeEventListener(EVENEMENT, lire);
    }, [authLoading, user, lire]);

    const regler = useCallback(async (brique: Brique, source: Source): Promise<unknown> => {
        const r = await reglerUneSourceApiV1BuilderSourcesBriquePut({ path: { brique }, body: { source } });
        if (!r.error && r.data) {
            setSources(r.data.sources as Record<string, Source>);
            prevenir();
        }
        return r.error;
    }, []);

    return { sources, erreur, regler, relire: lire };
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
