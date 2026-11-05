"use client";

/**
 * [.mark] Partie 3, sous-lot 20 : deux petits crochets de l'éditeur du graphe.
 * - `usePreferenceLocale` : un choix d'affichage propre à la personne (aimant, carte, empêcher les boucles), gardé par son
 *   navigateur. Le stockage peut manquer (fenêtre privée) : l'écran marche sans, le choix tient jusqu'au rechargement.
 * - `useStatistiquesDesEtapes` : lit les derniers appels de l'agent par la route EXISTANTE, puis les étapes traversées
 *   (`statistiques-etapes.ts`). Rien n'est lu tant que les statistiques sont éteintes.
 */
import { useCallback, useEffect, useState } from "react";

import { getWorkflowRunsApiV1WorkflowWorkflowIdRunsGet } from "@/client";
import { notifier } from "@/components/mark/notifications";

import { type AppelLu, lireLesEtapes, type StatistiquesDesEtapes } from "./statistiques-etapes";

export function usePreferenceLocale(cle: string, parDefaut: boolean): [boolean, () => void] {
    const [valeur, setValeur] = useState(parDefaut);
    useEffect(() => {
        try {
            const gardee = window.localStorage.getItem(cle);
            if (gardee === "1" || gardee === "0") setValeur(gardee === "1");
        } catch {
            /* pas de stockage : le choix par défaut */
        }
    }, [cle]);
    const basculer = useCallback(() => {
        setValeur((v) => {
            try {
                window.localStorage.setItem(cle, v ? "0" : "1");
            } catch {
                /* le choix tient jusqu'au rechargement */
            }
            return !v;
        });
    }, [cle]);
    return [valeur, basculer];
}

/** Le nombre d'appels lus pour les statistiques : les derniers, la route des appels de l'agent en rend 100 au plus. */
export const APPELS_LUS = 100;

export function useStatistiquesDesEtapes(workflowId: number, allumees: boolean): StatistiquesDesEtapes | null {
    const [stats, setStats] = useState<StatistiquesDesEtapes | null>(null);
    useEffect(() => {
        if (!allumees) return;
        let annule = false;
        void (async () => {
            const reponse = await getWorkflowRunsApiV1WorkflowWorkflowIdRunsGet({
                path: { workflow_id: workflowId },
                query: { page: 1, limit: APPELS_LUS },
            });
            if (annule) return;
            if (reponse.error || !reponse.data) {
                notifier.echec({ fr: "Statistiques illisibles. Réessayez dans un instant.", en: "Could not read the statistics. Try again in a moment." });
                return;
            }
            setStats(lireLesEtapes(reponse.data.runs as AppelLu[]));
        })();
        return () => {
            annule = true;
        };
    }, [workflowId, allumees]);
    return allumees ? stats : null;
}
