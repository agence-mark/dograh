"use client";

/**
 * [.mark] Réglages du Labo (K1) : la page de la maquette (`app/labo/reglages`), un titre, des onglets. Les onglets des
 * trois cerveaux de l'atelier (Builder IA, Appelant simulé, Juge : `CerveauxReglages`, K6) puis Sources, Équipe et rôles,
 * Organisation, et Affichage (langue et thème, sortis de la barre latérale, forme provisoire E-K1-1).
 */
import { EquipeEtRoles } from "@/components/mark/equipe/PageEquipe";
import { useLangue } from "@/components/mark/langue/langue";
import { OngletAppelantOuJuge, OngletBuilderIA } from "@/components/mark/reglages/CerveauxReglages";
import { PanneauAffichage } from "@/components/mark/reglages/PanneauAffichage";
import { ReglagesOrganisation } from "@/components/mark/reglages/ReglagesOrganisation";
import { OngletSources } from "@/components/mark/sources/OngletSources";
import { allerALOnglet, OngletsPage } from "@/components/mark/studio/onglets-page";
import { PageStudio } from "@/components/mark/studio/shell-studio";
import { TitrePage } from "@/components/mark/studio/titre-page";

export function PageReglages({ defaut = "builder" }: { defaut?: "builder" | "appelant" | "juge" | "equipe" | "organisation" | "affichage" | "sources" }) {
    const { t } = useLangue();
    return (
        <PageStudio>
            <TitrePage
                titre={t({ en: "Settings", fr: "Réglages" })}
                info={t({
                    en: "The team of the workshop and the Lab's organization settings. Every change is versioned and written to the journal.",
                    fr: "L'équipe de l'atelier et les réglages de l'organisation du Labo. Chaque changement est versionné et journalisé.",
                })}
            />
            <OngletsPage
                espacement="space-y-10"
                defaut={defaut}
                onglets={[
                    { id: "builder", titre: "Builder IA", contenu: <OngletBuilderIA aller={() => allerALOnglet("sources")} /> },
                    { id: "appelant", titre: t({ en: "Simulated caller", fr: "Appelant simulé" }), contenu: <OngletAppelantOuJuge role="appelant" aller={() => allerALOnglet("sources")} /> },
                    { id: "juge", titre: t({ en: "Judge", fr: "Juge" }), contenu: <OngletAppelantOuJuge role="juge" aller={() => allerALOnglet("sources")} /> },
                    { id: "sources", titre: t({ en: "Sources", fr: "Sources" }), contenu: <OngletSources /> },
                    { id: "equipe", titre: t({ en: "Team and roles", fr: "Équipe et rôles" }), contenu: <EquipeEtRoles /> },
                    { id: "organisation", titre: t({ en: "Organization", fr: "Organisation" }), contenu: <ReglagesOrganisation /> },
                    { id: "affichage", titre: t({ en: "Display", fr: "Affichage" }), contenu: <PanneauAffichage /> },
                ]}
            />
        </PageStudio>
    );
}
