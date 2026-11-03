"use client";

/**
 * [.mark] U3 quater (E65) : l'onglet « Site » d'un agent dont le canal est le site. Il RÉSUME le module (site, chemins,
 * script détecté, état) et « Configurer le module » ouvre le MÊME éditeur que l'écran « Intégrer » (`PanneauSite`), sur
 * les mêmes routes (`/organizations/sites`, `/organizations/agents-site/{id}/*`), donc sur la même donnée que le portail.
 * Aucun second configurateur.
 */
import { useCallback, useEffect, useState } from "react";

import { lireLEmplacementApiV1OrganizationsAgentsSiteWorkflowIdGet } from "@/client/sdk.gen";
import type { EmplacementLu } from "@/client/types.gen";
import { Button } from "@/components/ui/button";
import { Dialog, DialogContent, DialogDescription, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { useAuth } from "@/lib/auth";

import { useLangue } from "../langue/langue";
import { PanneauSite } from "./PanneauSite";

export function PageSiteAgent({ agentId }: { agentId: number }) {
    const { t } = useLangue();
    const { user, loading: authLoading } = useAuth();
    const [emplacement, setEmplacement] = useState<EmplacementLu | null>(null);
    const [refus, setRefus] = useState(false);
    const [ouvert, setOuvert] = useState(false);

    const lire = useCallback(async () => {
        try {
            const reponse = await lireLEmplacementApiV1OrganizationsAgentsSiteWorkflowIdGet({ path: { workflow_id: agentId } });
            setRefus(!reponse.data);
            setEmplacement(reponse.data ?? null);
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
    if (!emplacement) return <p className="p-6 text-sm text-muted-foreground">{t({ en: "Loading...", fr: "Chargement..." })}</p>;
    if (emplacement.canal !== "site") {
        return (
            <p className="p-6 text-sm text-muted-foreground" data-testid="site-pas-le-canal">
                {t({ en: "This agent answers on the phone: the Site tab applies to a site agent.", fr: "Cet agent répond au téléphone : l'onglet Site concerne un agent de site." })}
            </p>
        );
    }
    const chemins = emplacement.chemins ?? [];
    return (
        <div className="mx-auto max-w-3xl space-y-4 p-6" data-onglet-site>
            <dl className="grid grid-cols-[160px_1fr] gap-x-4 gap-y-2 text-sm">
                <dt className="text-muted-foreground">{t({ en: "Site", fr: "Site" })}</dt>
                <dd data-site-cle>{emplacement.site_cle ?? t({ en: "No site chosen yet", fr: "Aucun site choisi" })}</dd>
                <dt className="text-muted-foreground">{t({ en: "Pages", fr: "Pages" })}</dt>
                <dd data-chemins>{chemins.length > 0 ? chemins.join(", ") : "—"}</dd>
                <dt className="text-muted-foreground">{t({ en: "Script", fr: "Script" })}</dt>
                <dd data-script>
                    {emplacement.dernier_chargement
                        ? `${t({ en: "Detected, last loaded", fr: "Détecté, dernier chargement" })} ${emplacement.dernier_chargement}`
                        : t({ en: "Not detected yet", fr: "Pas encore détecté" })}
                </dd>
                <dt className="text-muted-foreground">{t({ en: "State", fr: "État" })}</dt>
                <dd data-etat>{emplacement.widget_actif ? t({ en: "Active", fr: "Actif" }) : t({ en: "Off", fr: "Éteint" })}</dd>
            </dl>
            <Button onClick={() => setOuvert(true)} data-testid="configurer-module">
                {t({ en: "Configure the module", fr: "Configurer le module" })}
            </Button>
            {ouvert && (
                <Dialog
                    open
                    onOpenChange={(o) => {
                        if (!o) {
                            setOuvert(false);
                            void lire();
                        }
                    }}
                >
                    <DialogContent className="max-h-[90vh] overflow-y-auto sm:max-w-3xl">
                        <DialogHeader>
                            <DialogTitle>{t({ en: "Site module", fr: "Module du site" })}</DialogTitle>
                            <DialogDescription>
                                {t({ en: "The same editor as the client portal: one source, the client and .mark set the same module.", fr: "Le même éditeur que le portail : une seule source, le client et .mark règlent le même module." })}
                            </DialogDescription>
                        </DialogHeader>
                        <PanneauSite workflowId={agentId} />
                    </DialogContent>
                </Dialog>
            )}
        </div>
    );
}
