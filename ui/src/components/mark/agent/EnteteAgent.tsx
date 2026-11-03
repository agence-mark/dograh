"use client";

/**
 * [.mark] K2 : la barre du haut d'une page d'agent, une seule pour le Parcours et les autres onglets, comme la maquette :
 * le nom de l'agent, le membre du groupe, les onglets au trait, puis les actions. Posée dans la barre du cadre
 * (`EnteteStudio`), jamais une seconde barre sous elle.
 */
import type { ReactNode } from "react";

import { EnteteStudio } from "@/components/mark/studio/shell-studio";

import { MenuMembre } from "./MenuMembre";
import type { OngletAgent } from "./onglets-agent";
import { OngletsAgent } from "./OngletsAgent";

export function EnteteAgent({ agentId, onglet, nom, actions }: { agentId: number; onglet: OngletAgent; nom: string; actions: ReactNode }) {
    return (
        <EnteteStudio
            nom={
                <span className="truncate text-sm font-medium" data-nom-agent>
                    {nom}
                </span>
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
