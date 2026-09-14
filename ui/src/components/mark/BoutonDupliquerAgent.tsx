"use client";

import { Copy } from "lucide-react";
import { useState } from "react";
import { toast } from "sonner";

import { duplicateWorkflowEndpointApiV1WorkflowWorkflowIdDuplicatePost } from "@/client";
import { Button } from "@/components/ui/button";

/**
 * [.mark] Duplicate an agent straight from its row in the list.
 *
 * Why: an A/B branch is a copy of the agent, and making one meant opening the
 * editor, finding the menu, duplicating, then coming back. The server route
 * and the editor's own button have existed all along; only the list was
 * missing the action.
 *
 * ⛔ No new server code. This calls the very same endpoint the editor calls,
 * so whatever the copy does or does not carry stays one behaviour, not two.
 *
 * ✅ We stay on the list, which refreshes and shows the copy (Evan, 14/09).
 * The copy lands at the root even when the original sits in a folder -- the
 * server decides that, and the success message says so, otherwise people look
 * for it inside the folder and conclude the button did nothing.
 */

interface BoutonDupliquerAgentProps {
    workflowId: number;
    /** Called once the copy exists, so the list can refresh. */
    onDuplique: () => void;
}

export const BoutonDupliquerAgent = ({
    workflowId,
    onDuplique,
}: BoutonDupliquerAgentProps) => {
    const [enCours, setEnCours] = useState(false);

    const dupliquer = async () => {
        // ⛔ Guarded twice: disabled on the button, and checked here. A double
        // click on a slow connection creates two copies, and nothing on the
        // screen would explain the second one.
        if (enCours) return;
        setEnCours(true);
        try {
            const reponse =
                await duplicateWorkflowEndpointApiV1WorkflowWorkflowIdDuplicatePost({
                    path: { workflow_id: workflowId },
                });
            // ⚠️ The generated client does NOT throw on an HTTP error: it
            // resolves with `{ data, error }`. Without this check a 500 would
            // read as a success and the list would refresh onto nothing.
            if (reponse.error) {
                toast.error("Failed to duplicate agent");
                return;
            }
            toast.success("Agent duplicated. The copy is at the root of the list.");
            onDuplique();
        } catch {
            toast.error("Failed to duplicate agent");
        } finally {
            setEnCours(false);
        }
    };

    return (
        <Button
            variant="outline"
            size="sm"
            onClick={dupliquer}
            disabled={enCours}
            className="flex items-center gap-2"
        >
            {enCours ? (
                <div className="h-4 w-4 animate-spin rounded-full border-2 border-current border-t-transparent" />
            ) : (
                <Copy size={16} />
            )}
            Duplicate
        </Button>
    );
};
