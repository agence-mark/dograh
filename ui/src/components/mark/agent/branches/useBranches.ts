"use client";

import { useCallback, useEffect, useState } from "react";

import { lireLesBranchesApiV1BuilderBranchesWorkflowIdGet } from "@/client/sdk.gen";
import type { BranchesVue } from "@/client/types.gen";
import { useAuth } from "@/lib/auth";
import { brancheOuverte, ouvrirBranche } from "@/lib/brancheOuverte";

/**
 * [.mark] Partie 3, SA-L3b : les branches de l'agent (une lecture), et la branche ouverte dans cet onglet. Une branche retenue
 * qui n'existe plus (archivée, autre organisation) est oubliée : la principale s'ouvre.
 */
export function useBranches(agentId: number) {
    const { user, loading: authLoading } = useAuth();
    const [vue, setVue] = useState<BranchesVue | null>(null);
    const [erreur, setErreur] = useState(false);
    const [ouverte, setOuverte] = useState<number | null>(null);

    const recharger = useCallback(async () => {
        try {
            const r = await lireLesBranchesApiV1BuilderBranchesWorkflowIdGet({ path: { workflow_id: agentId } });
            if (r.error || !r.data) {
                setErreur(true);
                return;
            }
            setErreur(false);
            setVue(r.data);
            const retenue = brancheOuverte(agentId);
            const existe = retenue !== null && r.data.branches.some((b) => b.id === retenue && !b.principale);
            if (retenue !== null && !existe) ouvrirBranche(agentId, null);
            setOuverte(existe ? retenue : null);
        } catch {
            setErreur(true);
        }
    }, [agentId]);

    useEffect(() => {
        if (authLoading || !user) return;
        void recharger();
    }, [authLoading, user, recharger]);

    const courante = vue?.branches.find((b) => (ouverte === null ? b.principale : b.id === ouverte)) ?? null;
    return { vue, erreur, recharger, ouverte, courante };
}
