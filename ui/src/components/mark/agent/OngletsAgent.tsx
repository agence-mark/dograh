"use client";

/**
 * [.mark] La ligne d'onglets d'un agent (E37 bis, E46), reprise de la maquette (K2) : posée dans la barre du haut, trait
 * sous l'onglet actif, survol sans changer le poids. Parcours · Réglages · Tests · Appels · Versions (+ Site). SA-V : la ligne passe par `Defileur` (flèches dès que ça déborde).
 */
import Link from "next/link";
import { useEffect, useState } from "react";

import { lireLesTestsApiV1BuilderTestsWorkflowIdGet } from "@/client";

import { useLangue } from "@/components/mark/langue/langue";
import { Defileur } from "@/components/mark/studio/defileur";

import { useAgentDeSite } from "../site/useAgentDeSite";
import { adresseOnglet, ONGLET_SITE, type OngletAgent, ONGLETS_AGENT } from "./onglets-agent";

/** Clôture D1 (É20, maquette « Tests 1 ») : le nombre de tests de l'agent, lu du serveur ; rien tant qu'il n'est pas lu ou qu'il vaut zéro. */
export function useNombreDeTests(agentId: number): number | null {
    const [nombre, setNombre] = useState<number | null>(null);
    useEffect(() => {
        let annule = false;
        void (async () => {
            const r = await lireLesTestsApiV1BuilderTestsWorkflowIdGet({ path: { workflow_id: agentId } });
            const tests = (r.data as { tests?: unknown[] } | undefined)?.tests;
            if (!annule && !r.error && Array.isArray(tests)) setNombre(tests.length);
        })();
        return () => {
            annule = true;
        };
    }, [agentId]);
    return nombre;
}

export function OngletsAgent({ agentId, actif }: { agentId: number; actif: OngletAgent }) {
    const { t } = useLangue();
    // [.mark] U3 quater (E65) : l'onglet « Site » n'existe que pour un agent dont le canal est le site.
    const agentDeSite = useAgentDeSite(agentId);
    const nombreDeTests = useNombreDeTests(agentId);
    const onglets = agentDeSite ? [...ONGLETS_AGENT, ONGLET_SITE] : ONGLETS_AGENT;
    return (
        <Defileur className="h-full" interieur="h-full">
        <nav role="tablist" data-ligne-onglets className="flex h-full items-center gap-1 whitespace-nowrap">
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
                    {o.id === "tests" && nombreDeTests ? (
                        <span className="ml-1.5 text-xs tabular-nums text-muted-foreground" data-compteur-onglet="tests">
                            {nombreDeTests}
                        </span>
                    ) : null}
                </Link>
            ))}
        </nav>
        </Defileur>
    );
}
