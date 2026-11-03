"use client";

/**
 * [.mark] U2 bis, l'écran « Entreprise » (E56) : les données du client, que l'agent lit à chaque appel et que le
 * client tient à jour depuis son portail (mêmes enregistrements, mêmes routes : on déplace l'écran, pas le modèle).
 *
 * Six sous-onglets, qui sont les thèmes de « Réglages de l'organisation » d'avant : Établissements, Équipe et
 * routage, Rendez-vous, Objets, Vérification de l'appelant, Écoute et sons. Chaque thème garde son composant, ses
 * champs et son enregistrement ; il est posé à plat dans son onglet (`plat`).
 */
import { useCallback, useState } from "react";

import { FormeMaquette } from "../ecran/forme-maquette";
import { useLangue } from "../langue/langue";
import { FournisseurEtablissements } from "../parametres-organisation/etablissements-partages";
import { usePreferencesOrganisation } from "../parametres-organisation/preferences";
import type { ThemeOrganisation } from "../parametres-organisation/references/cas-organisation";
import { useBaseClient } from "../parametres-organisation/ThemeDonneesClient";
import { ThemeEcouteOrganisation } from "../parametres-organisation/ThemesOrganisation";
import { ThemeVerification } from "../parametres-organisation/ThemeVerification";
import { useAnnonceOuverture } from "../SectionAnnonceOuverture";
import { OngletsPage } from "../studio/onglets-page";
import { PageStudio } from "../studio/shell-studio";
import { TitrePage } from "../studio/titre-page";
import { OngletEquipe } from "./OngletEquipe";
import { OngletEtablissements } from "./OngletEtablissements";
import { OngletRendezVous } from "./OngletRendezVous";
import { SonsEtCacheVoix } from "./SonsEtCacheVoix";
import { ThemeObjets } from "./ThemeObjets";

type Etat = { modifie: boolean; enErreur: boolean };

export const ONGLETS_ENTREPRISE = ["etablissements", "equipe", "rendez-vous", "objets", "verification", "ecoute"] as const;

export function PageEntreprise() {
    const { t } = useLangue();
    const preferences = usePreferencesOrganisation();
    const annonce = useAnnonceOuverture();
    const base = useBaseClient();
    const [etats, setEtats] = useState<Partial<Record<ThemeOrganisation, Etat>>>({});

    const signaler = useCallback((id: ThemeOrganisation, modifie: boolean, enErreur: boolean) => {
        setEtats((avant) =>
            avant[id]?.modifie === modifie && avant[id]?.enErreur === enErreur ? avant : { ...avant, [id]: { modifie, enErreur } },
        );
    }, []);
    // Un thème posé à plat ne se replie pas : il est toujours « ouvert ».
    const commun = { ouvert: true, onBasculer: () => undefined, ouvrir: () => undefined, signaler, plat: true };
    const etat = (id: ThemeOrganisation) => etats[id] ?? { modifie: false, enErreur: false };
    const baseRattachee = base.etat ? Boolean(base.etat.nom_base) : null;

    return (
        <PageStudio>
            <FournisseurEtablissements>
            <FormeMaquette>
            <TitrePage
                titre={t({ en: "Company", fr: "Entreprise" })}
                info={t({
                    en: "What the agents know about the company, read at every call: places, team, appointments, objects, caller verification, vocabulary and sounds. The client keeps it up to date from the portal: each fiche says who changed it last and from where.",
                    fr: "Ce que les agents savent de l'entreprise, lu à chaque appel : lieux, équipe, rendez-vous, variables, vérification de l'appelant, vocabulaire et sons. Le client la tient à jour depuis son portail : chaque fiche dit qui l'a modifiée en dernier et d'où.",
                })}
            />
            <div className="-mt-2">
            <OngletsPage
                espacement="space-y-10"
                onglets={[
                    {
                        id: "etablissements",
                        titre: t({ en: "Establishments", fr: "Établissements" }),
                        ...etat("etablissement"),
                        contenu: <OngletEtablissements signaler={signaler} preferences={preferences} annonce={annonce} />,
                    },
                    {
                        id: "equipe",
                        titre: t({ en: "Team and routing", fr: "Équipe et routage" }),
                        contenu: <OngletEquipe baseRattachee={baseRattachee} />,
                    },
                    {
                        id: "rendez-vous",
                        titre: t({ en: "Appointments", fr: "Rendez-vous" }),
                        contenu: <OngletRendezVous baseRattachee={baseRattachee} />,
                    },
                    { id: "objets", titre: t({ en: "Variables", fr: "Variables" }), contenu: <ThemeObjets /> },
                    {
                        id: "verification",
                        titre: t({ en: "Caller verification", fr: "Vérification de l'appelant" }),
                        ...etat("verification"),
                        contenu: <ThemeVerification {...commun} sansTitre />,
                    },
                    {
                        id: "ecoute",
                        titre: t({ en: "Listening and sounds", fr: "Écoute et sons" }),
                        ...etat("ecoute"),
                        contenu: <ThemeEcouteOrganisation {...commun} sansTitre sons={<SonsEtCacheVoix />} />,
                    },
                ]}
            />
            </div>
            </FormeMaquette>
            </FournisseurEtablissements>
        </PageStudio>
    );
}
