"use client";

import { Info } from "./marques";

/** Le titre d'une page : une explication passe par `info` (le « ! »), `phrase` est réservée à une donnée. */
export function TitrePage({
    titre,
    info,
    phrase,
    action,
}: {
    titre: string;
    info?: React.ReactNode;
    phrase?: React.ReactNode;
    action?: React.ReactNode;
}) {
    return (
        <div className="flex flex-col gap-4 sm:flex-row sm:items-end sm:justify-between">
            <div className="space-y-1">
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
