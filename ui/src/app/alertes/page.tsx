"use client";

/**
 * [.mark] The « Alerts » page of the menu (passages-fiables, lot G): the problems met by the customers' calls.
 */
import { useLangue } from "@/components/mark/langue/langue";
import { PageAlertes } from "@/components/mark/tri/PageAlertes";
import { Skeleton } from "@/components/ui/skeleton";
import { useAuth } from "@/lib/auth";

export default function PageAlertesDuMenu() {
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
        <div className="container mx-auto px-4 py-8" data-testid="page-alertes-menu">
            <div className="mx-auto max-w-3xl space-y-6">
                <div>
                    <h1 className="mb-2 text-3xl font-bold">{t({ en: "Alerts", fr: "Alertes" })}</h1>
                    <p className="text-muted-foreground">
                        {t({
                            en: "The problems met by your customers' calls: call ended in error, tool failure, model outage, transfer failed.",
                            fr: "Les problèmes rencontrés par les appels de vos clients : appel terminé en erreur, outil en échec, panne du modèle, transfert échoué.",
                        })}
                    </p>
                </div>
                <PageAlertes />
            </div>
        </div>
    );
}
