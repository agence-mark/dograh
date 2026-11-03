"use client";

/**
 * [.mark] L'en-tête des onglets autres que le Parcours (Réglages, Tests, Appels, Versions) : la flèche retour, le nom de
 * l'agent, puis la ligne d'onglets (avec le menu du membre du groupe). Le Parcours a la barre complète
 * (`WorkflowEditorHeader`). L'écran de l'onglet est monté dessous, tel qu'il est.
 */
import { ArrowLeft } from "lucide-react";
import Link from "next/link";
import { type ReactNode, useEffect, useState } from "react";

import { getWorkflowApiV1WorkflowFetchWorkflowIdGet } from "@/client/sdk.gen";
import { useLangue } from "@/components/mark/langue/langue";
import { useAuth } from "@/lib/auth";
import { espaceRetenu } from "@/lib/espaceCourant";

import { adresseDesAgents } from "./liste-des-agents";
import { MenuMembre } from "./MenuMembre";
import type { OngletAgent } from "./onglets-agent";
import { OngletsAgent } from "./OngletsAgent";

export function EntetePageAgent({ agentId, onglet, children }: { agentId: number; onglet: OngletAgent; children: ReactNode }) {
    const { t } = useLangue();
    const { user, loading: authLoading } = useAuth();
    const [nom, setNom] = useState<string | null>(null);
    const [retour, setRetour] = useState("/labo/agents");

    useEffect(() => setRetour(adresseDesAgents(espaceRetenu())), []);
    useEffect(() => {
        if (authLoading || !user) return;
        let annule = false;
        (async () => {
            try {
                const reponse = await getWorkflowApiV1WorkflowFetchWorkflowIdGet({ path: { workflow_id: agentId } });
                if (!annule) setNom(reponse.data?.name ?? null);
            } catch {
                if (!annule) setNom(null);
            }
        })();
        return () => {
            annule = true;
        };
    }, [agentId, authLoading, user]);

    return (
        <div className="flex min-h-full flex-col">
            <div className="flex h-14 items-center gap-3 border-b bg-background px-4">
                <Link
                    href={retour}
                    aria-label={t({ en: "Back to the agents", fr: "Retour aux agents" })}
                    className="flex size-8 cursor-pointer items-center justify-center rounded-lg hover:bg-accent"
                >
                    <ArrowLeft className="size-5 text-muted-foreground" />
                </Link>
                <h1 className="truncate text-base font-medium" data-nom-agent>
                    {nom ?? ""}
                </h1>
            </div>
            <OngletsAgent agentId={agentId} actif={onglet} debut={<MenuMembre agentId={agentId} onglet={onglet} />} />
            <div className="min-h-0 flex-1">{children}</div>
        </div>
    );
}
