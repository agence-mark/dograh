"use client";

/**
 * [.mark] Builder partie 3, SA-L3a : la correction en un clic d'un réglage « sans effet ». Écrit dans le BROUILLON (rien n'est
 * publié), dit le résultat par une notification, puis fait relire toutes les listes affichées.
 */
import { useCallback, useState } from "react";

import { corrigerUnReglageApiV1BuilderPublicationWorkflowIdCorrigerUnReglagePost } from "@/client/sdk.gen";
import { notifier } from "@/components/mark/notifications";

import { useRecalculDuPret } from "./recalcul";
import type { CorrectionDeLigne } from "./textes";

export function useCorrectionEnUnClic(workflowId: number, apres?: () => void | Promise<void>) {
    const [enCours, setEnCours] = useState(false);
    const recalculer = useRecalculDuPret((s) => s.demander);
    const corriger = useCallback(
        async (correction: CorrectionDeLigne) => {
            if (enCours) return;
            setEnCours(true);
            try {
                const r = await corrigerUnReglageApiV1BuilderPublicationWorkflowIdCorrigerUnReglagePost({
                    path: { workflow_id: workflowId },
                    body: { correction: correction.id, noeud_id: correction.noeud_id ?? null, liaison_id: correction.liaison_id ?? null },
                });
                if (r.error) {
                    notifier.echec(
                        { fr: "Correction impossible : l'agent a changé. La liste est relue.", en: "Could not fix: the agent changed. The list is read again." },
                        { erreur: r.error },
                    );
                } else {
                    notifier.succes({ fr: "Corrigé dans le brouillon. Rien n'est publié.", en: "Fixed in the draft. Nothing is published." });
                }
                recalculer();
                await apres?.();
            } finally {
                setEnCours(false);
            }
        },
        [workflowId, enCours, recalculer, apres],
    );
    return { corriger, enCours };
}
