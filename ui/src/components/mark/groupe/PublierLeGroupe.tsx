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
import { useRouter } from "next/navigation";
import { useState } from "react";
import { adresseOnglet } from "@/components/mark/agent/onglets-agent";
import { notifier } from "@/components/mark/notifications";

import { publierLeGroupeApiV1WorkflowWorkflowIdGroupePublierPost } from "@/client/sdk.gen";
import type { PublierGroupeResponse } from "@/client/types.gen";
import { Button } from "@/components/ui/button";
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from "@/components/ui/dialog";

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
    const router = useRouter();
    const [enCours, setEnCours] = useState(false);
    // [.mark] Partie 3 (SE-12) : `choix` = les seuls spécialistes à publier (un choix par spécialiste), le principal restant à part
    // quand `avecLePrincipal` est faux (la fenêtre Publier vient de le publier avec ses propres contrôles). Sans choix : tout le groupe.
    const publier = async (
        principalId: number,
        choix?: { specialises: number[]; avecLePrincipal: boolean },
    ): Promise<PublierGroupeResponse | null> => {
        setEnCours(true);
        try {
            const reponse = await publierLeGroupeApiV1WorkflowWorkflowIdGroupePublierPost({
                path: { workflow_id: principalId },
                ...(choix ? { body: { specialises: choix.specialises, avec_le_principal: choix.avecLePrincipal } } : {}),
            });
            if (reponse.error || !reponse.data) {
                notifier.echec({ fr: "Groupe non publié. Réessayez.", en: "Group not published. Try again." }, { erreur: reponse.error });
                return null;
            }
            const corps = reponse.data;
            if (corps.refus) {
                notifier.echec({ fr: `Publication refusée pour « ${corps.refus.name} » : ${corps.refus.detail}.`, en: `Publication refused for "${corps.refus.name}": ${corps.refus.detail}.` }, { bouton: { libelle: { fr: "Ouvrir l'agent", en: "Open the agent" }, action: () => router.push(adresseOnglet(corps.refus!.id, "parcours")) } });
            } else if ((corps.publies ?? []).length === 0) {
                notifier.information({ fr: "Le groupe est déjà à jour.", en: "The group is already up to date." });
            } else {
                notifier.succes({ fr: `Publié : ${(corps.publies ?? []).map((p) => p.name).join(", ")}.`, en: `Published: ${(corps.publies ?? []).map((p) => p.name).join(", ")}.` });
            }
            return corps;
        } catch {
            notifier.echec({ fr: "Groupe non publié. Réessayez.", en: "Group not published. Try again." });
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
        <Dialog centree open={ouvert} onOpenChange={onOuvertChange}>
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
