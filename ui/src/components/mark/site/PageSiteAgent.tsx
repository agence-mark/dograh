"use client";

/**
 * [.mark] U3 quater (E65) : l'onglet « Site » d'un agent dont le canal est le site. Il RÉSUME le module (site, chemins,
 * script détecté, état) et « Configurer le module » ouvre le MÊME éditeur que l'écran « Intégrer » (`PanneauSite`), sur
 * les mêmes routes (`/organizations/sites`, `/organizations/agents-site/{id}/*`), donc sur la même donnée que le portail.
 * Aucun second configurateur.
 */
import { useCallback, useEffect, useState } from "react";

import { lireLEmplacementApiV1OrganizationsAgentsSiteWorkflowIdGet, listerLesSitesApiV1OrganizationsSitesGet } from "@/client/sdk.gen";
import type { EmplacementLu } from "@/client/types.gen";
import { EtatVide } from "@/components/mark/studio/etat-vide";
import { Info } from "@/components/mark/studio/marques";
import { Button } from "@/components/ui/button";
import { useAuth } from "@/lib/auth";

import { useLangue } from "../langue/langue";
import { EditeurWidget } from "./EditeurWidget";

export function PageSiteAgent({ agentId }: { agentId: number }) {
    const { t } = useLangue();
    const { user, loading: authLoading } = useAuth();
    const [emplacement, setEmplacement] = useState<EmplacementLu | null>(null);
    const [nomDuSite, setNomDuSite] = useState<string | null>(null);
    const [refus, setRefus] = useState(false);
    const [ouvert, setOuvert] = useState(false);

    const lire = useCallback(async () => {
        try {
            // Les deux lectures partent ensemble ; le nom du site est un confort : sans lui, la clé reste affichée.
            const [reponse, sites] = await Promise.all([
                lireLEmplacementApiV1OrganizationsAgentsSiteWorkflowIdGet({ path: { workflow_id: agentId } }),
                Promise.resolve()
                    .then(() => listerLesSitesApiV1OrganizationsSitesGet())
                    .catch(() => null),
            ]);
            setRefus(!reponse.data);
            setEmplacement(reponse.data ?? null);
            const site = (sites?.data ?? []).find((x) => x.id === reponse.data?.site_id);
            setNomDuSite(site ? site.nom || site.allowed_domains?.[0] || null : null);
        } catch {
            setRefus(true);
        }
    }, [agentId]);

    useEffect(() => {
        if (authLoading || !user) return;
        void lire();
    }, [authLoading, user, lire]);

    if (refus) {
        return (
            <p className="p-6 text-sm text-muted-foreground" data-testid="site-refus">
                {t({ en: "The site module cannot be read.", fr: "Le module du site est illisible." })}
            </p>
        );
    }
    if (!emplacement) return <EtatVide cas="chargement" lignes={3} />;
    if (emplacement.canal !== "site") {
        return (
            <p className="p-6 text-sm text-muted-foreground" data-testid="site-pas-le-canal">
                {t({ en: "This agent answers on the phone: the Site tab applies to a site agent.", fr: "Cet agent répond au téléphone : l'onglet Site concerne un agent de site." })}
            </p>
        );
    }
    const chemins = emplacement.chemins ?? [];
    // K3 (maquette `OngletSite`) : le titre « Le module du site » avec son « ! » et le bouton, puis des lignes nues.
    const lignes: Array<[string, string, Record<string, string>]> = [
        [t({ en: "Site", fr: "Site" }), nomDuSite ?? emplacement.site_cle ?? t({ en: "No site chosen yet", fr: "Aucun site choisi" }), { "data-site-cle": "" }],
        [t({ en: "Pages", fr: "Pages" }), chemins.length > 0 ? chemins.join(", ") : "—", { "data-chemins": "" }],
        [
            t({ en: "Script", fr: "Script" }),
            emplacement.dernier_chargement
                ? `${t({ en: "Detected, last loaded", fr: "Détecté, dernier chargement" })} ${emplacement.dernier_chargement}`
                : t({ en: "Not detected yet", fr: "Pas encore détecté" }),
            { "data-script": "" },
        ],
        [t({ en: "State", fr: "État" }), emplacement.widget_actif ? t({ en: "Active", fr: "Actif" }) : t({ en: "Off", fr: "Éteint" }), { "data-etat": "" }],
    ];
    return (
        <div className="mx-auto max-w-5xl space-y-6 px-6 py-6" data-onglet-site>
            <div>
                <div className="flex items-center gap-2">
                    <h2 className="flex flex-1 items-center gap-1.5 text-base font-semibold">
                        {t({ en: "The site module", fr: "Le module du site" })}
                        <Info>
                            {t({
                                en: "The widget placed on the client's site: look, behaviour, installation on the site and .mark settings. The client sets the same one in their portal.",
                                fr: "Le widget posé sur le site du client : apparence, comportement, pose sur le site et réglages .mark. Le client règle le même dans son portail.",
                            })}
                        </Info>
                    </h2>
                    <Button size="sm" onClick={() => setOuvert(true)} data-testid="configurer-module">
                        {t({ en: "Configure the module", fr: "Configurer le module" })}
                    </Button>
                </div>
                <div className="mt-4 divide-y border-t text-sm">
                    {lignes.map(([libelle, valeur, marque]) => (
                        <div key={libelle} className="flex items-center gap-3 py-3">
                            <span className="w-64 shrink-0 text-muted-foreground">{libelle}</span>
                            <span {...marque}>{valeur}</span>
                        </div>
                    ))}
                </div>
            </div>
            {ouvert && (
                <EditeurWidget
                    workflowId={agentId}
                    onFermer={() => {
                        setOuvert(false);
                        void lire();
                    }}
                />
            )}
        </div>
    );
}
