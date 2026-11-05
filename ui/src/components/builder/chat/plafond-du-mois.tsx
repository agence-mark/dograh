"use client";

/**
 * [.mark] Partie 3, sous-lot 11 (SE-16, E-5) : le plafond de dépense du mois est atteint.
 *
 * La conversation en cours finit toujours ; c'est un NOUVEAU travail que le serveur refuse (402). L'écran le dit par une notification
 * et propose la fenêtre « Continuer quand même » : un dépassement explicite, pour CETTE demande seulement, réservé à l'équipe .mark
 * et journalisé par le serveur. Rien n'est mémorisé : la demande suivante redemande.
 */
import { type Texte, useLangue } from "@/components/mark/langue/langue";
import { Button } from "@/components/ui/button";
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from "@/components/ui/dialog";

export const STATUT_PLAFOND = 402;
export const STATUT_REFUSE = 403;

export const TEXTES_PLAFOND = {
    notification: {
        en: "The builder's monthly budget is reached. Your current work is not cut; a new one needs your agreement.",
        fr: "Le budget du mois du builder est atteint. Le travail en cours n'est pas coupé ; un nouveau demande votre accord.",
    },
    titre: { en: "Monthly budget reached", fr: "Budget du mois atteint" },
    description: {
        en: "Continuing spends beyond the monthly ceiling set in the builder settings. This applies to this request only, and it is written in the journal.",
        fr: "Continuer dépense au-delà du plafond du mois réglé dans les réglages du builder. Cela ne vaut que pour cette demande, et c'est écrit au journal.",
    },
    annuler: { en: "Cancel", fr: "Annuler" },
    continuer: { en: "Continue anyway", fr: "Continuer quand même" },
    reserve: {
        en: "Only the .mark team can go past the monthly budget. Ask them to raise it.",
        fr: "Seule l'équipe .mark peut dépasser le budget du mois. Demandez-lui de le relever.",
    },
} satisfies Record<string, Texte>;

export const statutDe = (r: { response?: { status?: number } }): number | undefined => r.response?.status;

export function FenetrePlafondDuMois({
    ouverte,
    enCours,
    continuer,
    annuler,
}: {
    ouverte: boolean;
    enCours: boolean;
    continuer: () => void;
    annuler: () => void;
}) {
    const { t } = useLangue();
    return (
        <Dialog centree open={ouverte} onOpenChange={(o) => !o && !enCours && annuler()}>
            <DialogContent className="sm:max-w-md" data-fenetre-plafond-du-mois>
                <DialogHeader>
                    <DialogTitle>{t(TEXTES_PLAFOND.titre)}</DialogTitle>
                    <DialogDescription>{t(TEXTES_PLAFOND.description)}</DialogDescription>
                </DialogHeader>
                <DialogFooter>
                    <Button type="button" variant="outline" className="cursor-pointer" autoFocus disabled={enCours} onClick={annuler}>
                        {t(TEXTES_PLAFOND.annuler)}
                    </Button>
                    <Button type="button" className="cursor-pointer" disabled={enCours} data-continuer-quand-meme onClick={continuer}>
                        {t(TEXTES_PLAFOND.continuer)}
                    </Button>
                </DialogFooter>
            </DialogContent>
        </Dialog>
    );
}
