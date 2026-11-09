"use client";

/**
 * [.mark] Clôture, SA-3 : ce qu'on dit quand un agent ne se charge pas. Si l'agent existe dans un autre espace que celui de
 * l'onglet (et que le compte ouvre cet espace), on le dit avec un lien qui y mène : « cet agent est dans l'espace … », au lieu
 * d'un « introuvable » qui laisse croire à une panne. Sinon la phrase d'erreur de la page, inchangée.
 */
import { type ReactNode, useEffect, useState } from "react";

import { espaceDUnAgentApiV1EspacesAgentWorkflowIdGet } from "@/client/sdk.gen";
import { useLangue } from "@/components/mark/langue/langue";
import { Button } from "@/components/ui/button";
import { useAuth } from "@/lib/auth";
import { retenirEspace } from "@/lib/espaceCourant";

type Lieu = { id: number; nom: string; espace: "labo" | "client" };

export function AgentIntrouvable({ agentId, children }: { agentId: number; /** La phrase d'erreur de la page, gardée quand l'agent n'est dans aucun espace ouvert. */ children: ReactNode }) {
    const { user, loading } = useAuth();
    const { t } = useLangue();
    const [lieu, setLieu] = useState<Lieu | null>(null);

    useEffect(() => {
        if (loading || !user || !Number.isFinite(agentId)) return;
        let annule = false;
        (async () => {
            try {
                const r = await espaceDUnAgentApiV1EspacesAgentWorkflowIdGet({ path: { workflow_id: agentId } });
                if (!annule && r.data) setLieu({ id: r.data.id, nom: r.data.nom, espace: r.data.espace as Lieu["espace"] });
            } catch {
                /* la phrase d'erreur de la page reste */
            }
        })();
        return () => {
            annule = true;
        };
    }, [agentId, loading, user]);

    if (!lieu) return <div className="text-lg text-destructive">{children}</div>;
    const ouvrir = () => {
        retenirEspace(lieu.espace === "labo" ? "/labo" : `/clients/${lieu.id}`);
        // Recharge la page : toutes les requêtes repartent avec l'espace retenu.
        window.location.assign(window.location.pathname + window.location.search);
    };
    return (
        <div role="status" className="flex flex-col items-center gap-3 text-center">
            <p className="text-lg font-semibold">
                {lieu.espace === "labo"
                    ? t({ en: "This agent is in the Lab space.", fr: "Cet agent est dans l'espace du Labo." })
                    : t({ en: `This agent is in the space « ${lieu.nom} ».`, fr: `Cet agent est dans l'espace « ${lieu.nom} ».` })}
            </p>
            <Button variant="outline" onClick={ouvrir}>
                {t({ en: "Open it in that space", fr: "L'ouvrir dans cet espace" })}
            </Button>
        </div>
    );
}
