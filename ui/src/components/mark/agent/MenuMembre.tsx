"use client";

/**
 * [.mark] Le membre du groupe sur lequel portent Réglages, Tests et Appels (E37 bis, proposition A) : un menu au début
 * de la ligne d'onglets, « Accueil (principal) ▾ ». Le canevas dessine le groupe ; ce menu suit le canevas. Un agent
 * seul n'a pas de menu (rien n'est affiché). La liste est lue dans la route du groupe, jamais écrite en dur.
 */
import { ChevronDown } from "lucide-react";
import Link from "next/link";
import { useEffect, useState } from "react";

import { lireUnGroupeApiV1WorkflowWorkflowIdGroupeGet } from "@/client/sdk.gen";
import { useLangue } from "@/components/mark/langue/langue";
import { Button } from "@/components/ui/button";
import { DropdownMenu, DropdownMenuContent, DropdownMenuItem, DropdownMenuTrigger } from "@/components/ui/dropdown-menu";
import { useAuth } from "@/lib/auth";

import { type MembreMenu, membresDuGroupe } from "./membres-groupe";
import { adresseOnglet, type OngletAgent } from "./onglets-agent";

export function MenuMembre({ agentId, onglet }: { agentId: number; onglet: OngletAgent }) {
    const { t } = useLangue();
    const { user, loading: authLoading } = useAuth();
    const [membres, setMembres] = useState<MembreMenu[]>([]);

    useEffect(() => {
        if (authLoading || !user) return;
        let annule = false;
        (async () => {
            try {
                const reponse = await lireUnGroupeApiV1WorkflowWorkflowIdGroupeGet({ path: { workflow_id: agentId } });
                if (!annule) setMembres(membresDuGroupe(reponse.data));
            } catch {
                if (!annule) setMembres([]);
            }
        })();
        return () => {
            annule = true;
        };
    }, [agentId, authLoading, user]);

    const courant = membres.find((m) => m.id === agentId);
    if (!courant) return null;
    const libelle = (m: MembreMenu) => (m.principal ? `${m.nom} (${t({ en: "main", fr: "principal" })})` : m.nom);

    return (
        <DropdownMenu>
            <DropdownMenuTrigger asChild>
                <Button variant="ghost" size="sm" className="cursor-pointer gap-1 hover:font-medium" data-menu-membre>
                    {libelle(courant)}
                    <ChevronDown className="size-3.5" aria-hidden />
                </Button>
            </DropdownMenuTrigger>
            <DropdownMenuContent align="start">
                {membres.map((m) => (
                    <DropdownMenuItem key={m.id} asChild className="cursor-pointer hover:font-medium">
                        <Link href={adresseOnglet(m.id, onglet)} data-membre={m.id}>
                            {libelle(m)}
                        </Link>
                    </DropdownMenuItem>
                ))}
            </DropdownMenuContent>
        </DropdownMenu>
    );
}
