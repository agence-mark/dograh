"use client";

/**
 * [.mark] U3 quater (E65) : « le canal de cet agent est-il le site ? ». Lu une fois par agent (`GET /organizations/
 * agents-site/{id}`). Sans réponse, `false` : l'onglet « Site » n'apparaît pas.
 */
import { useEffect, useState } from "react";

import { lireLEmplacementApiV1OrganizationsAgentsSiteWorkflowIdGet } from "@/client/sdk.gen";
import { useAuth } from "@/lib/auth";

export const useAgentDeSite = (agentId: number): boolean => {
    const { user, loading: authLoading } = useAuth();
    const [site, setSite] = useState(false);
    useEffect(() => {
        if (authLoading || !user || !Number.isFinite(agentId)) return;
        let annule = false;
        void (async () => {
            try {
                const reponse = await lireLEmplacementApiV1OrganizationsAgentsSiteWorkflowIdGet({ path: { workflow_id: agentId } });
                if (!annule) setSite(reponse.data?.canal === "site");
            } catch {
                if (!annule) setSite(false);
            }
        })();
        return () => {
            annule = true;
        };
    }, [agentId, authLoading, user]);
    return site;
};
