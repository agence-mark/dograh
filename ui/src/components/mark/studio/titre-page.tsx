"use client";

import { ArrowLeft } from "lucide-react";
import Link from "next/link";

import { Info } from "./marques";

export type Retour = { href: string; libelle: string };

/**
 * [.mark] T6 : la flèche retour de toute page ouverte depuis une autre, UN seul composant (Evan, 05/11). Posée devant le
 * titre (`TitrePage retour`), jamais écrite page par page. Lien interne (sans rechargement), survol en gras, jamais souligné,
 * focus visible. Dans une fenêtre imbriquée, c'est la croix du composant `Dialog` qui devient flèche (règle E71).
 */
export function FlecheRetour({ href, libelle }: Retour) {
    return (
        <Link
            href={href}
            data-fleche-retour
            className="inline-flex cursor-pointer items-center gap-1.5 rounded-sm text-sm text-muted-foreground hover:font-semibold hover:text-foreground focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-ring"
        >
            <ArrowLeft className="size-4 shrink-0" aria-hidden />
            {libelle}
        </Link>
    );
}

/** Le titre d'une page : une explication passe par `info` (le « ! »), `phrase` est réservée à une donnée. */
export function TitrePage({
    titre,
    info,
    phrase,
    action,
    retour,
}: {
    titre: string;
    /** Une page ouverte depuis une autre : la flèche retour, au-dessus du titre. */
    retour?: Retour;
    info?: React.ReactNode;
    phrase?: React.ReactNode;
    action?: React.ReactNode;
}) {
    return (
        <div className="flex flex-col gap-4 sm:flex-row sm:items-end sm:justify-between">
            <div className="space-y-1">
                {retour && <FlecheRetour {...retour} />}
                <h1 className="flex items-center gap-2 text-2xl font-semibold tracking-tight">
                    {titre}
                    {info && <Info>{info}</Info>}
                </h1>
                {phrase && <p className="text-muted-foreground">{phrase}</p>}
            </div>
            {action}
        </div>
    );
}
