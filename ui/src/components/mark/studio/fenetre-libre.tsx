"use client";

import { Dialog, DialogContent, DialogTitle } from "@/components/ui/dialog";

import { Info } from "./marques";

/**
 * [.mark] K4b : la fenêtre de la maquette dont le pied porte des boutons que le fork décide (créer ou rattacher une
 * base : deux gestes, deux boutons). Même forme que `FenetreChamps` : en-tête fixe, corps blanc sans carte, pied fixe.
 */
export function FenetreLibre({
    ouverte,
    fermer,
    titre,
    info,
    corps,
    pied,
    actions,
    centree = false,
}: {
    ouverte: boolean;
    fermer: () => void;
    titre: React.ReactNode;
    info?: React.ReactNode;
    corps: React.ReactNode;
    /** À gauche du pied (un geste rare : détacher, retirer). */
    pied?: React.ReactNode;
    /** À droite du pied : Annuler et le geste principal. */
    actions: React.ReactNode;
    /** Reste au milieu de l'écran (liste des centrées de `07-fenetres-panneau-ou-centrees.md`). */
    centree?: boolean;
}) {
    return (
        <Dialog centree={centree} open={ouverte} onOpenChange={(o) => !o && fermer()}>
            <DialogContent onOpenAutoFocus={(e) => e.preventDefault()} className="flex max-h-[86vh] flex-col gap-0 overflow-hidden p-0 sm:max-w-xl">
                <div className="shrink-0 border-b px-6 pt-5 pr-12 pb-4">
                    <DialogTitle className="flex items-center gap-2 text-lg">
                        {titre}
                        {info && <Info>{info}</Info>}
                    </DialogTitle>
                </div>
                <div className="min-h-0 flex-1 overflow-auto bg-background px-6 py-1">{corps}</div>
                <div className="flex shrink-0 items-center justify-end gap-2 border-t px-6 py-3">
                    {pied && <div className="mr-auto">{pied}</div>}
                    {actions}
                </div>
            </DialogContent>
        </Dialog>
    );
}
