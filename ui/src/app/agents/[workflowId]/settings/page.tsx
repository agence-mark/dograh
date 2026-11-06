"use client";

// [.mark] U3 : l'onglet Réglages monte l'écran actuel des réglages de l'agent (refondu par D1) sous l'en-tête de l'agent.
import { useParams } from "next/navigation";

import SettingsPage from "@/app/workflow/[workflowId]/settings/page";
import { EntetePageAgent } from "@/components/mark/agent/EntetePageAgent";

export default function OngletReglagesAgent() {
    const { workflowId } = useParams();
    return (
        <EntetePageAgent agentId={Number(workflowId)} onglet="reglages">
            <SettingsPage />
        </EntetePageAgent>
    );
}
