"use client";

/**
 * [.mark] U3 sexies : les outils de l'organisation et leurs statistiques (30 jours, calculées à la volée par le serveur).
 * L'organisation est celle du compte (jamais envoyée d'ici).
 */
import { useCallback, useEffect, useRef, useState } from "react";

import { listToolsApiV1ToolsGet, statistiquesDesOutilsApiV1ToolsStatistiquesGet } from "@/client/sdk.gen";
import type { ResumeOutil, ToolResponse } from "@/client/types.gen";
import { detailFromError } from "@/lib/apiError";
import { useAuth } from "@/lib/auth";

export function useOutils() {
    const { user, loading: authLoading } = useAuth();
    const [outils, setOutils] = useState<ToolResponse[] | null>(null);
    const [stats, setStats] = useState<Record<string, ResumeOutil>>({});
    const [erreur, setErreur] = useState<string | null>(null);
    const dejaLu = useRef(false);

    const relire = useCallback(async () => {
        const [liste, resume] = await Promise.all([
            listToolsApiV1ToolsGet({ query: { status: "active,draft,archived" } }),
            statistiquesDesOutilsApiV1ToolsStatistiquesGet(),
        ]);
        if (liste.error || !liste.data) {
            setErreur(detailFromError(liste.error, "Tools unreadable"));
            return;
        }
        setErreur(null);
        setOutils(liste.data);
        // Des statistiques illisibles ne cachent pas les outils : la colonne reste vide.
        setStats(resume.data ?? {});
    }, []);

    useEffect(() => {
        if (authLoading || !user || dejaLu.current) return;
        dejaLu.current = true;
        void relire();
    }, [authLoading, user, relire]);

    return { outils, stats, erreur, relire };
}

export type Outils = ReturnType<typeof useOutils>;
