"use client";

/**
 * [.mark] La barre des onglets autres que le Parcours (Réglages, Tests, Appels, Versions), la même que celle du Parcours
 * (`EnteteAgent` + `ActionsAgent`, K2) : le nom, le membre du groupe, les onglets, version ⌄, Essayer ⌄, Builder IA, Publier, ⋮.
 * L'écran de l'onglet est monté dessous, tel qu'il est.
 */
import { type ReactNode, useEffect, useState } from "react";

import { getWorkflowApiV1WorkflowFetchWorkflowIdGet } from "@/client/sdk.gen";
import { type Texte, useLangue } from "@/components/mark/langue/langue";
import { LigneLive } from "@/components/mark/sources/useModifications";
import { Button } from "@/components/ui/button";
import { useAuth } from "@/lib/auth";

import { ActionsAgent } from "./ActionsAgent";
import { ContexteBrouillonLocal, useRegistreBrouillons } from "./brouillon-local";
import { EnteteAgent } from "./EnteteAgent";
import type { OngletAgent } from "./onglets-agent";

const T = {
    modifieAilleurs: {
        en: "This agent was modified elsewhere. Your unsaved input is kept.",
        fr: "Cet agent a été modifié ailleurs. Votre saisie non enregistrée est gardée.",
    },
    recharger: { en: "Reload", fr: "Recharger" },
} satisfies Record<string, Texte>;

type Fiche = { nom: string; uuid: string | null; numero: number | null; statut: string | null };

export function EntetePageAgent({ agentId, onglet, children }: { agentId: number; onglet: OngletAgent; children: ReactNode }) {
    const { user, loading: authLoading } = useAuth();
    const { t } = useLangue();
    const [fiche, setFiche] = useState<Fiche | null>(null);
    // U12 : une ecriture (Claude Code, le builder, un collegue) sur cet agent relit l'ecran seul (l'onglet est remonte),
    // SAUF si l'onglet porte une saisie non enregistree : on la garde, on previent, on recharge sur demande (K6).
    const [lecture, setLecture] = useState(0);
    const [remontage, setRemontage] = useState(0);
    const [modifieAilleurs, setModifieAilleurs] = useState(false);
    const recharger = () => {
        setModifieAilleurs(false);
        setRemontage((n) => n + 1);
    };
    const { declarer, aUneSaisie } = useRegistreBrouillons(() => {
        if (modifieAilleurs) recharger();
    });
    const surModification = () => {
        setLecture((n) => n + 1);
        if (aUneSaisie()) setModifieAilleurs(true);
        else setRemontage((n) => n + 1);
    };

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
                <LigneLive objet={`agent:${agentId}`} quand={surModification} />
            </div>
            {modifieAilleurs && (
                <div role="status" className="flex items-center gap-3 px-6 py-1 text-sm">
                    <span>{t(T.modifieAilleurs)}</span>
                    <Button size="sm" variant="outline" onClick={recharger}>
                        {t(T.recharger)}
                    </Button>
                </div>
            )}
            <ContexteBrouillonLocal.Provider value={declarer}>
                <div key={remontage} className="min-h-0 flex-1">
                    {children}
                </div>
            </ContexteBrouillonLocal.Provider>
        </div>
    );
}
