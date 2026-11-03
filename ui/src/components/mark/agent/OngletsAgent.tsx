"use client";

/**
 * [.mark] La ligne d'onglets d'un agent (E37 bis, E46) : le membre du groupe au début (si l'agent est dans un groupe),
 * puis Parcours · Réglages · Tests · Appels · Versions. À droite, `droite` porte « non enregistré » et les erreurs.
 * Même forme que les onglets de la fenêtre commune : trait sous l'onglet actif, survol en gras.
 */
import Link from "next/link";
import type { ReactNode } from "react";

import { useLangue } from "@/components/mark/langue/langue";

import { useAgentDeSite } from "../site/useAgentDeSite";
import { adresseOnglet, ONGLET_SITE, type OngletAgent, ONGLETS_AGENT } from "./onglets-agent";

export function OngletsAgent({
    agentId,
    actif,
    debut,
    droite,
}: {
    agentId: number;
    actif: OngletAgent;
    debut?: ReactNode;
    droite?: ReactNode;
}) {
    const { t } = useLangue();
    // [.mark] U3 quater (E65) : l'onglet « Site » n'existe que pour un agent dont le canal est le site.
    const agentDeSite = useAgentDeSite(agentId);
    const onglets = agentDeSite ? [...ONGLETS_AGENT, ONGLET_SITE] : ONGLETS_AGENT;
    return (
        <div className="flex items-center gap-3 border-b bg-background px-4" data-ligne-onglets>
            {debut}
            <nav role="tablist" className="flex flex-1 items-center gap-1">
                {onglets.map((o) => (
                    <Link
                        key={o.id}
                        href={adresseOnglet(agentId, o.id)}
                        role="tab"
                        aria-selected={actif === o.id}
                        data-onglet={o.id}
                        className={`-mb-px cursor-pointer border-b-2 px-3 py-2.5 text-sm ${
                            actif === o.id
                                ? "border-primary font-medium"
                                : "border-transparent text-muted-foreground hover:font-medium hover:text-foreground"
                        }`}
                    >
                        {t(o.titre)}
                    </Link>
                ))}
            </nav>
            {droite && <div className="flex items-center gap-2">{droite}</div>}
        </div>
    );
}
