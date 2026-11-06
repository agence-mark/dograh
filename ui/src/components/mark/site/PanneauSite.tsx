"use client";

/**
 * [.mark] U10 / S2 puis V5 : l'entrée « widget du site » de l'écran « Intégrer » de Dograh (EmbedDialog).
 *
 * Le formulaire à plat d'avant est remplacé par l'éditeur de la maquette (`EditeurWidget`) : ici restent le choix du
 * canal de l'agent (téléphone ou site, `PUT /organizations/agents-site/{id}/canal`) et le bouton qui ouvre l'éditeur.
 * La page « Site » d'un agent (`PageSiteAgent`) ouvre le MÊME éditeur : une seule source, aucun second configurateur.
 */
import { Loader2 } from "lucide-react";
import { useCallback, useEffect, useState } from "react";

import { lireLEmplacementApiV1OrganizationsAgentsSiteWorkflowIdGet, reglerLeCanalApiV1OrganizationsAgentsSiteWorkflowIdCanalPut } from "@/client/sdk.gen";
import type { EmplacementLu } from "@/client/types.gen";
import { useLangue } from "@/components/mark/langue/langue";
import { notifier } from "@/components/mark/notifications";
import { Button } from "@/components/ui/button";
import { Label } from "@/components/ui/label";
import { Switch } from "@/components/ui/switch";
import { useAuth } from "@/lib/auth";

import { EditeurWidget } from "./EditeurWidget";

export function PanneauSite({ workflowId }: { workflowId: number }) {
    const { t } = useLangue();
    const { user, loading: authLoading } = useAuth();
    const [emplacement, setEmplacement] = useState<EmplacementLu | null>(null);
    const [occupe, setOccupe] = useState(false);
    const [ouvert, setOuvert] = useState(false);

    const charger = useCallback(async () => {
        const e = await lireLEmplacementApiV1OrganizationsAgentsSiteWorkflowIdGet({ path: { workflow_id: workflowId } });
        setEmplacement(e.data ?? null);
    }, [workflowId]);

    useEffect(() => {
        if (authLoading || !user) return;
        void charger();
    }, [authLoading, user, charger]);

    if (!emplacement) return <Loader2 className="h-4 w-4 animate-spin" aria-label="loading" />;
    const estSite = emplacement.canal === "site";

    const changerCanal = async (valeur: boolean) => {
        setOccupe(true);
        try {
            const res = await reglerLeCanalApiV1OrganizationsAgentsSiteWorkflowIdCanalPut({ path: { workflow_id: workflowId }, body: { canal: valeur ? "site" : "telephone" } });
            if (res.error) {
                notifier.echec({ fr: "Canal non enregistré. Un numéro, un outil de transfert ou un widget actif l'en empêche peut-être.", en: "Channel not saved. A phone number, a transfer tool or an active widget may prevent it." }, { erreur: res.error });
                return;
            }
            notifier.succes({ fr: "Canal enregistré.", en: "Channel saved." });
            await charger();
        } finally {
            setOccupe(false);
        }
    };

    return (
        <section className="grid gap-4" data-testid="panneau-site">
            <div className="flex items-center justify-between gap-4">
                <Label htmlFor="canal-site" className="cursor-pointer">
                    {t({ en: "Site agent (widget on a website)", fr: "Agent de site (widget sur un site internet)" })}
                </Label>
                <Switch id="canal-site" checked={estSite} disabled={occupe} onCheckedChange={(v) => void changerCanal(v)} />
            </div>
            {estSite && (
                <div>
                    <Button type="button" size="sm" onClick={() => setOuvert(true)} data-testid="configurer-widget">
                        {t({ en: "Configure the widget", fr: "Configurer le widget" })}
                    </Button>
                </div>
            )}
            {ouvert && (
                <EditeurWidget
                    workflowId={workflowId}
                    onFermer={() => {
                        setOuvert(false);
                        void charger();
                    }}
                />
            )}
        </section>
    );
}
