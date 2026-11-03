"use client";

/**
 * [.mark] K1b : « Qualité » (décision d'Evan, 04/11, comme la maquette). Deux onglets : le rapport quotidien des appels
 * (l'écran de rapports d'avant), et les alertes (l'ancienne entrée « Alertes » du menu). `?onglet=alertes` ouvre les alertes.
 */
import ReportsPage from "@/app/reports/page";
import { useLangue } from "@/components/mark/langue/langue";
import { OngletsPage } from "@/components/mark/studio/onglets-page";
import { PageStudio, TitrePage } from "@/components/mark/studio/shell-studio";
import { OngletAlertes } from "@/components/mark/tri/OngletAlertes";

export function PageQualite() {
    const { t } = useLangue();
    return (
        <PageStudio>
            <TitrePage titre={t({ en: "Quality", fr: "Qualité" })} />
            <OngletsPage
                onglets={[
                    { id: "rapport", titre: t({ en: "Daily report", fr: "Rapport quotidien" }), contenu: <ReportsPage /> },
                    { id: "alertes", titre: t({ en: "Alerts", fr: "Alertes" }), contenu: <OngletAlertes /> },
                ]}
            />
        </PageStudio>
    );
}
