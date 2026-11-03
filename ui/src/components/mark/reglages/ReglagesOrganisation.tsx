"use client";

/**
 * [.mark] « Réglages de l'organisation » dans la forme de la maquette (`EcranReglagesOrganisation`, K1) : un menu de
 * thèmes à gauche (Général, Intégrations, Développeurs), le thème choisi à droite, posé à plat. Mêmes thèmes, mêmes
 * routes, mêmes enregistrements que `PageParametresOrganisation` ; seule la forme change. La section se lit et s'écrit
 * dans l'adresse (`?section=`).
 */
import { useCallback, useEffect, useState } from "react";

import APIKeysPage from "@/app/api-keys/page";
import { Intertitre } from "@/components/mark/ecran/Intertitre";
import { useLangue } from "@/components/mark/langue/langue";
import { usePreferencesOrganisation } from "@/components/mark/parametres-organisation/preferences";
import type { ThemeOrganisation } from "@/components/mark/parametres-organisation/references/cas-organisation";
import { useApresAppel } from "@/components/mark/parametres-organisation/ThemeApresAppel";
import {
    ThemeDeveloppeurs,
    ThemeIntegrations,
    ThemeOrganisationGenerale,
} from "@/components/mark/parametres-organisation/ThemesOrganisation";
import { PageStudio } from "@/components/mark/studio/shell-studio";
import { TitrePage } from "@/components/mark/studio/titre-page";

type Section = "organisation" | "integrations" | "developpeurs";
type Etat = { modifie: boolean; enErreur: boolean };

const lireSection = (): Section => {
    try {
        const v = new URLSearchParams(window.location.search).get("section");
        return v === "integrations" || v === "developpeurs" ? v : "organisation";
    } catch {
        return "organisation";
    }
};

export function ReglagesOrganisation() {
    const { t } = useLangue();
    const preferences = usePreferencesOrganisation();
    const apresAppel = useApresAppel();
    const [section, setSection] = useState<Section>("organisation");
    const [, setEtats] = useState<Partial<Record<ThemeOrganisation, Etat>>>({});
    useEffect(() => setSection(lireSection()), []);

    const choisir = (s: Section) => {
        setSection(s);
        try {
            const adresse = new URL(window.location.href);
            adresse.searchParams.set("section", s);
            window.history.replaceState(window.history.state, "", adresse);
        } catch {
            /* la section reste choisie à l'écran */
        }
    };

    const signaler = useCallback((id: ThemeOrganisation, modifie: boolean, enErreur: boolean) => {
        setEtats((avant) =>
            avant[id]?.modifie === modifie && avant[id]?.enErreur === enErreur ? avant : { ...avant, [id]: { modifie, enErreur } },
        );
    }, []);
    const commun = { ouvert: true, onBasculer: () => undefined, ouvrir: () => undefined, signaler, plat: true };

    const sections: { id: Section; titre: string }[] = [
        { id: "organisation", titre: t({ en: "General", fr: "Général" }) },
        { id: "integrations", titre: t({ en: "Integrations", fr: "Intégrations" }) },
        { id: "developpeurs", titre: t({ en: "Developers", fr: "Développeurs" }) },
    ];

    return (
        <div className="grid gap-6 lg:grid-cols-[220px_1fr]">
            <aside className="space-y-0.5">
                {sections.map((s) => (
                    <button
                        key={s.id}
                        type="button"
                        onClick={() => choisir(s.id)}
                        className={`w-full rounded-lg px-3 py-2 text-left text-sm ${
                            section === s.id ? "bg-accent font-medium text-accent-foreground" : "hover:bg-muted hover:font-medium"
                        }`}
                    >
                        {s.titre}
                    </button>
                ))}
            </aside>
            <div className="min-w-0">
                {section === "organisation" && (
                    <ThemeOrganisationGenerale
                        {...commun}
                        preferences={preferences}
                        adressesMark={apresAppel.ecran?.adresses.installation ?? []}
                    />
                )}
                {section === "integrations" && <ThemeIntegrations {...commun} preferences={preferences} />}
                {section === "developpeurs" && (
                    <div className="space-y-8">
                        <ThemeDeveloppeurs {...commun} />
                        <Intertitre id="developpeurs-cles" titre={{ en: "Dograh API keys", fr: "Clés d'API de Dograh" }}>
                            <APIKeysPage />
                        </Intertitre>
                    </div>
                )}
            </div>
        </div>
    );
}

/** `/clients/<org>/reglages` : la page « Réglages de l'organisation » d'un client. */
export function PageReglagesOrganisation() {
    const { t } = useLangue();
    return (
        <PageStudio>
            <TitrePage
                titre={t({ en: "Organization settings", fr: "Réglages de l'organisation" })}
                info={t({
                    en: "Valid for all the agents of this organization, unless an establishment or an agent replaces them.",
                    fr: "Valables pour tous les agents de cette organisation, sauf quand un établissement ou un agent les remplace.",
                })}
            />
            <ReglagesOrganisation />
        </PageStudio>
    );
}
