"use client";

// [.mark] U3 (E47) : l'onglet Tests de l'agent (liste, exécutions passées, fenêtre d'un test, depuis la bibliothèque).
import { useParams } from "next/navigation";

import { PageTests } from "@/components/builder/tests/PageTests";
import { EntetePageAgent } from "@/components/mark/agent/EntetePageAgent";
import { Skeleton } from "@/components/ui/skeleton";
import { useAuth } from "@/lib/auth";

export default function OngletTestsAgent() {
    const { workflowId } = useParams();
    const { user, loading } = useAuth();
    return (
        <EntetePageAgent agentId={Number(workflowId)} onglet="tests">
            {loading || !user ? <Skeleton className="m-6 h-64" /> : <PageTests workflowId={Number(workflowId)} />}
        </EntetePageAgent>
    );
}
