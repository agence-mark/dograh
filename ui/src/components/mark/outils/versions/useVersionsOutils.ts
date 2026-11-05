"use client";

/**
 * [.mark] Builder partie 3, SA-L3d (décision 21) : les lectures des versions d'outils.
 *
 * - `useOutilsDeLAgent` : les outils de l'agent OUVERT (brouillon de la branche ouverte, sinon version en ligne), avec la version
 *   épinglée et la courante ; relu après chaque passage (`relire`) et à chaque geste du builder ;
 * - `useVersionsDUnOutil` : les versions d'un outil et qui utilise quelle version (fenêtre de l'outil).
 * Les requêtes d'une page partent ensemble ; une panne se dit par `echec`, jamais un écran blanc.
 */
import { useCallback, useEffect, useState } from "react";

import { lireLesOutilsDeLAgentApiV1BuilderOutilsAgentWorkflowIdGet, lireLesVersionsDUnOutilApiV1BuilderOutilsToolUuidVersionsGet } from "@/client/sdk.gen";
import type { OutilDeLAgent, VersionsDUnOutil } from "@/client/types.gen";
import { useBuilderEcran } from "@/components/builder/ecran/store";

import { useRecalculDuPret } from "../../agent/pret/recalcul";

/** Un événement léger : un passage de version relit toutes les vues qui montrent des versions d'outils. */
let compteur = 0;
const ecouteurs = new Set<() => void>();
export function signalerUnChangementDeVersion() {
    compteur += 1;
    ecouteurs.forEach((e) => e());
    useRecalculDuPret.getState().demander();
}

function useChangementsDeVersion(): number {
    const [n, setN] = useState(compteur);
    useEffect(() => {
        const e = () => setN(compteur);
        ecouteurs.add(e);
        return () => {
            ecouteurs.delete(e);
        };
    }, []);
    return n;
}

export function useOutilsDeLAgent(workflowId?: number) {
    const [outils, setOutils] = useState<OutilDeLAgent[] | null>(null);
    const [echec, setEchec] = useState(false);
    const changements = useChangementsDeVersion();
    const gestes = useBuilderEcran((s) => s.operationsVives.length);

    const lire = useCallback(async () => {
        if (workflowId === undefined) return;
        try {
            const r = await lireLesOutilsDeLAgentApiV1BuilderOutilsAgentWorkflowIdGet({ path: { workflow_id: workflowId } });
            if (r.error || !r.data) setEchec(true);
            else {
                setEchec(false);
                setOutils(r.data.outils);
            }
        } catch {
            setEchec(true);
        }
    }, [workflowId]);

    useEffect(() => {
        void lire();
    }, [lire, changements, gestes]);

    return { outils, echec, relire: lire };
}

export function useVersionsDUnOutil(toolUuid: string) {
    const [vue, setVue] = useState<VersionsDUnOutil | null>(null);
    const [echec, setEchec] = useState(false);
    const changements = useChangementsDeVersion();

    const lire = useCallback(async () => {
        try {
            const r = await lireLesVersionsDUnOutilApiV1BuilderOutilsToolUuidVersionsGet({ path: { tool_uuid: toolUuid } });
            if (r.error || !r.data) setEchec(true);
            else {
                setEchec(false);
                setVue(r.data);
            }
        } catch {
            setEchec(true);
        }
    }, [toolUuid]);

    useEffect(() => {
        void lire();
    }, [lire, changements]);

    return { vue, echec, relire: lire };
}
