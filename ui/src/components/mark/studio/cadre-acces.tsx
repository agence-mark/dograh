"use client";

/**
 * [.mark] Le cadre des pages d'accès (U2 ter) : connexion, « Rejoindre l'équipe .mark ». Une colonne centrée, le logo,
 * les jetons du design system ; pas de carte dans une carte, pas de panneau de promotion.
 */
import type { ReactNode } from "react";

import { useLangue } from "@/components/mark/langue/langue";

export function CadreAcces({ titre, sousTitre, children }: { titre: string; sousTitre?: string; children: ReactNode }) {
    const { t } = useLangue();
    return (
        <main className="flex min-h-screen w-full items-center justify-center bg-background p-6">
            <div className="w-full max-w-sm space-y-6">
                {/* eslint-disable-next-line @next/next/no-img-element */}
                <img src="/mark-lockup.svg" alt={t({ en: ".mark logo", fr: "Logo .mark" })} className="mx-auto h-7" />
                <div className="space-y-1.5 text-center">
                    <h1 className="text-2xl font-semibold tracking-tight">{titre}</h1>
                    {sousTitre && <p className="text-sm text-muted-foreground">{sousTitre}</p>}
                </div>
                {children}
            </div>
        </main>
    );
}
