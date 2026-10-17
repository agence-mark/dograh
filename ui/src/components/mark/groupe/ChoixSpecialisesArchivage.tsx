"use client";

/**
 * [.mark] Chantier agents-specialises, lot 10 (A10) : « supprimer un principal demande à l'écran quoi
 * faire de ses spécialisés » : les garder comme agents seuls, ou les archiver avec lui. Une modale
 * centrée ; rien n'est supprimé (archiver est réversible). Le choix part à la route du groupe.
 */
import { useState } from "react";
import { toast } from "sonner";

import { archiverUnPrincipalApiV1WorkflowWorkflowIdGroupeArchiverPost } from "@/client/sdk.gen";
import { Button } from "@/components/ui/button";
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { detailFromError } from "@/lib/apiError";

import { type Texte, useLangue } from "../langue/langue";

const TEXTES = {
    titre: { en: "Archive the main agent", fr: "Archiver l'agent principal" },
    question: {
        en: "What should happen to its specialised agents?",
        fr: "Que faire de ses agents spécialisés ?",
    },
    garder: { en: "Keep them as lone agents", fr: "Les garder comme agents seuls" },
    archiver: { en: "Archive them too", fr: "Les archiver aussi" },
    annuler: { en: "Cancel", fr: "Annuler" },
    fait: { en: "Main agent archived.", fr: "Agent principal archivé." },
    echec: { en: "The main agent could not be archived.", fr: "L'agent principal n'a pas pu être archivé." },
} satisfies Record<string, Texte>;

export const ChoixSpecialisesArchivage = ({
    principal,
    nombre,
    onFerme,
    onFait,
}: {
    principal: { id: number; name: string } | null;
    nombre: number;
    onFerme: () => void;
    onFait: () => void;
}) => {
    const { t } = useLangue();
    const [enCours, setEnCours] = useState(false);

    const choisir = async (specialises: "garder" | "archiver") => {
        if (!principal) return;
        setEnCours(true);
        try {
            const reponse = await archiverUnPrincipalApiV1WorkflowWorkflowIdGroupeArchiverPost({
                path: { workflow_id: principal.id },
                body: { specialises },
            });
            if (reponse.error) {
                toast.error(detailFromError(reponse.error, t(TEXTES.echec)));
                return;
            }
            toast.success(t(TEXTES.fait));
            onFait();
        } catch {
            toast.error(t(TEXTES.echec));
        } finally {
            setEnCours(false);
            onFerme();
        }
    };

    return (
        <Dialog open={principal !== null} onOpenChange={(ouvert) => !ouvert && onFerme()}>
            <DialogContent className="sm:max-w-md" data-modale="archiver-principal">
                <DialogHeader>
                    <DialogTitle>
                        {t(TEXTES.titre)} : {principal?.name}
                    </DialogTitle>
                    <DialogDescription>
                        {t(TEXTES.question)} ({nombre})
                    </DialogDescription>
                </DialogHeader>
                <DialogFooter className="gap-2 sm:flex-col sm:space-x-0">
                    <Button type="button" disabled={enCours} onClick={() => void choisir("garder")}>
                        {t(TEXTES.garder)}
                    </Button>
                    <Button type="button" variant="outline" disabled={enCours} onClick={() => void choisir("archiver")}>
                        {t(TEXTES.archiver)}
                    </Button>
                    <Button type="button" variant="ghost" disabled={enCours} onClick={onFerme}>
                        {t(TEXTES.annuler)}
                    </Button>
                </DialogFooter>
            </DialogContent>
        </Dialog>
    );
};
