"use client";

/**
 * [.mark] La barre des onglets autres que le Parcours (Réglages, Tests, Appels, Versions), la même que celle du Parcours
 * (`EnteteAgent` + `ActionsAgent`, K2) : le nom, le membre du groupe, les onglets, version ⌄, Essayer ⌄, Builder IA, Publier, ⋮.
 * L'écran de l'onglet est monté dessous, tel qu'il est.
 */
import { type ReactNode, useEffect, useState } from "react";

import { getWorkflowApiV1WorkflowFetchWorkflowIdGet } from "@/client/sdk.gen";
import { LigneLive } from "@/components/mark/sources/useModifications";
import { useAuth } from "@/lib/auth";

import { ActionsAgent } from "./ActionsAgent";
import { EnteteAgent } from "./EnteteAgent";
import type { OngletAgent } from "./onglets-agent";

type Fiche = { nom: string; uuid: string | null; numero: number | null; statut: string | null };

export function EntetePageAgent({ agentId, onglet, children }: { agentId: number; onglet: OngletAgent; children: ReactNode }) {
    const { user, loading: authLoading } = useAuth();
    const [fiche, setFiche] = useState<Fiche | null>(null);
    // U12 : une ecriture (Claude Code, le builder, un collegue) sur cet agent relit l'ecran seul (l'onglet est remonte).
    const [lecture, setLecture] = useState(0);

    useEffect(() => {
        if (authLoading || !user) return;
        let annule = false;
        (async () => {
            try {
                const reponse = await getWorkflowApiV1WorkflowFetchWorkflowIdGet({ path: { workflow_id: agentId } });
                const d = reponse.data;
                if (!annule && d) setFiche({ nom: d.name, uuid: d.workflow_uuid ?? null, numero: d.version_number ?? null, statut: d.version_status ?? null });
            } catch {
                if (!annule) setFiche(null);
            }
        })();
        return () => {
            annule = true;
        };
    }, [agentId, authLoading, user, lecture]);

    return (
        <div className="flex min-h-full flex-col">
            <EnteteAgent
                agentId={agentId}
                onglet={onglet}
                nom={fiche?.nom ?? ""}
                actions={
                    <ActionsAgent
                        agentId={agentId}
                        nom={fiche?.nom ?? ""}
                        workflowUuid={fiche?.uuid}
                        versionNumero={fiche?.numero ?? null}
                        versionStatut={fiche?.statut ?? null}
                        aUnBrouillon={fiche?.statut === "draft"}
                    />
                }
            />
            <div className="px-6 empty:hidden">
                <LigneLive objet={`agent:${agentId}`} quand={() => setLecture((n) => n + 1)} />
            </div>
            <div key={lecture} className="min-h-0 flex-1">
                {children}
            </div>
        </div>
    );
}
