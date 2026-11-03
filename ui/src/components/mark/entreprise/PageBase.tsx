"use client";

/**
 * [.mark] U2, l'écran « Base et automatisations » (E52) : champ pour champ les thèmes « Données du client » (la base :
 * créer, rattacher, mettre à niveau, tester, détacher ; conservation par table ; conservation des appels ; cases des
 * listes de valeurs) et « Après l'appel » (synthèse, serveur de mail, récapitulatif, webhook sur mesure, tâche de
 * nuit) de « Réglages de l'organisation » d'avant. Mêmes routes, mêmes enregistrements.
 *
 * [.mark] K4 : comme la maquette (`ecrans-organisation.tsx`, EcranBase), UNE page sans sous-onglets : le titre, puis deux
 * intertitres en petites capitales (« Données du client », « Après l'appel ») ; chaque thème est posé à plat, sans son
 * titre (l'intertitre le porte).
 */
import { useCallback, useState } from "react";

import { FormeMaquette } from "../ecran/forme-maquette";
import { useLangue } from "../langue/langue";
import type { ThemeOrganisation } from "../parametres-organisation/references/cas-organisation";
import { ThemeApresAppel, useApresAppel } from "../parametres-organisation/ThemeApresAppel";
import { ThemeDonneesClient, useBaseClient } from "../parametres-organisation/ThemeDonneesClient";
import { GroupePage as Groupe } from "../studio/groupe-page";
import { PageStudio } from "../studio/shell-studio";
import { TitrePage } from "../studio/titre-page";

type Etat = { modifie: boolean; enErreur: boolean };

export function PageBase() {
    const { t } = useLangue();
    const base = useBaseClient();
    const apresAppel = useApresAppel();
    const [, setEtats] = useState<Partial<Record<ThemeOrganisation, Etat>>>({});
    const signaler = useCallback((id: ThemeOrganisation, modifie: boolean, enErreur: boolean) => {
        setEtats((avant) =>
            avant[id]?.modifie === modifie && avant[id]?.enErreur === enErreur ? avant : { ...avant, [id]: { modifie, enErreur } },
        );
    }, []);
    const commun = { ouvert: true, onBasculer: () => undefined, ouvrir: () => undefined, signaler, plat: true, sansTitre: true };

    return (
        <PageStudio>
            <FormeMaquette>
            <TitrePage
                titre={t({ en: "Data and automations", fr: "Base et automatisations" })}
                info={t({
                    en: "The client's own database (source of its establishments, team and sentences, where every call is written) and what Dograh does once the call is over.",
                    fr: "La base propre du client (source de ses établissements, de son équipe et de ses phrases, où chaque appel s'écrit) et ce que Dograh fait une fois l'appel fini.",
                })}
            />
            <section id="base" data-theme-groupe="donnees">
                <Groupe titre={t({ en: "Client data", fr: "Données du client" })} />
                <ThemeDonneesClient {...commun} base={base} />
            </section>
            <section id="apres-appel" data-theme-groupe="apres-appel">
                <Groupe
                    titre={t({ en: "After the call", fr: "Après l'appel" })}
                    info={t({
                        en: "What Dograh does once the call is over, for the agents that switch it on in « Call data »: write it in the client's database, summarise it, mail the request, run the modules.",
                        fr: "Ce que fait Dograh une fois l'appel fini, pour les agents qui l'allument dans « Données de l'appel » : l'écrire dans la base du client, le résumer, envoyer la demande par mail, lancer les modules.",
                    })}
                />
                <ThemeApresAppel {...commun} apresAppel={apresAppel} />
            </section>
            </FormeMaquette>
        </PageStudio>
    );
}
