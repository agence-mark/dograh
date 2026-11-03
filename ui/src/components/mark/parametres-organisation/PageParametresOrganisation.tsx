"use client";

/**
 * [.mark] « Réglages de l'organisation » (chantier reorganisation-ecran-reglages, puis U2 / U2 bis du builder
 * partie 2, D8) : trois thèmes seulement, Général, Intégrations, Développeurs.
 *
 * Les sept autres ont changé de place sans changer de fonction : Établissements, Équipe et routage, Rendez-vous,
 * Vérification de l'appelant et Écoute sont dans l'écran Entreprise (`entreprise/PageEntreprise.tsx`), Données du
 * client et Après l'appel dans l'écran Base et automatisations (`entreprise/PageBase.tsx`). Les anciennes ancres
 * (`/settings#etablissement`...) y mènent (`entreprise/anciennes-ancres.ts`). Le test d'inventaire garde chaque
 * réglage : aucun ne disparaît.
 *
 * Appelée par `app/settings/page.tsx`.
 */
import { useCallback, useEffect, useState } from "react";

import { NavigationThemes } from "../ecran/NavigationThemes";
import { useThemesOuverts } from "../ecran/useThemesOuverts";
import { destinationDeLAncre } from "../entreprise/anciennes-ancres";
import { useLangue } from "../langue/langue";
import { usePreferencesOrganisation } from "./preferences";
import type { ThemeOrganisation } from "./references/cas-organisation";
import { useApresAppel } from "./ThemeApresAppel";
import {
    ThemeDeveloppeurs,
    ThemeIntegrations,
    ThemeOrganisationGenerale,
    THEMES_ORGANISATION,
} from "./ThemesOrganisation";

type Etat = { modifie: boolean; enErreur: boolean };

/** Les thèmes qui restent dans les réglages de l'organisation (D8). */
export const THEMES_RESTANTS: ThemeOrganisation[] = ["organisation", "integrations", "developpeurs"];

export const PageParametresOrganisation = () => {
    const { t } = useLangue();
    const themes = useThemesOuverts();
    const preferences = usePreferencesOrganisation();
    const apresAppel = useApresAppel();
    const [etats, setEtats] = useState<Partial<Record<ThemeOrganisation, Etat>>>({});

    // Une ancienne adresse `/settings#etablissement` mène à l'écran où le thème est allé.
    useEffect(() => {
        const ailleurs = destinationDeLAncre(window.location.hash.replace(/^#/, ""));
        if (ailleurs) window.location.replace(ailleurs);
    }, []);

    const signaler = useCallback((id: ThemeOrganisation, modifie: boolean, enErreur: boolean) => {
        setEtats((avant) =>
            avant[id]?.modifie === modifie && avant[id]?.enErreur === enErreur ? avant : { ...avant, [id]: { modifie, enErreur } },
        );
    }, []);

    const commun = (id: ThemeOrganisation) => ({
        ouvert: themes.estOuvert(id),
        onBasculer: () => themes.basculer(id),
        ouvrir: () => themes.ouvrir(id),
        signaler,
    });

    return (
        <div className="mx-auto flex max-w-5xl gap-8 px-4 py-12">
            <div className="min-w-0 flex-1 space-y-4">
                <div>
                    <h1 className="text-2xl font-bold">{t({ en: "Platform Settings", fr: "Paramètres de la plateforme" })}</h1>
                    <p className="text-muted-foreground">
                        {t({
                            en: "Manage your platform configuration and integrations.",
                            fr: "Gérer la configuration et les intégrations de la plateforme.",
                        })}
                    </p>
                </div>

                <ThemeOrganisationGenerale
                    {...commun("organisation")}
                    preferences={preferences}
                    adressesMark={apresAppel.ecran?.adresses.installation ?? []}
                />
                <ThemeIntegrations {...commun("integrations")} preferences={preferences} />
                <ThemeDeveloppeurs {...commun("developpeurs")} />
                {/* No "Call events" card: its only destination is the BigQuery
                    export, neutralised by decision of Evan (25/09/2026, E3) and
                    refused by the server whatever a configuration asks. */}
            </div>

            <NavigationThemes
                actif={null}
                onChoisir={themes.choisir}
                entrees={THEMES_ORGANISATION.filter((theme) => THEMES_RESTANTS.includes(theme.id)).map((theme) => ({
                    ...theme,
                    modifie: etats[theme.id]?.modifie ?? false,
                    enErreur: etats[theme.id]?.enErreur ?? false,
                }))}
            />
        </div>
    );
};
