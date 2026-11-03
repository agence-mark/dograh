"use client";

/**
 * [.mark] U6 (J3) : « Juge des vrais appels », un réglage PAR AGENT, en tête de l'onglet Réglages.
 *
 * Lu et écrit côté serveur (`GET|PUT /workflow/{id}/juge-vrais-appels`) ; éteint par défaut. Allumé, l'après-appel juge chaque vrai
 * appel de l'agent avec le juge du Labo (Réglages du Labo › Juge), sans nœud à poser. Une lecture ou un enregistrement qui échoue
 * le dit, sans inventer d'état.
 */
import { useEffect, useState } from "react";

import {
    lireLeJugeDesVraisAppelsApiV1WorkflowWorkflowIdJugeVraisAppelsGet,
    reglerLeJugeDesVraisAppelsApiV1WorkflowWorkflowIdJugeVraisAppelsPut,
} from "@/client/sdk.gen";

import { useLangue } from "../langue/langue";
import { Info } from "../studio/marques";

export function JugeDesVraisAppels({ workflowId }: { workflowId: number }) {
    const { t } = useLangue();
    const [actif, setActif] = useState<boolean | null>(null);
    const [erreur, setErreur] = useState(false);

    useEffect(() => {
        let annule = false;
        void lireLeJugeDesVraisAppelsApiV1WorkflowWorkflowIdJugeVraisAppelsGet({ path: { workflow_id: workflowId } }).then(
            (reponse) => {
                if (annule) return;
                if (reponse?.error || !reponse?.data) setErreur(true);
                else setActif(Boolean(reponse.data.actif));
            },
        );
        return () => {
            annule = true;
        };
    }, [workflowId]);

    const changer = async (valeur: boolean) => {
        setErreur(false);
        const reponse = await reglerLeJugeDesVraisAppelsApiV1WorkflowWorkflowIdJugeVraisAppelsPut({
            path: { workflow_id: workflowId },
            body: { actif: valeur },
        });
        if (reponse?.error || !reponse?.data) setErreur(true);
        else setActif(Boolean(reponse.data.actif));
    };

    const libelle = t({ en: "Judge the real calls", fr: "Juge des vrais appels" });
    return (
        <div className="flex items-center gap-2 text-sm" data-testid="juge-vrais-appels">
            <input
                type="checkbox"
                className="size-4 cursor-pointer"
                checked={actif === true}
                disabled={actif === null}
                onChange={(e) => void changer(e.target.checked)}
                aria-label={libelle}
            />
            <span>{libelle}</span>
            <Info>
                {t({
                    en: "After each real call of this agent, the judge set in the Labo settings rates it criterion by criterion, with a proof. Off by default. On Claude Code, the call waits in « To judge ».",
                    fr: "Après chaque vrai appel de cet agent, le juge réglé dans les Réglages du Labo le note critère par critère, avec une preuve. Éteint par défaut. Sur Claude Code, l'appel attend dans « À juger ».",
                })}
            </Info>
            {erreur && (
                <span data-erreur="juge-vrais-appels" className="text-destructive">
                    {t({ en: "Could not read or save this setting", fr: "Réglage illisible ou non enregistré" })}
                </span>
            )}
        </div>
    );
}
