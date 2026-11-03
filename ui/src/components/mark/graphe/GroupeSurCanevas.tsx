"use client";

/**
 * [.mark] K2 : le dessin du groupe sur le canevas, repris de la maquette (`canevas.tsx`). Sur l'agent principal, ses
 * spécialisés sont des cartes à droite de l'étape qui les appelle, reliées par des courbes en pointillés ; un clic ouvre le
 * spécialisé. Sur un spécialisé, un fil « Groupe › Nom » ramène au principal. Tout vient de la route du groupe : aucun nom
 * ni compte n'est écrit ici. Les cartes sont posées dans le repère du canevas (elles suivent le zoom), jamais enregistrées.
 */
import { useNodes, ViewportPortal } from "@xyflow/react";
import { ChevronRight, Workflow } from "lucide-react";
import Link from "next/link";
import { useEffect, useMemo, useState } from "react";

import { getWorkflowApiV1WorkflowFetchWorkflowIdGet, lireUnGroupeApiV1WorkflowWorkflowIdGroupeGet } from "@/client/sdk.gen";
import type { GroupeResponse } from "@/client/types.gen";
import { useLangue } from "@/components/mark/langue/langue";
import { useAuth } from "@/lib/auth";

import { adresseOnglet } from "../agent/onglets-agent";

const LARGEUR = 250;
const X_CARTE = LARGEUR + 95;
const ECART = 150;
const Y_PREMIERE = -70;

type Carte = { id: number; nom: string; etapes: number | null };

/** Le groupe de l'agent, et le nombre d'étapes de chaque spécialisé (lu dans sa définition). */
export function useGroupe(agentId: number) {
    const { user, loading: authLoading } = useAuth();
    const [groupe, setGroupe] = useState<GroupeResponse | null>(null);
    const [etapes, setEtapes] = useState<Record<number, number>>({});

    useEffect(() => {
        if (authLoading || !user) return;
        let annule = false;
        (async () => {
            try {
                const reponse = await lireUnGroupeApiV1WorkflowWorkflowIdGroupeGet({ path: { workflow_id: agentId } });
                if (annule) return;
                setGroupe(reponse.data ?? null);
                await Promise.all(
                    (reponse.data?.specialises ?? []).map(async (m) => {
                        const fiche = await getWorkflowApiV1WorkflowFetchWorkflowIdGet({ path: { workflow_id: m.id } });
                        const noeuds = (fiche.data?.workflow_definition as { nodes?: Array<{ type?: string }> } | undefined)?.nodes ?? [];
                        if (!annule) setEtapes((e) => ({ ...e, [m.id]: noeuds.filter((n) => n.type !== "globalNode").length }));
                    }),
                );
            } catch {
                if (!annule) setGroupe(null);
            }
        })();
        return () => {
            annule = true;
        };
    }, [agentId, authLoading, user]);

    return { groupe, etapes };
}

/** À poser DANS le canevas : les cartes des spécialisés à droite de l'étape qui les appelle, et leurs courbes. */
export function GroupeSurCanevas({ agentId }: { agentId: number }) {
    const { t } = useLangue();
    const { groupe, etapes } = useGroupe(agentId);
    const noeuds = useNodes();
    const cartes: Carte[] = useMemo(
        () => (groupe?.principal?.id === agentId ? (groupe.specialises ?? []).map((m) => ({ id: m.id, nom: m.name, etapes: etapes[m.id] ?? null })) : []),
        [groupe, agentId, etapes],
    );
    // L'étape qui appelle les spécialisés : la première qui porte des outils (les passations), sinon le début.
    const ancre = useMemo(() => {
        const avecOutils = noeuds.find((n) => Array.isArray((n.data as { tool_uuids?: string[] }).tool_uuids) && ((n.data as { tool_uuids?: string[] }).tool_uuids?.length ?? 0) > 0);
        return avecOutils ?? noeuds.find((n) => n.type === "startCall") ?? noeuds[0];
    }, [noeuds]);

    if (cartes.length === 0 || !ancre) return null;
    const x1 = ancre.position.x + LARGEUR;
    const y1 = ancre.position.y + 40;
    const xCarte = ancre.position.x + X_CARTE;
    return (
        <ViewportPortal>
            <svg className="pointer-events-none absolute overflow-visible" style={{ left: 0, top: 0 }} width="1" height="1">
                {cartes.map((c, i) => {
                    const y2 = ancre.position.y + Y_PREMIERE + i * ECART + 30;
                    return (
                        <path
                            key={c.id}
                            d={`M${x1} ${y1} C ${x1 + 50} ${y1}, ${xCarte - 50} ${y2}, ${xCarte} ${y2}`}
                            stroke="var(--liaison)"
                            strokeWidth="1.5"
                            strokeDasharray="4 4"
                            fill="none"
                        />
                    );
                })}
            </svg>
            {cartes.map((c, i) => (
                <Link
                    key={c.id}
                    href={adresseOnglet(c.id, "parcours")}
                    data-specialise={c.id}
                    style={{ position: "absolute", left: xCarte, top: ancre.position.y + Y_PREMIERE + i * ECART }}
                    className="nodrag nopan w-52 cursor-pointer rounded-xl border border-black/10 bg-card px-3.5 py-3 text-left shadow-xs hover:border-black/25"
                >
                    <p className="flex items-center gap-1.5 text-[10px] font-medium uppercase tracking-wider text-muted-foreground">
                        <Workflow className="size-3" />
                        {t({ en: "Specialist", fr: "Spécialiste" })}
                    </p>
                    <p className="mt-0.5 text-sm font-medium">{c.nom}</p>
                    <p className="text-xs text-muted-foreground">
                        {c.etapes !== null && `${c.etapes} ${c.etapes > 1 ? t({ en: "steps", fr: "étapes" }) : t({ en: "step", fr: "étape" })} · `}
                        {t({ en: "open", fr: "ouvrir" })}
                    </p>
                </Link>
            ))}
        </ViewportPortal>
    );
}

/** Sur un spécialisé : « Groupe › Nom », en haut à gauche du canevas ; « Groupe » ramène au principal. */
export function FilGroupe({ agentId }: { agentId: number }) {
    const { t } = useLangue();
    const { groupe } = useGroupe(agentId);
    const principal = groupe?.principal;
    const courant = groupe?.specialises?.find((m) => m.id === agentId);
    if (!principal || principal.id === agentId || !courant) return null;
    return (
        <div className="absolute left-4 top-4 z-10 flex items-center gap-1 rounded-lg border bg-background px-2 py-1 text-sm shadow-sm" data-fil-groupe>
            <Link href={adresseOnglet(principal.id, "parcours")} className="cursor-pointer text-muted-foreground hover:text-foreground">
                {t({ en: "Group", fr: "Groupe" })}
            </Link>
            <ChevronRight className="size-3.5 text-muted-foreground" />
            <span className="font-medium">{courant.name}</span>
        </div>
    );
}
