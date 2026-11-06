"use client";

/**
 * [.mark] builder-agent-vocal (lot 6): « Tests and corrections » (`/workflow/<id>/tests`). The button of the editor's top bar is placed
 * by the builder panel's chantier; this is the page it opens.
 */
import { useParams } from "next/navigation";

import { PageTests } from "@/components/builder/tests/PageTests";
import { useLangue } from "@/components/mark/langue/langue";
import { Skeleton } from "@/components/ui/skeleton";
import { useAuth } from "@/lib/auth";

import WorkflowLayout from "../../WorkflowLayout";

export default function PageTestsDeLAgent() {
    const { workflowId } = useParams();
    const { t } = useLangue();
    const { user, loading } = useAuth();

    return (
        <WorkflowLayout showFeaturesNav={false}>
            <div className="container mx-auto px-4 py-8" data-testid="page-tests-agent">
                <div className="mx-auto max-w-4xl space-y-6">
                    <div>
                        <h1 className="mb-2 text-3xl font-bold">{t({ en: "Tests and corrections", fr: "Tests et corrections" })}</h1>
                        <p className="text-muted-foreground">
                            {t({
                                en: "The tests of this agent, judged by the code. A required test that fails, or a prompt check that fails, blocks the publication.",
                                fr: "Les tests de cet agent, jugés par le code. Un test obligatoire qui échoue, ou un contrôle du prompt qui échoue, bloque la publication.",
                            })}
                        </p>
                    </div>
                    {loading || !user ? <Skeleton className="h-64 w-full" /> : <PageTests workflowId={Number(workflowId)} />}
                </div>
            </div>
        </WorkflowLayout>
    );
}
