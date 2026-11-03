"use client";

/**
 * [.mark] U2, l'écran « Base et automatisations » (E52) : champ pour champ les thèmes « Données du client » (la base :
 * créer, rattacher, mettre à niveau, tester, détacher ; conservation par table ; conservation des appels ; cases des
 * listes de valeurs) et « Après l'appel » (synthèse, serveur de mail, récapitulatif, webhook sur mesure, tâche de
 * nuit) de « Réglages de l'organisation » d'avant. Mêmes routes, mêmes enregistrements ; chaque thème est posé à plat
 * dans son sous-onglet.
 */
import { useCallback, useState } from "react";

import { useLangue } from "../langue/langue";
import type { ThemeOrganisation } from "../parametres-organisation/references/cas-organisation";
import { ThemeApresAppel, useApresAppel } from "../parametres-organisation/ThemeApresAppel";
import { ThemeDonneesClient, useBaseClient } from "../parametres-organisation/ThemeDonneesClient";
import { OngletsPage } from "../studio/onglets-page";
import { TitrePage } from "../studio/titre-page";

type Etat = { modifie: boolean; enErreur: boolean };

export const ONGLETS_BASE = ["base", "apres-appel"] as const;

export function PageBase() {
    const { t } = useLangue();
    const base = useBaseClient();
    const apresAppel = useApresAppel();
    const [etats, setEtats] = useState<Partial<Record<ThemeOrganisation, Etat>>>({});
    const signaler = useCallback((id: ThemeOrganisation, modifie: boolean, enErreur: boolean) => {
        setEtats((avant) =>
            avant[id]?.modifie === modifie && avant[id]?.enErreur === enErreur ? avant : { ...avant, [id]: { modifie, enErreur } },
        );
    }, []);
    const commun = { ouvert: true, onBasculer: () => undefined, ouvrir: () => undefined, signaler, plat: true };
    const etat = (id: ThemeOrganisation) => etats[id] ?? { modifie: false, enErreur: false };

    return (
        <div className="mx-auto w-full max-w-5xl space-y-6 p-6">
            <TitrePage
                titre={t({ en: "Data and automations", fr: "Base et automatisations" })}
                info={t({
                    en: "The client's database, what is kept of the calls, and what runs after each call: summary, mail, recap, custom webhook and the night task.",
                    fr: "La base du client, ce qui est gardé des appels, et ce qui s'exécute après chaque appel : synthèse, mail, récapitulatif, webhook sur mesure et tâche de nuit.",
                })}
            />
            <OngletsPage
                onglets={[
                    {
                        id: "base",
                        titre: t({ en: "Client database", fr: "Base du client" }),
                        ...etat("donnees"),
                        contenu: <ThemeDonneesClient {...commun} base={base} />,
                    },
                    {
                        id: "apres-appel",
                        titre: t({ en: "After the call", fr: "Après l'appel" }),
                        ...etat("apres-appel"),
                        contenu: <ThemeApresAppel {...commun} apresAppel={apresAppel} />,
                    },
                ]}
            />
        </div>
    );
}
