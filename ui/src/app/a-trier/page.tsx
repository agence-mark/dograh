"use client";

/**
 * [.mark] The « To triage » page of the menu (passages-fiables, lot G): what the agent and the code flagged during calls.
 */
import { useLangue } from "@/components/mark/langue/langue";
import { PageATrier } from "@/components/mark/tri/PageATrier";
import { Skeleton } from "@/components/ui/skeleton";
import { useAuth } from "@/lib/auth";

export default function PageATrierDuMenu() {
    const { t } = useLangue();
    const { user, loading } = useAuth();

    if (loading || !user) {
        return (
            <div className="container mx-auto px-4 py-8">
                <Skeleton className="h-64 w-full max-w-3xl" />
            </div>
        );
    }

    return (
        <div className="container mx-auto px-4 py-8" data-testid="page-a-trier-menu">
            <div className="mx-auto max-w-3xl space-y-6">
                <div>
                    <h1 className="mb-2 text-3xl font-bold">{t({ en: "To triage", fr: "À trier" })}</h1>
                    <p className="text-muted-foreground">
                        {t({
                            en: "The flags raised by the agent and by the code during calls, to sort out and settle.",
                            fr: "Les signalements levés par l'agent et par le code pendant les appels, à trier et à régler.",
                        })}
                    </p>
                </div>
                <PageATrier />
            </div>
        </div>
    );
}
