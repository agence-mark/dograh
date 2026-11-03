"use client";

import { useEffect, useState } from "react";

import { lireClientsRelation } from "@/components/mark/relation/lecture-clients";
import { useAuth } from "@/lib/auth";

import type { Espace } from "./navigation-studio";
import type { CompteurMenu } from "./sidebar-studio";

/**
 * Compteurs de la barre latérale, branchés sur des routes réelles (ordre 18). Un compteur sans source n'est pas
 * affiché (jamais de fausse valeur) :
 *  - Relation clients › Messages : somme des messages non lus des clients (`/relation/clients`, une seule lecture
 *    partagée avec la page). Urgent, comme la maquette.
 *  - Chat et À améliorer : pas de route de comptage au fork pour l'instant (voir `18`), donc rien d'affiché.
 * Relu à chaque changement de page (`cle`), jamais en boucle.
 */
export function useCompteursBarre(espace: Espace, cle: string): Record<string, CompteurMenu> {
    const { user, loading } = useAuth();
    const [messages, setMessages] = useState(0);
    useEffect(() => {
        if (espace !== "relation" || loading || !user) return;
        let actif = true;
        lireClientsRelation()
            .then((res) => {
                if (!actif || !res.data) return;
                setMessages(res.data.reduce((total, c) => total + (c.non_lus ?? 0), 0));
            })
            .catch(() => undefined);
        return () => {
            actif = false;
        };
    }, [espace, cle, loading, user]);
    return espace === "relation" && messages > 0 ? { "relation-messages": { n: messages, urgent: true } } : {};
}
