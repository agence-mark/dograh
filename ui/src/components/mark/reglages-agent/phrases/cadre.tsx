"use client";

/**
 * [.mark] correctifs-apres-banc-v4, lot 5 : les morceaux communs des modales du thème Phrases.
 * Le cadre : modale CENTRÉE (jamais un panneau latéral), en-tête fixe, corps qui défile sans barre visible, pied
 * figé. `L` est une ligne « libellé + cases + aide » ; `Gris` la ligne grise qui remplace une case qui ne
 * s'applique pas au motif.
 */
import { Info } from "lucide-react";
import type { ReactNode } from "react";

import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from "@/components/ui/dialog";

export const CadreModale = ({
    titre,
    description,
    onFermer,
    pied,
    children,
    identifiant,
}: {
    titre: string;
    description: string;
    onFermer: () => void;
    pied: ReactNode;
    children: ReactNode;
    identifiant?: string;
}) => (
    <Dialog open onOpenChange={(ouvert) => !ouvert && onFermer()}>
        <DialogContent data-modale-phrase={identifiant} className="flex max-h-[90vh] flex-col gap-0 overflow-hidden p-0 sm:max-w-3xl">
            <DialogHeader className="shrink-0 border-b px-6 pb-4 pt-6">
                <DialogTitle>{titre}</DialogTitle>
                <DialogDescription>{description}</DialogDescription>
            </DialogHeader>
            <div className="min-h-0 flex-1 overflow-y-auto px-6 py-5 [scrollbar-width:none] [&::-webkit-scrollbar]:hidden">{children}</div>
            <DialogFooter className="shrink-0 items-center border-t bg-background px-6 py-4 sm:justify-between">{pied}</DialogFooter>
        </DialogContent>
    </Dialog>
);

export const L = ({ label, children, aide, nom }: { label: string; children: ReactNode; aide?: string; nom?: string }) => (
    <div className="grid grid-cols-[120px_1fr] items-start gap-3" data-ligne-phrase={nom}>
        <span className="pt-2 text-sm font-medium">{label}</span>
        <div className="space-y-1">
            <div className="flex flex-wrap items-center gap-2">{children}</div>
            {aide && <p className="text-xs text-muted-foreground">{aide}</p>}
        </div>
    </div>
);

export const Gris = ({ children }: { children: ReactNode }) => (
    <span className="flex items-start gap-1.5 text-xs text-muted-foreground" data-gris>
        <Info className="mt-0.5 h-3.5 w-3.5 shrink-0" />
        <span>{children}</span>
    </span>
);
