"use client";

/**
 * [.mark] Les pièces d'un sous-menu de module (le motif du fournisseur, `GroupesFournisseur.tsx`) : le sous-menu déroulant et les
 * lignes « se branche sur » de ses besoins. Partagées par le thème « Modules » et par le groupe d'un module d'ensemble.
 */
import { ChevronDown } from "lucide-react";
import type { ReactNode } from "react";

import type { ModuleDeLAgent } from "@/client/types.gen";
import { cn } from "@/lib/utils";

import { type Texte, useLangue } from "../langue/langue";
import type { ModuleAgent } from "./modules-agent";

export const ETAT: Record<"on" | "off", Texte> = { on: { en: "On", fr: "Allumé" }, off: { en: "Off", fr: "Coupé" } };

/** A drop-down sub-menu (the provider's pattern, `GroupesFournisseur.tsx`), opened from outside on « show ». */
export const SousMenuModule = ({
    module,
    allume,
    ouvert,
    onBasculer,
    ensemble = false,
    children,
}: {
    module: ModuleAgent;
    allume: boolean | null;
    ouvert: boolean;
    onBasculer: () => void;
    /** Une ligne d'un module d'ensemble (son groupe), pas un module de base : sa marque de test est à part. */
    ensemble?: boolean;
    children: ReactNode;
}) => {
    const { t } = useLangue();
    const idContenu = `sous-menu-module-${module.code}`;
    return (
        <div className="rounded-md border" {...{ [ensemble ? "data-ligne-module-ensemble" : "data-sous-menu-module"]: module.code }}>
            <button
                type="button"
                aria-expanded={ouvert}
                aria-controls={idContenu}
                aria-label={t(module.titre)}
                onClick={onBasculer}
                className="flex w-full items-center gap-3 px-4 py-3 text-left"
            >
                <span className="flex-1 text-sm font-medium">{t(module.titre)}</span>
                {allume !== null && (
                    <span className={cn("text-xs", allume ? "text-foreground" : "text-muted-foreground")}>
                        {t(allume ? ETAT.on : ETAT.off)}
                    </span>
                )}
                <code className="text-[11px] text-muted-foreground/80">{module.code}</code>
                <ChevronDown className={cn("h-4 w-4 text-muted-foreground transition-transform", ouvert && "rotate-180")} />
            </button>
            {ouvert && (
                <div id={idContenu} className="space-y-4 border-t px-4 py-4">
                    {children}
                </div>
            )}
        </div>
    );
};

/** « Plugs into » for each need, from the server (the organization's translator, or a source of the fork). */
export const Besoins = ({ module }: { module: ModuleDeLAgent | undefined }) => {
    const { t } = useLangue();
    const besoins = module?.besoins ?? [];
    if (!module || besoins.length === 0) return null;
    return (
        <div className="space-y-1" data-besoins-module={module.code}>
            <p className="text-xs font-medium">{t({ en: "Needs", fr: "Besoins" })}</p>
            <ul className="space-y-0.5 text-xs text-muted-foreground">
                {besoins.map((besoin) => (
                    <li key={besoin.code} data-besoin={besoin.code}>
                        {t(besoin.libelle)} · {t({ en: "plugs into", fr: "se branche sur" })} :{" "}
                        {besoin.traducteur
                            ? besoin.traducteur.libelle
                            : besoin.source_interne
                              ? t(besoin.source_interne)
                              : t({ en: "no software chosen", fr: "aucun logiciel choisi" })}
                        {besoin.domaine && <code className="ml-2 text-[11px] text-muted-foreground/80">{besoin.domaine}</code>}
                    </li>
                ))}
            </ul>
        </div>
    );
};

