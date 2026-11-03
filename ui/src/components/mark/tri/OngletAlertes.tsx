"use client";

/**
 * [.mark] K1b : les alertes, onglet de « Qualité » (décision d'Evan, 04/11, comme la maquette : tout ce qui mesure la
 * qualité des appels est au même endroit). Les problèmes rencontrés par les appels des clients, dans l'ordre où ils sont
 * arrivés ; l'explication est dans le « ! » du titre.
 */
import { useLangue } from "@/components/mark/langue/langue";
import { Info } from "@/components/mark/studio/marques";
import { TitreTableau } from "@/components/mark/studio/tableau";
import { PageAlertes } from "@/components/mark/tri/PageAlertes";
import { Skeleton } from "@/components/ui/skeleton";
import { useAuth } from "@/lib/auth";

export function OngletAlertes() {
    const { t } = useLangue();
    const { user, loading } = useAuth();

    if (loading || !user) return <Skeleton className="h-64 w-full max-w-3xl" />;

    return (
        <div data-testid="page-alertes-menu" className="space-y-4">
            <TitreTableau
                titre={t({ en: "Alerts", fr: "Alertes" })}
                info={
                    <Info>
                        {t({
                            en: "The problems met by your customers' calls: call ended in error, tool failure, model outage, transfer failed.",
                            fr: "Les problèmes rencontrés par les appels de vos clients : appel terminé en erreur, outil en échec, panne du modèle, transfert échoué.",
                        })}
                    </Info>
                }
            />
            <PageAlertes />
        </div>
    );
}
