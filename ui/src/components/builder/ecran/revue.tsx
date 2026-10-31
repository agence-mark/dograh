"use client";

/**
 * [.mark] builder-agent-vocal (lot 4): the review of the builder's changes, shared by the « Changes » card and the
 * draft banner (See · Accept/Refuse), so both do exactly the same thing.
 */
import { useState } from "react";
import { toast } from "sonner";

import { WorkflowVersionDiffDialog } from "@/app/workflow/[workflowId]/components/WorkflowVersionDiffDialog";
import { getWorkflowVersionsApiV1WorkflowWorkflowIdVersionsGet } from "@/client";
import type { WorkflowVersionResponse } from "@/client/types.gen";
import { type Texte, useLangue } from "@/components/mark/langue/langue";
import { detailFromError } from "@/lib/apiError";

import { useContexteDuPanneau } from "./contexte-du-panneau";
import { appliquerLesOperations, comparer, type Resume, resumer } from "./graphe";
import { useBuilderEcran } from "./store";

const T = {
    pasDeVersion: { en: "No earlier version to compare with.", fr: "Pas de version antérieure à comparer." },
    accepte: { en: "Changes accepted (still a draft, not published).", fr: "Changements acceptés (toujours un brouillon, pas publié)." },
    refuse: { en: "Changes refused: the graph from before is back.", fr: "Changements refusés : le graphe d'avant est revenu." },
    echecRefus: { en: "The graph from before could not be restored.", fr: "Le graphe d'avant n'a pas pu être restauré." },
} satisfies Record<string, Texte>;

export interface RevueDesChangements {
    /** `null` when nothing is under review. */
    resume: Resume | null;
    /** Operations are still arriving (the draft is not saved yet): Accept and Refuse wait. */
    enAttente: boolean;
    occupe: boolean;
    peutVoir: boolean;
    voir: () => Promise<void>;
    accepter: () => void;
    refuser: () => Promise<void>;
    dialogue: React.ReactNode;
}

export function useRevueDesChangements(): RevueDesChangements {
    const { t } = useLangue();
    const { workflowId, lireLeGraphe, restaurer } = useContexteDuPanneau();
    const avant = useBuilderEcran((s) => s.avant);
    const operations = useBuilderEcran((s) => s.operationsVives);
    const changements = useBuilderEcran((s) => s.changements);
    const solder = useBuilderEcran((s) => s.solderLesChangements);
    const [paire, setPaire] = useState<{ precedente: WorkflowVersionResponse; choisie: WorkflowVersionResponse } | null>(null);
    const [occupe, setOccupe] = useState(false);

    const enAttente = operations.length > 0;
    const resume = avant ? resumer(comparer(avant, enAttente ? appliquerLesOperations(avant, operations) : lireLeGraphe())) : null;

    const voir = async () => {
        const reponse = await getWorkflowVersionsApiV1WorkflowWorkflowIdVersionsGet({
            path: { workflow_id: workflowId },
            query: { limit: 10, offset: 0 },
        });
        if (reponse.error || !reponse.data) {
            toast.error(detailFromError(reponse.error, "Failed to load version history"));
            return;
        }
        const choisie = reponse.data.find((v) => v.status === "draft");
        const precedente = reponse.data.find((v) => v.status === "published") ?? reponse.data.find((v) => v.status !== "draft");
        if (!choisie || !precedente) {
            toast.message(t(T.pasDeVersion));
            return;
        }
        setPaire({ precedente, choisie });
    };

    const accepter = () => {
        solder();
        toast.success(t(T.accepte));
    };

    const refuser = async () => {
        if (!avant) return;
        setOccupe(true);
        const ok = await restaurer(avant);
        setOccupe(false);
        if (!ok) {
            toast.error(t(T.echecRefus));
            return;
        }
        solder();
        toast.success(t(T.refuse));
    };

    return {
        resume,
        enAttente,
        occupe,
        peutVoir: Boolean(changements) && !enAttente,
        voir,
        accepter,
        refuser,
        dialogue: paire ? (
            <WorkflowVersionDiffDialog
                open
                onOpenChange={(ouvert) => {
                    if (!ouvert) setPaire(null);
                }}
                previousVersion={paire.precedente}
                selectedVersion={paire.choisie}
            />
        ) : null,
    };
}
