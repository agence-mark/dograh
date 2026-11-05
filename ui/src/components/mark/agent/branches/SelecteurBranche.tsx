"use client";

import { Check, GitBranch, Plus } from "lucide-react";

import type { BranchesVue } from "@/client/types.gen";
import { useLangue } from "@/components/mark/langue/langue";
import { Info } from "@/components/mark/studio/marques";
import { DropdownMenu, DropdownMenuContent, DropdownMenuItem, DropdownMenuLabel, DropdownMenuSeparator, DropdownMenuTrigger } from "@/components/ui/dropdown-menu";

/**
 * [.mark] Partie 3, SA-L3b (05 § 18, maquette `selecteur-branche.tsx`) : le sélecteur de branche de la barre de l'agent, en icône
 * seule avec son point AVANT l'icône (T5, Evan 05/11 ; vert : la branche reçoit des appels ; creux : aucune part). Collé au bouton de la version
 * (`●⑂ · v12 ▾`), sans bordure.
 */
export function SelecteurBranche({
    vue,
    ouverte,
    choisir,
    nouvelle,
}: {
    vue: BranchesVue | null;
    /** La branche ouverte (`null` : la principale). */
    ouverte: number | null;
    choisir: (brancheId: number | null) => void;
    nouvelle: () => void;
}) {
    const { t } = useLangue();
    const branches = vue?.branches ?? [];
    const courante = branches.find((b) => (ouverte === null ? b.principale : b.id === ouverte)) ?? branches[0];
    const libelle = (b: { nom: string; part: number }) =>
        b.part > 0 ? `${b.nom} · ${t({ en: "Live", fr: "En ligne" })} ${b.part} %` : `${b.nom} · ${t({ en: "Draft", fr: "Brouillon" })}`;
    return (
        <DropdownMenu>
            <DropdownMenuTrigger asChild>
                <button
                    type="button"
                    data-menu-branche
                    disabled={!courante}
                    aria-label={`${t({ en: "Branch", fr: "Branche" })} : ${courante ? libelle(courante) : "…"}`}
                    title={courante ? libelle(courante) : undefined}
                    className="inline-flex h-8 shrink-0 cursor-pointer items-center gap-1.5 rounded-md px-2 hover:bg-muted"
                >
                    <span
                        data-point-branche={courante && courante.part > 0 ? "plein" : "creux"}
                        className={`size-2 shrink-0 rounded-full ${courante && courante.part > 0 ? "bg-(--etat-fait)" : "border-[1.5px] border-muted-foreground"}`}
                    />
                    <GitBranch className="size-4 text-muted-foreground" />
                </button>
            </DropdownMenuTrigger>
            <DropdownMenuContent align="start" className="w-72">
                <DropdownMenuLabel className="flex items-center gap-1.5 text-xs font-normal text-muted-foreground">
                    {t({ en: "Branches", fr: "Branches" })}
                    {courante ? ` · ${libelle(courante)}` : ""}
                    <Info>
                        {t({
                            en: "A branch is a working copy of the agent. The settings of the whole agent (name, rights, alerts, judge) only change on the main branch.",
                            fr: "Une branche est une copie de travail de l'agent. Les réglages de l'agent entier (nom, droits, alertes, juge) ne changent que sur la principale.",
                        })}
                    </Info>
                </DropdownMenuLabel>
                {branches.map((b) => (
                    <DropdownMenuItem key={b.id} onSelect={() => choisir(b.principale ? null : b.id)} className="cursor-pointer gap-2">
                        <span className={`size-2 shrink-0 rounded-full ${b.part > 0 ? "bg-(--etat-fait)" : "border-[1.5px] border-muted-foreground"}`} />
                        <span className="flex-1 truncate">{b.nom}</span>
                        <span className="text-xs text-muted-foreground">{b.part > 0 ? `${b.part} %` : t({ en: "draft", fr: "brouillon" })}</span>
                        {b.id === courante?.id && <Check className="size-4" />}
                    </DropdownMenuItem>
                ))}
                <DropdownMenuSeparator />
                <DropdownMenuItem onSelect={nouvelle} className="cursor-pointer gap-2">
                    <Plus className="size-4" /> {t({ en: "New branch", fr: "Nouvelle branche" })}
                </DropdownMenuItem>
            </DropdownMenuContent>
        </DropdownMenu>
    );
}
