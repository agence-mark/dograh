"use client";

/**
 * [.mark] Builder partie 3, SA-L3d (décision 21) : sous les outils d'une étape, une ligne par outil dont une version plus récente
 * existe (« reserver v4 · une v5 existe », « Passer à la v5 ») ; un outil déjà passé dans le brouillon se dit « dans le brouillon ».
 * Rien ne s'affiche quand tout est à jour. Lit l'agent ouvert (brouillon de la branche ouverte).
 */
import { useWorkflowOptional } from "@/app/workflow/[workflowId]/contexts/WorkflowContext";
import type { OutilDeLAgent } from "@/client/types.gen";

import { useLangue } from "../../langue/langue";
import { Info } from "../../studio/marques";
import { BoutonPasser } from "./BoutonPasser";
import { REGLE_VERSIONS_OUTIL, T } from "./textes";
import { useOutilsDeLAgent } from "./useVersionsOutils";

export function VersionsDansEtape({ outilsDeLEtape }: { outilsDeLEtape: readonly string[] }) {
    const { t } = useLangue();
    const workflow = useWorkflowOptional();
    const { outils } = useOutilsDeLAgent(workflow?.workflowId);
    if (!workflow?.workflowId || !outils) return null;
    const dans = (o: OutilDeLAgent) => outilsDeLEtape.includes(o.tool_uuid);
    const enRetard = outils.filter((o) => dans(o) && o.epinglee < o.courante);
    if (enRetard.length === 0) return null;
    return (
        <div className="space-y-1.5 pt-2" data-versions-etape>
            {enRetard.map((o) => (
                <p key={o.tool_uuid} className="flex flex-wrap items-center gap-x-2 gap-y-1 text-xs text-muted-foreground">
                    <span>
                        <span className="font-mono">
                            {o.nom} v{o.epinglee}
                        </span>{" "}
                        · {t(T.uneExiste(o.courante))}
                    </span>
                    <Info>{t(REGLE_VERSIONS_OUTIL)}</Info>
                    <BoutonPasser
                        cible={{
                            toolUuid: o.tool_uuid,
                            outil: o.nom,
                            workflowId: workflow.workflowId as number,
                            agent: "",
                            branche: "",
                            suivreLEnTete: true,
                            de: o.epinglee,
                            vers: o.courante,
                        }}
                    />
                </p>
            ))}
        </div>
    );
}
