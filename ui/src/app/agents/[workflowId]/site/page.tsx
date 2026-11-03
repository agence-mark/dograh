"use client";

// [.mark] U3 quater (E65) : l'onglet Site d'un agent dont le canal est le site.
import { useParams } from "next/navigation";

import { EntetePageAgent } from "@/components/mark/agent/EntetePageAgent";
import { PageSiteAgent } from "@/components/mark/site/PageSiteAgent";

export default function OngletSiteAgent() {
    const { workflowId } = useParams();
    return (
        <EntetePageAgent agentId={Number(workflowId)} onglet="site">
            <PageSiteAgent agentId={Number(workflowId)} />
        </EntetePageAgent>
    );
}
