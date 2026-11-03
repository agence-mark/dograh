"use client";

/**
 * [.mark] K5 (E77) : les propositions de branchement de CETTE organisation (celles qu'on a faites à un client, et qui
 * attendent son autorisation). Une seule lecture par page ; le serveur n'en montre jamais d'une autre organisation.
 */
import { useCallback, useEffect, useRef, useState } from "react";

import { getPropositionsApiV1ConnecteursPropositionsGet } from "@/client/sdk.gen";
import type { PropositionConnecteur } from "@/client/types.gen";
import { useAuth } from "@/lib/auth";

export const usePropositions = () => {
    const { user, loading } = useAuth();
    const [liste, setListe] = useState<PropositionConnecteur[] | null>(null);
    const dejaLu = useRef(false);

    const relire = useCallback(async () => {
        try {
            const r = await getPropositionsApiV1ConnecteursPropositionsGet();
            setListe(!r.error && Array.isArray(r.data) ? r.data : []);
        } catch {
            setListe([]);
        }
    }, []);

    useEffect(() => {
        if (loading || !user || dejaLu.current) return;
        dejaLu.current = true;
        void relire();
    }, [loading, user, relire]);

    return { liste, relire };
};

export type Propositions = ReturnType<typeof usePropositions>;
