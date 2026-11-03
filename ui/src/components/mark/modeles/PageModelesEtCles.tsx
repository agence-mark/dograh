"use client";

/**
 * [.mark] K1b : « Modèles et clés » (décision d'Evan, 04/11, comme la maquette). Deux onglets : les modèles de
 * l'organisation, et la bibliothèque de clés (l'ancienne entrée « Clés » du menu). `?onglet=cles` ouvre les clés.
 */
import ModelConfigurationV2 from "@/components/ModelConfigurationV2";
import { OngletCles } from "@/components/mark/cles/OngletCles";
import { useLangue } from "@/components/mark/langue/langue";
import { OngletsPage } from "@/components/mark/studio/onglets-page";
import { PageStudio, TitrePage } from "@/components/mark/studio/shell-studio";
import { SETTINGS_DOCUMENTATION_URLS } from "@/constants/documentation";

export function PageModelesEtCles() {
    const { t } = useLangue();
    return (
        <PageStudio>
            <TitrePage titre={t({ en: "Models and keys", fr: "Modèles et clés" })} />
            <OngletsPage
                onglets={[
                    {
                        id: "modeles",
                        titre: t({ en: "Models", fr: "Modèles" }),
                        contenu: <ModelConfigurationV2 docsUrl={SETTINGS_DOCUMENTATION_URLS.modelOverrides} />,
                    },
                    { id: "cles", titre: t({ en: "Keys", fr: "Clés" }), contenu: <OngletCles /> },
                ]}
            />
        </PageStudio>
    );
}
