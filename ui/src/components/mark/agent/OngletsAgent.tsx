"use client";

/**
 * [.mark] La ligne d'onglets d'un agent (E37 bis, E46), reprise de la maquette (K2) : posée dans la barre du haut, trait
 * sous l'onglet actif, survol sans changer le poids. Parcours · Réglages · Tests · Appels · Versions (+ Site).
 */
import Link from "next/link";

import { useLangue } from "@/components/mark/langue/langue";

import { useAgentDeSite } from "../site/useAgentDeSite";
import { adresseOnglet, ONGLET_SITE, type OngletAgent, ONGLETS_AGENT } from "./onglets-agent";

export function OngletsAgent({ agentId, actif }: { agentId: number; actif: OngletAgent }) {
    const { t } = useLangue();
    // [.mark] U3 quater (E65) : l'onglet « Site » n'existe que pour un agent dont le canal est le site.
    const agentDeSite = useAgentDeSite(agentId);
    const onglets = agentDeSite ? [...ONGLETS_AGENT, ONGLET_SITE] : ONGLETS_AGENT;
    return (
        <nav role="tablist" data-ligne-onglets className="flex h-full items-center gap-1 overflow-x-auto whitespace-nowrap">
            {onglets.map((o) => (
                <Link
                    key={o.id}
                    href={adresseOnglet(agentId, o.id)}
                    // L : un onglet est une page entière ; préchargée en entier, elle s'ouvre sans attendre son code.
                    prefetch
                    role="tab"
                    aria-selected={actif === o.id}
                    data-onglet={o.id}
                    className={`flex h-full cursor-pointer items-center border-b-2 px-2.5 text-sm ${
                        actif === o.id ? "border-primary font-medium" : "border-transparent text-muted-foreground hover:text-foreground"
                    }`}
                >
                    {t(o.titre)}
                </Link>
            ))}
        </nav>
    );
}
