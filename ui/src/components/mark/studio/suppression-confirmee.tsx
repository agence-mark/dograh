"use client";

/**
 * [.mark] R3 M3 : le geste de suppression en deux temps (`bonnes-pratiques-ecran.md`, « Gestes sûrs »).
 *
 * - `SuppressionConfirmee` : confirmation EN PLACE, dans le pied d'une fenêtre ou au bout d'une ligne : le premier clic montre
 *   « Supprimer ? Non / Oui, supprimer », le second seulement supprime. Aucune fenêtre de plus par-dessus une fenêtre.
 * - `ConfirmerSuppression` : fenêtre centrée à corps blanc, quand la suppression se déclenche depuis un menu ou une icône
 *   sans place pour la confirmation en place.
 *
 * Le test `suppressions-confirmees.test.ts` échoue sur tout appel `*Delete` sans l'un de ces deux motifs, un « Annuler »
 * différé (`notifier.annulable`, `notifier.reversible`) ou une exemption écrite `suppression-confirmee : <où>`.
 */
import { type ReactNode, useState } from "react";

import { useLangue } from "@/components/mark/langue/langue";
import { Button } from "@/components/ui/button";
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from "@/components/ui/dialog";

interface PropsEnPlace {
    /** Le contenu du premier bouton (icône + libellé). */
    children: ReactNode;
    onConfirmer: () => void;
    /** Libellé accessible du premier bouton quand il n'a qu'une icône. */
    libelle?: string;
    disabled?: boolean;
    className?: string;
    size?: "sm" | "default";
    variant?: "ghost" | "outline";
}

export function SuppressionConfirmee({ children, onConfirmer, libelle, disabled, className, size = "sm", variant = "ghost" }: PropsEnPlace) {
    const { t } = useLangue();
    const [demande, setDemande] = useState(false);
    if (!demande) {
        return (
            <Button type="button" variant={variant} size={size} className={`cursor-pointer ${className ?? ""}`} aria-label={libelle} disabled={disabled} onClick={() => setDemande(true)}>
                {children}
            </Button>
        );
    }
    return (
        <span className="inline-flex items-center gap-1" role="group" aria-label={t({ en: "Confirm the deletion", fr: "Confirmer la suppression" })}>
            <Button type="button" variant="outline" size="sm" className="cursor-pointer" autoFocus onClick={() => setDemande(false)}>
                {t({ en: "No", fr: "Non" })}
            </Button>
            <Button
                type="button"
                variant="destructive"
                size="sm"
                className="cursor-pointer"
                data-confirmer-suppression
                onClick={() => {
                    setDemande(false);
                    onConfirmer();
                }}
            >
                {t({ en: "Yes, delete", fr: "Oui, supprimer" })}
            </Button>
        </span>
    );
}

interface PropsFenetre {
    ouvert: boolean;
    titre: string;
    description?: string;
    onConfirmer: () => void;
    onFermer: () => void;
    enCours?: boolean;
}

export function ConfirmerSuppression({ ouvert, titre, description, onConfirmer, onFermer, enCours }: PropsFenetre) {
    const { t } = useLangue();
    return (
        <Dialog open={ouvert} onOpenChange={(o) => !o && onFermer()}>
            <DialogContent className="sm:max-w-md">
                <DialogHeader>
                    <DialogTitle>{titre}</DialogTitle>
                    {description && <DialogDescription>{description}</DialogDescription>}
                </DialogHeader>
                <DialogFooter>
                    <Button type="button" variant="outline" className="cursor-pointer" onClick={onFermer}>
                        {t({ en: "Cancel", fr: "Annuler" })}
                    </Button>
                    <Button type="button" variant="destructive" className="cursor-pointer" disabled={enCours} data-confirmer-suppression onClick={onConfirmer}>
                        {t({ en: "Delete", fr: "Supprimer" })}
                    </Button>
                </DialogFooter>
            </DialogContent>
        </Dialog>
    );
}
