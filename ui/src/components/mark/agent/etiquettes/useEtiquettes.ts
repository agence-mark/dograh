"use client";

/**
 * [.mark] Lit les étiquettes de l'organisation (`GET /etiquettes`) une fois l'authentification prête. `recharger` relit
 * après une pose. Un échec laisse `donnees` à null : l'écran qui en dépend n'affiche alors rien (jamais une fausse liste).
 */
import { useCallback, useEffect, useState } from "react";

import { lireLesEtiquettesApiV1EtiquettesGet } from "@/client/sdk.gen";
import type { EtiquettesResponse } from "@/client/types.gen";
import { useAuth } from "@/lib/auth";

export function useEtiquettes() {
    const { user, loading } = useAuth();
    const [donnees, setDonnees] = useState<EtiquettesResponse | null>(null);

    const recharger = useCallback(async () => {
        try {
            const reponse = await lireLesEtiquettesApiV1EtiquettesGet();
            setDonnees(reponse.error ? null : (reponse.data ?? null));
        } catch {
            setDonnees(null);
        }
    }, []);

    useEffect(() => {
        if (loading || !user) return;
        void recharger();
    }, [loading, user, recharger]);

    return { donnees, recharger };
}
