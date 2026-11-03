"use client";

// [.mark] U3 : l'onglet Versions (historique paginé, ouvrir, comparer) ; il remplace le panneau latéral de l'éditeur.
import { useParams } from "next/navigation";

import { EntetePageAgent } from "@/components/mark/agent/EntetePageAgent";
import { PageVersions } from "@/components/mark/agent/PageVersions";

export default function OngletVersionsAgent() {
    const { workflowId } = useParams();
    return (
        <EntetePageAgent agentId={Number(workflowId)} onglet="versions">
            <PageVersions agentId={Number(workflowId)} />
        </EntetePageAgent>
    );
}
