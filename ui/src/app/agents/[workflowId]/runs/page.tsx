"use client";

// [.mark] U3 : l'onglet Appels monte la liste des appels de l'agent sous l'en-tête de l'agent.
import { useParams } from "next/navigation";

import WorkflowRunsPage from "@/app/workflow/[workflowId]/runs/page";
import { EntetePageAgent } from "@/components/mark/agent/EntetePageAgent";

export default function OngletAppelsAgent() {
    const { workflowId } = useParams();
    return (
        <EntetePageAgent agentId={Number(workflowId)} onglet="appels">
            <WorkflowRunsPage />
        </EntetePageAgent>
    );
}
