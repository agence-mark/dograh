"use client";

/**
 * [.mark] Partie 3, lot 15 (SE-25, L-1) : l'état remonté dans la ligne d'un thème (au lieu de « Dans la fenêtre »).
 *
 * Chaque ligne dit ce qui est réglé, lu sur la vraie route : l'agenda branché, le repli en cas de panne, les clés d'API, le
 * serveur MCP (il se joint avec une clé), le traçage Langfuse. Une lecture qui échoue dit « illisible », jamais un état
 * inventé ; tant qu'elle n'est pas revenue, la ligne dit « Lecture… ». Les lectures partent toutes ensemble, une seule fois,
 * quand l'authentification est prête.
 */
import { useEffect, useRef, useState } from "react";

import {
    getApiKeysApiV1UserApiKeysGet,
    getLangfuseCredentialsApiV1OrganizationsLangfuseCredentialsGet,
    getPanneApiV1OrganizationsPanneGet,
} from "@/client/sdk.gen";
import { useAuth } from "@/lib/auth";

export type Lu<T> = { etat: "chargement" } | { etat: "illisible" } | { etat: "lu"; valeur: T };
const CHARGEMENT = { etat: "chargement" } as const;

/** Ce que la ligne dit : tout est déjà réduit à des faits (aucune clé, aucun secret ne passe ici). */
export type EtatsDesLignes = {
    /** Une adresse de secours est réglée (le repli en cas de panne répond ailleurs). */
    repli: Lu<boolean>;
    /** Nombre de clés d'API actives. */
    cles: Lu<number>;
    /** Le traçage Langfuse est configuré (hôte et clés enregistrés). */
    langfuse: Lu<boolean>;
};

export function useEtatsDesLignes(): EtatsDesLignes {
    const { user, loading } = useAuth();
    const [etats, setEtats] = useState<EtatsDesLignes>({ repli: CHARGEMENT, cles: CHARGEMENT, langfuse: CHARGEMENT });
    const dejaLu = useRef(false);
    const monte = useRef(true);
    useEffect(() => {
        monte.current = true;
        return () => {
            monte.current = false;
        };
    }, []);

    useEffect(() => {
        if (loading || !user || dejaLu.current) return;
        dejaLu.current = true;
        // `lire` ne laisse jamais passer une exception : une lecture en échec devient « illisible ».
        const lire = async <T,>(appel: () => Promise<{ data?: unknown; error?: unknown }>, extraire: (donnees: never) => T): Promise<Lu<T>> => {
            try {
                const r = await appel();
                if (r.error || r.data === undefined || r.data === null) return { etat: "illisible" };
                return { etat: "lu", valeur: extraire(r.data as never) };
            } catch {
                return { etat: "illisible" };
            }
        };
        void (async () => {
            const [repli, cles, langfuse] = await Promise.all([
                lire(
                    () => getPanneApiV1OrganizationsPanneGet(),
                    (d: { reglages?: { url_secours?: string | null } }) => Boolean(d.reglages?.url_secours),
                ),
                lire(
                    () => getApiKeysApiV1UserApiKeysGet(),
                    (d: { is_active?: boolean }[]) => (Array.isArray(d) ? d.filter((k) => k.is_active !== false).length : 0),
                ),
                lire(
                    () => getLangfuseCredentialsApiV1OrganizationsLangfuseCredentialsGet(),
                    (d: { configured?: boolean }) => Boolean(d.configured),
                ),
            ]);
            if (monte.current) setEtats({ repli, cles, langfuse });
        })();
    }, [loading, user]);

    return etats;
}
