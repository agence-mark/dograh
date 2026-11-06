"use client";

/**
 * [.mark] U3 bis (E62) : le catalogue des variables de l'agent ouvert, lu une fois par page (`GET /mark/variables`).
 * L'agent est celui de l'adresse (`/agents/<id>`, `/workflow/<id>`). Sans réponse, le catalogue est vide et le champ
 * ne montre aucune étiquette en rouge : on ne dit « inconnue » que sur une réponse du serveur.
 */
import { useParams } from "next/navigation";
import { useEffect, useState } from "react";

import { lireLeCatalogueApiV1MarkVariablesGet } from "@/client/sdk.gen";
import { useAuth } from "@/lib/auth";

import type { VariableCatalogue } from "./texte-etiquettes";

export interface EtatCatalogue {
    variables: VariableCatalogue[];
    /** `false` tant que le serveur n'a pas répondu : aucune étiquette n'est alors déclarée inconnue. */
    lu: boolean;
}

export const useCatalogueVariables = (): EtatCatalogue => {
    const params = useParams<{ workflowId?: string; id?: string }>();
    const agent = Number(params?.workflowId ?? params?.id);
    const { user, loading: authLoading } = useAuth();
    const [etat, setEtat] = useState<EtatCatalogue>({ variables: [], lu: false });
    useEffect(() => {
        if (authLoading || !user) return;
        let annule = false;
        void (async () => {
            try {
                const reponse = await lireLeCatalogueApiV1MarkVariablesGet({ query: Number.isFinite(agent) && agent > 0 ? { agent } : undefined });
                if (!annule && reponse.data) setEtat({ variables: reponse.data.variables, lu: true });
            } catch {
                /* un catalogue illisible = pas d'étiquettes, le champ reste un texte */
            }
        })();
        return () => {
            annule = true;
        };
    }, [agent, authLoading, user]);
    return etat;
};
