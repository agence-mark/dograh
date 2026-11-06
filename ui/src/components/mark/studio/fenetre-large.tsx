"use client";

import { Dialog, DialogContent, DialogTitle } from "@/components/ui/dialog";

import { Info } from "./marques";

/**
 * [.mark] K5 : la fenêtre à pied de la maquette de la Bibliothèque (`Fenetre` de `components/studio/bibliotheque.tsx`) :
 * en-tête fixe (titre, ligne grise), corps blanc qui défile sans carte, pied fixe. `large` : 3xl et 86 % de la hauteur ;
 * sinon xl. Les sections du corps sont des `Carte` (titre gras + « ! »), séparées de 32 px.
 */
export function FenetreLarge({
    ouverte = true,
    fermer,
    titre,
    sous,
    children,
    pied,
    large = true,
    liste = false,
    testid,
    centree = false,
}: {
    ouverte?: boolean;
    fermer: () => void;
    titre: React.ReactNode;
    sous?: React.ReactNode;
    children: React.ReactNode;
    pied: React.ReactNode;
    large?: boolean;
    /** Une liste en lignes séparées par un trait, sans conteneur, sur fond blanc. */
    liste?: boolean;
    testid?: string;
    /** Une confirmation, une création, un configurateur : reste au milieu de l'écran (liste des centrées de `07-fenetres-panneau-ou-centrees.md`). */
    centree?: boolean;
}) {
    return (
        <Dialog centree={centree} open={ouverte} onOpenChange={(o) => !o && fermer()}>
            <DialogContent
                data-testid={testid}
                onOpenAutoFocus={(e) => e.preventDefault()}
                className={`${large ? "h-[86vh] sm:max-w-3xl" : "max-h-[86vh] sm:max-w-xl"} flex flex-col gap-0 overflow-hidden p-0`}
            >
                <div className="shrink-0 border-b px-6 pt-5 pr-12 pb-4">
                    <DialogTitle className="text-lg">{titre}</DialogTitle>
                    {sous && <div className="mt-0.5 text-sm text-muted-foreground">{sous}</div>}
                </div>
                <div className={`min-h-0 flex-1 overflow-auto bg-background ${liste ? "px-6 py-2" : "space-y-8 px-6 py-5"}`}>{children}</div>
                <div className="flex shrink-0 items-center gap-2 border-t px-6 py-3">{pied}</div>
            </DialogContent>
        </Dialog>
    );
}

export function Carte({ titre, info, children }: { titre?: React.ReactNode; info?: React.ReactNode; children: React.ReactNode }) {
    return (
        <section className="space-y-3">
            {titre && (
                <p className="flex items-center gap-1.5 text-sm font-semibold">
                    {titre}
                    {info && <Info>{info}</Info>}
                </p>
            )}
            {children}
        </section>
    );
}

export function ChampFenetre({ titre, info, children }: { titre: React.ReactNode; info?: React.ReactNode; children: React.ReactNode }) {
    return (
        <div className="space-y-1.5">
            <p className="flex items-center gap-1.5 text-sm">
                {titre}
                {info && <Info>{info}</Info>}
            </p>
            {children}
        </div>
    );
}
