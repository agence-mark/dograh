"use client";

/**
 * [.mark] Lots 8 et 22 : le catalogue des objets citables de l'agent ouvert (`GET /mark/etiquettes-prompt?agent=`), lu UNE fois par
 * page et partagé par tous les champs (une lecture par donnée et par page). `relireLesEtiquettes()` le rafraîchit après une
 * correction. Sans réponse, `lu` reste faux : aucune étiquette n'est déclarée en erreur.
 */
import { useParams } from "next/navigation";
import { useEffect, useState } from "react";

import { lireLesEtiquettesApiV1MarkEtiquettesPromptGet } from "@/client/sdk.gen";
import type { CatalogueEtiquettes } from "@/client/types.gen";
import { useAuth } from "@/lib/auth";

import type { ObjetCitable } from "./etiquettes-objets";

export interface EtatEtiquettes {
    objets: ObjetCitable[];
    problemes: CatalogueEtiquettes["problemes"];
    lu: boolean;
}

const VIDE: EtatEtiquettes = { objets: [], problemes: [], lu: false };
const enCours = new Map<number, Promise<EtatEtiquettes>>();
const abonnes = new Set<() => void>();

const lire = (agent: number): Promise<EtatEtiquettes> => {
    let promesse = enCours.get(agent);
    if (!promesse) {
        promesse = (async () => {
            try {
                const r = await lireLesEtiquettesApiV1MarkEtiquettesPromptGet({ query: agent > 0 ? { agent } : undefined });
                if (r.error || !r.data) return VIDE;
                return { objets: r.data.objets, problemes: r.data.problemes, lu: true };
            } catch {
                return VIDE;
            }
        })();
        enCours.set(agent, promesse);
    }
    return promesse;
};

/** Oublie la lecture : les champs ouverts relisent le catalogue (après une correction, un outil créé…). */
export const relireLesEtiquettes = () => {
    enCours.clear();
    abonnes.forEach((f) => f());
};

export const useCatalogueEtiquettes = (actif = true): EtatEtiquettes => {
    const params = useParams<{ workflowId?: string; id?: string }>();
    const agent = Number(params?.workflowId ?? params?.id);
    const { user, loading: authLoading } = useAuth();
    const [etat, setEtat] = useState<EtatEtiquettes>(VIDE);
    const [tour, setTour] = useState(0);
    useEffect(() => {
        const relire = () => setTour((n) => n + 1);
        abonnes.add(relire);
        return () => {
            abonnes.delete(relire);
        };
    }, []);
    useEffect(() => {
        if (!actif || authLoading || !user) return;
        let annule = false;
        void lire(Number.isFinite(agent) ? agent : 0).then((e) => {
            if (!annule) setEtat(e);
        });
        return () => {
            annule = true;
        };
    }, [actif, agent, authLoading, user, tour]);
    return etat;
};
