"use client";

// [.mark] U3 : l'onglet Appels monte la liste des appels de l'agent sous l'en-tête de l'agent.
import { useParams, useSearchParams } from "next/navigation";

import { WorkflowExecutions } from "@/app/workflow/[workflowId]/components/WorkflowExecutions";
import { EntetePageAgent } from "@/components/mark/agent/EntetePageAgent";

export default function OngletAppelsAgent() {
    const { workflowId } = useParams();
    const searchParams = useSearchParams();
    return (
        <EntetePageAgent agentId={Number(workflowId)} onglet="appels">
            <WorkflowExecutions workflowId={Number(workflowId)} searchParams={searchParams} forme="agent" />
        </EntetePageAgent>
    );
}
