"use client";

/**
 * [.mark] Chantier agents-specialises, lot 10 (A10) : « publier le principal propose de publier tout le
 * groupe ». La route publie agent par agent (les spécialisés d'abord, le principal en dernier) et
 * s'arrête au premier refus en le disant : ce composant montre ce qui est parti et, le cas échéant,
 * quel agent a refusé et pourquoi.
 *
 * - ``BoutonPublierLeGroupe`` : dans la vue du groupe de la liste d'agents ;
 * - ``ProposerLaPublicationDuGroupe`` : une modale centrée proposée dans l'éditeur du principal, juste
 *   après la publication de l'agent.
 */
import { Rocket } from "lucide-react";
import { useState } from "react";
import { toast } from "sonner";

import { publierLeGroupeApiV1WorkflowWorkflowIdGroupePublierPost } from "@/client/sdk.gen";
import type { PublierGroupeResponse } from "@/client/types.gen";
import { Button } from "@/components/ui/button";
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { detailFromError } from "@/lib/apiError";

import { type Texte, useLangue } from "../langue/langue";

const TEXTES = {
    bouton: { en: "Publish the group", fr: "Publier le groupe" },
    enCours: { en: "Publishing...", fr: "Publication..." },
    ok: { en: "Group published", fr: "Groupe publié" },
    aJour: { en: "Nothing to publish: the whole group is up to date.", fr: "Rien à publier : tout le groupe est à jour." },
    refus: { en: "Not published:", fr: "Non publié :" },
    echec: { en: "The group could not be published.", fr: "Le groupe n'a pas pu être publié." },
    titreProposition: { en: "Publish the whole group?", fr: "Publier tout le groupe ?" },
    descriptionProposition: {
        en: "The main agent is published. Its specialised agents may still hold unpublished changes: publish them too, one by one, stopping at the first refusal.",
        fr: "L'agent principal est publié. Ses agents spécialisés peuvent encore avoir des changements non publiés : les publier aussi, un par un, en s'arrêtant au premier refus.",
    },
    plusTard: { en: "Not now", fr: "Pas maintenant" },
} satisfies Record<string, Texte>;

/** Joue la publication du groupe et dit le résultat ; rend la réponse (ou null si la route a échoué). */
export const usePublierLeGroupe = () => {
    const { t } = useLangue();
    const [enCours, setEnCours] = useState(false);
    const publier = async (principalId: number): Promise<PublierGroupeResponse | null> => {
        setEnCours(true);
        try {
            const reponse = await publierLeGroupeApiV1WorkflowWorkflowIdGroupePublierPost({ path: { workflow_id: principalId } });
            if (reponse.error || !reponse.data) {
                toast.error(detailFromError(reponse.error, t(TEXTES.echec)));
                return null;
            }
            const corps = reponse.data;
            if (corps.refus) {
                toast.error(`${t(TEXTES.refus)} ${corps.refus.name} : ${corps.refus.detail}`);
            } else if ((corps.publies ?? []).length === 0) {
                toast.success(t(TEXTES.aJour));
            } else {
                toast.success(`${t(TEXTES.ok)} : ${(corps.publies ?? []).map((p) => p.name).join(", ")}`);
            }
            return corps;
        } catch {
            toast.error(t(TEXTES.echec));
            return null;
        } finally {
            setEnCours(false);
        }
    };
    return { enCours, publier };
};

export const BoutonPublierLeGroupe = ({ principalId, onFait }: { principalId: number; onFait?: () => void }) => {
    const { t } = useLangue();
    const { enCours, publier } = usePublierLeGroupe();
    return (
        <Button
            type="button"
            variant="outline"
            size="sm"
            disabled={enCours}
            onClick={async () => {
                if (await publier(principalId)) onFait?.();
            }}
        >
            <Rocket className="mr-2 h-3.5 w-3.5" />
            {enCours ? t(TEXTES.enCours) : t(TEXTES.bouton)}
        </Button>
    );
};

export const ProposerLaPublicationDuGroupe = ({
    principalId,
    ouvert,
    onOuvertChange,
}: {
    principalId: number;
    ouvert: boolean;
    onOuvertChange: (ouvert: boolean) => void;
}) => {
    const { t } = useLangue();
    const { enCours, publier } = usePublierLeGroupe();
    return (
        <Dialog open={ouvert} onOpenChange={onOuvertChange}>
            <DialogContent className="sm:max-w-md" data-modale="publier-le-groupe">
                <DialogHeader>
                    <DialogTitle>{t(TEXTES.titreProposition)}</DialogTitle>
                    <DialogDescription>{t(TEXTES.descriptionProposition)}</DialogDescription>
                </DialogHeader>
                <DialogFooter>
                    <Button type="button" variant="outline" onClick={() => onOuvertChange(false)}>
                        {t(TEXTES.plusTard)}
                    </Button>
                    <Button
                        type="button"
                        disabled={enCours}
                        onClick={async () => {
                            await publier(principalId);
                            onOuvertChange(false);
                        }}
                    >
                        {enCours ? t(TEXTES.enCours) : t(TEXTES.bouton)}
                    </Button>
                </DialogFooter>
            </DialogContent>
        </Dialog>
    );
};
