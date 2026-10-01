"use client";

import { PhoneForwarded, PhoneOff } from "lucide-react";
import { useEffect, useState } from "react";
import { toast } from "sonner";

import {
    deciderDuRenvoiApiV1WorkflowWorkflowIdRunsRunIdRenvoiEnTestPost,
    etatDuRenvoiApiV1WorkflowWorkflowIdRunsRunIdRenvoiEnTestGet,
} from "@/client";
import { Button } from "@/components/ui/button";

/**
 * [.mark] Lot D (chantier fiabilite-fiche-et-renvoi, 01/10/2026): the tester's answer
 * to a call transfer, in the keyboard chat and in the voice tester.
 *
 * Outside telephony, Dograh's transfer tool used to fail on the spot: a transfer
 * could not be tried anywhere before production. The tool now waits for the
 * tester; these two buttons give the answer, and the agent receives exactly what
 * telephony would give it (accepted: the agent withdraws; declined: it carries on).
 *
 * ⛔ The labels are Evan's, word for word (01/10): « Accepter le renvoi d'appel »
 * and « Refuser le renvoi d'appel ». Nothing here is specific to a client.
 *
 * ``actif``: true while a transfer may be waiting (a keyboard message being
 * answered, a voice call in progress). The page asks the server every second
 * only then.
 */

const INTERVALLE_MS = 1000;

interface BoutonsRenvoiEnTestProps {
    workflowId: number;
    runId: number | null | undefined;
    actif: boolean;
}

export const BoutonsRenvoiEnTest = ({ workflowId, runId, actif }: BoutonsRenvoiEnTestProps) => {
    const [enAttente, setEnAttente] = useState(false);
    const [envoi, setEnvoi] = useState(false);

    useEffect(() => {
        if (!actif || !runId) {
            setEnAttente(false);
            return;
        }
        let arrete = false;
        const lire = async () => {
            try {
                const reponse = await etatDuRenvoiApiV1WorkflowWorkflowIdRunsRunIdRenvoiEnTestGet({
                    path: { workflow_id: workflowId, run_id: runId },
                });
                if (!arrete) setEnAttente(Boolean(reponse.data?.en_attente));
            } catch {
                // A missed poll is retried a second later; nothing to show.
            }
        };
        void lire();
        const minuterie = setInterval(() => void lire(), INTERVALLE_MS);
        return () => {
            arrete = true;
            clearInterval(minuterie);
        };
    }, [actif, runId, workflowId]);

    if (!actif || !runId || !enAttente) return null;

    const decider = async (accepte: boolean) => {
        if (envoi) return;
        setEnvoi(true);
        try {
            const reponse = await deciderDuRenvoiApiV1WorkflowWorkflowIdRunsRunIdRenvoiEnTestPost({
                path: { workflow_id: workflowId, run_id: runId },
                body: { accepte },
            });
            // The generated client resolves with `{ data, error }` on an HTTP error.
            if (reponse.error) {
                toast.error("Le renvoi n'attend plus de réponse (délai dépassé).");
            }
            setEnAttente(false);
        } catch {
            toast.error("La réponse au renvoi n'a pas pu être envoyée.");
        } finally {
            setEnvoi(false);
        }
    };

    return (
        <div className="flex flex-wrap gap-2 py-2" data-testid="boutons-renvoi-en-test">
            <Button type="button" size="sm" disabled={envoi} onClick={() => void decider(true)}>
                <PhoneForwarded className="h-3.5 w-3.5" />
                Accepter le renvoi d&apos;appel
            </Button>
            <Button type="button" size="sm" variant="outline" disabled={envoi} onClick={() => void decider(false)}>
                <PhoneOff className="h-3.5 w-3.5" />
                Refuser le renvoi d&apos;appel
            </Button>
        </div>
    );
};
