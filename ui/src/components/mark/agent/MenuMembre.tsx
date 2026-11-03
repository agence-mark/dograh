"use client";

/**
 * [.mark] Le membre du groupe sur lequel portent Réglages, Tests et Appels (E37 bis), repris de la maquette (K2) : « Accueil ⌄ »
 * au début des onglets, menu « Groupe » avec le principal, les spécialisés et « Ajouter un spécialiste ». Un agent seul n'a
 * pas de menu (rien n'est affiché). La liste est lue dans la route du groupe, jamais écrite en dur.
 */
import { Check, ChevronDown, Plus } from "lucide-react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { useEffect, useState } from "react";

import { creerUnSpecialiseApiV1WorkflowWorkflowIdGroupeSpecialisePost, lireUnGroupeApiV1WorkflowWorkflowIdGroupeGet } from "@/client/sdk.gen";
import { DialogueNom } from "@/components/mark/groupe/DialogueNom";
import { useLangue } from "@/components/mark/langue/langue";
import { notifier } from "@/components/mark/notifications";
import {
    DropdownMenu,
    DropdownMenuContent,
    DropdownMenuItem,
    DropdownMenuLabel,
    DropdownMenuSeparator,
    DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import { useAuth } from "@/lib/auth";

import { type MembreMenu, membresDuGroupe } from "./membres-groupe";
import { adresseOnglet, type OngletAgent } from "./onglets-agent";

export function MenuMembre({ agentId, onglet }: { agentId: number; onglet: OngletAgent }) {
    const { t } = useLangue();
    const router = useRouter();
    const { user, loading: authLoading } = useAuth();
    const [membres, setMembres] = useState<MembreMenu[]>([]);
    const [creation, setCreation] = useState(false);

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
    const principal = membres.find((m) => m.principal);
    // Le principal se lit par son nom ; le mot « principal » n'est dit que dans la liste (maquette).
    const libelle = (m: MembreMenu) => (m.principal ? `${m.nom} (${t({ en: "main", fr: "principal" })})` : m.nom);

    const ajouter = async (nom: string) => {
        if (!principal) return;
        const reponse = await creerUnSpecialiseApiV1WorkflowWorkflowIdGroupeSpecialisePost({
            path: { workflow_id: principal.id },
            body: { name: nom },
        });
        if (reponse.error || !reponse.data) {
            notifier.echec({ fr: "L'agent spécialisé n'a pas pu être créé.", en: "The specialised agent could not be created." });
            throw new Error("specialise");
        }
        notifier.succes({ fr: "Agent spécialisé créé.", en: "Specialised agent created." });
        router.push(adresseOnglet(reponse.data.workflow_id, onglet));
    };

    return (
        <>
            <DropdownMenu>
                <DropdownMenuTrigger asChild>
                    <button
                        data-menu-membre
                        className="flex shrink-0 cursor-pointer items-center gap-1.5 rounded-md px-2 py-1 text-sm font-medium hover:bg-muted"
                    >
                        {courant.nom}
                        <ChevronDown className="size-3.5 text-muted-foreground" aria-hidden />
                    </button>
                </DropdownMenuTrigger>
                <DropdownMenuContent align="start" className="w-56">
                    <DropdownMenuLabel className="text-xs text-muted-foreground">{t({ en: "Group", fr: "Groupe" })}</DropdownMenuLabel>
                    {membres.map((m) => (
                        <DropdownMenuItem key={m.id} asChild className="cursor-pointer">
                            <Link href={adresseOnglet(m.id, onglet)} data-membre={m.id}>
                                {libelle(m)}
                                {m.id === agentId && <Check className="ml-auto size-3.5" />}
                            </Link>
                        </DropdownMenuItem>
                    ))}
                    <DropdownMenuSeparator />
                    <DropdownMenuItem className="cursor-pointer" onClick={() => setCreation(true)}>
                        <Plus className="mr-2 size-4" /> {t({ en: "Add a specialist", fr: "Ajouter un spécialiste" })}
                    </DropdownMenuItem>
                </DropdownMenuContent>
            </DropdownMenu>
            <span className="mx-2 h-5 w-px shrink-0 bg-border" />
            <DialogueNom
                ouvert={creation}
                onOuvertChange={setCreation}
                titre={{ en: "New specialised agent", fr: "Nouvel agent spécialisé" }}
                libelle={{ en: "Name", fr: "Nom" }}
                valider={{ en: "Create", fr: "Créer" }}
                onValider={ajouter}
            />
        </>
    );
}
