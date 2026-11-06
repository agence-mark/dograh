"use client";

/**
 * [.mark] K2 : la barre du haut d'une page d'agent, une seule pour le Parcours et les autres onglets, comme la maquette :
 * le nom de l'agent, le membre du groupe, les onglets au trait, puis les actions. Posée dans la barre du cadre
 * (`EnteteStudio`), jamais une seconde barre sous elle.
 */
import { ArrowLeft, ChevronRight } from "lucide-react";
import Link from "next/link";
import type { ReactNode } from "react";

import { useLangue } from "@/components/mark/langue/langue";
import { useBaseEspace } from "@/components/mark/studio/base-espace";
import { EnteteStudio } from "@/components/mark/studio/shell-studio";

import { MenuMembre } from "./MenuMembre";
import type { OngletAgent } from "./onglets-agent";
import { OngletsAgent } from "./OngletsAgent";

/**
 * `fil` : le dernier maillon d'une page ouverte depuis l'agent (T6) : le nom devient un lien vers l'agent, suivi de ce maillon
 * (le fil d'Ariane ramène d'où l'on vient).
 */
export function EnteteAgent({ agentId, onglet, nom, actions, fil }: { agentId: number; onglet: OngletAgent; nom: string; actions: ReactNode; fil?: string }) {
    const { t } = useLangue();
    const base = useBaseEspace();
    const aLaListe = t({ en: "Back to the agents", fr: "Retour aux agents" });
    return (
        <EnteteStudio
            nom={
                <>
                    {/* T6 : la page d'un agent s'ouvre depuis la liste des agents de l'espace : la flèche y ramène. */}
                    <Link
                        href={`${base}/agents`}
                        data-fleche-retour
                        aria-label={aLaListe}
                        title={aLaListe}
                        className="mr-1 inline-flex size-7 shrink-0 cursor-pointer items-center justify-center rounded-md text-muted-foreground hover:bg-muted hover:text-foreground focus-visible:outline-2 focus-visible:outline-ring"
                    >
                        <ArrowLeft className="size-4" aria-hidden />
                    </Link>
                {fil ? (
                    <nav className="flex min-w-0 items-center gap-1.5 text-sm" data-nom-agent>
                        <Link href={`/agents/${agentId}`} className="truncate text-muted-foreground hover:font-medium hover:text-foreground">
                            {nom}
                        </Link>
                        <ChevronRight className="size-3.5 shrink-0 text-muted-foreground" aria-hidden />
                        <span className="truncate font-medium">{fil}</span>
                    </nav>
                ) : (
                    <span className="truncate text-sm font-medium" data-nom-agent>
                        {nom}
                    </span>
                )}
                </>
            }
            milieu={
                <>
                    <span className="mx-3 h-5 w-px shrink-0 bg-border" />
                    <MenuMembre agentId={agentId} onglet={onglet} />
                    <OngletsAgent agentId={agentId} actif={onglet} />
                </>
            }
            actions={actions}
        />
    );
}
