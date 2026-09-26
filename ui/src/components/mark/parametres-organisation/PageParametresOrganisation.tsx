"use client";

/**
 * [.mark] The Platform Settings page in 5 themes (chantier
 * reorganisation-ecran-reglages, step 5, convention § 2).
 *
 * Called from Dograh's `app/settings/page.tsx` in place of its cards (the one
 * change to their file). Their preferences card stays in its file, unused:
 * its settings are rebuilt over three themes (option B of D6), and
 * `inventaire-organisation.test.ts` fails if one is drawn nowhere.
 */
import { useCallback, useState } from "react";

import { NavigationThemes } from "../ecran/NavigationThemes";
import { useThemesOuverts } from "../ecran/useThemesOuverts";
import { useLangue } from "../langue/langue";
import { useAnnonceOuverture } from "../SectionAnnonceOuverture";
import { usePreferencesOrganisation } from "./preferences";
import type { ThemeOrganisation } from "./references/cas-organisation";
import {
    ThemeDeveloppeurs,
    ThemeEcouteOrganisation,
    ThemeEtablissementOrganisation,
    ThemeIntegrations,
    ThemeOrganisationGenerale,
    THEMES_ORGANISATION,
} from "./ThemesOrganisation";

type Etat = { modifie: boolean; enErreur: boolean };

export const PageParametresOrganisation = () => {
    const { t } = useLangue();
    const themes = useThemesOuverts();
    const preferences = usePreferencesOrganisation();
    const annonce = useAnnonceOuverture();
    const [etats, setEtats] = useState<Partial<Record<ThemeOrganisation, Etat>>>({});

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

                <ThemeOrganisationGenerale {...commun("organisation")} preferences={preferences} />
                <ThemeEtablissementOrganisation {...commun("etablissement")} preferences={preferences} annonce={annonce} />
                <ThemeEcouteOrganisation {...commun("ecoute")} />
                <ThemeIntegrations {...commun("integrations")} preferences={preferences} />
                <ThemeDeveloppeurs {...commun("developpeurs")} />
                {/* No "Call events" card: its only destination is the BigQuery
                    export, neutralised by decision of Evan (25/09/2026, E3) and
                    refused by the server whatever a configuration asks. */}
            </div>

            <NavigationThemes
                actif={null}
                onChoisir={themes.choisir}
                entrees={THEMES_ORGANISATION.map((theme) => ({
                    ...theme,
                    modifie: etats[theme.id]?.modifie ?? false,
                    enErreur: etats[theme.id]?.enErreur ?? false,
                }))}
            />
        </div>
    );
};
