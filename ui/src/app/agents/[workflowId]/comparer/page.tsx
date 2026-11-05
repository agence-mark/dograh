"use client";

// [.mark] Partie 3, SA-L3c : « Comparer en duel » deux branches ou deux versions d'un agent (sous l'onglet Versions).
import { useParams } from "next/navigation";

import { PageComparer } from "@/components/mark/agent/branches/PageComparer";
import { EntetePageAgent } from "@/components/mark/agent/EntetePageAgent";
import { useLangue } from "@/components/mark/langue/langue";

export default function ComparerAgent() {
    const { workflowId } = useParams();
    const { t } = useLangue();
    return (
        <EntetePageAgent agentId={Number(workflowId)} onglet="versions" fil={t({ en: "Compare", fr: "Comparer" })}>
            <PageComparer agentId={Number(workflowId)} />
        </EntetePageAgent>
    );
}
