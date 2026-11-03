"use client";

// [.mark] U3 : l'onglet Tests monte l'écran actuel des tests de l'agent (refondu par B2) sous l'en-tête de l'agent.
import { useParams } from "next/navigation";

import PageTestsDeLAgent from "@/app/workflow/[workflowId]/tests/page";
import { EntetePageAgent } from "@/components/mark/agent/EntetePageAgent";

export default function OngletTestsAgent() {
    const { workflowId } = useParams();
    return (
        <EntetePageAgent agentId={Number(workflowId)} onglet="tests">
            <PageTestsDeLAgent />
        </EntetePageAgent>
    );
}
