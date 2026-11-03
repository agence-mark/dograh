"use client";

/**
 * [.mark] Le cadre des pages d'accès (connexion, premier compte, « Rejoindre l'équipe .mark »), repris de la maquette
 * (`components/studio/acces.tsx`, K1) : une colonne étroite alignée à gauche, le logo, un titre et sa phrase, le contenu.
 */
import type { ReactNode } from "react";

import { useLangue } from "@/components/mark/langue/langue";

export function CadreAcces({ titre, sousTitre, children }: { titre: string; sousTitre?: ReactNode; children: ReactNode }) {
    const { t } = useLangue();
    return (
        <main className="flex min-h-screen items-center justify-center bg-white px-4">
            <div className="w-full max-w-sm space-y-8">
                {/* eslint-disable-next-line @next/next/no-img-element */}
                <img src="/mark-lockup.svg" alt={t({ en: ".mark logo", fr: "Logo .mark" })} className="h-7" />
                <div className="space-y-1">
                    <h1 className="text-2xl font-semibold tracking-tight">{titre}</h1>
                    {sousTitre && <p className="text-sm text-muted-foreground">{sousTitre}</p>}
                </div>
                {children}
            </div>
        </main>
    );
}

/** Un champ de la maquette : le libellé au-dessus, l'aide dessous. */
export function ChampAcces({ libelle, aide, children }: { libelle: string; aide?: string; children: ReactNode }) {
    return (
        <label className="block space-y-1.5">
            <span className="text-sm font-medium">{libelle}</span>
            {children}
            {aide && <span className="block text-xs text-muted-foreground">{aide}</span>}
        </label>
    );
}

/** Le pied d'une page d'accès : un trait, une phrase. */
export function PiedAcces({ children }: { children: ReactNode }) {
    return <p className="border-t pt-4 text-xs text-muted-foreground">{children}</p>;
}
