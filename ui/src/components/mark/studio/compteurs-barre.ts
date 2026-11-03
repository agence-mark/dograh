"use client";

import { useEffect, useState } from "react";

import { compterLesAmeliorationsApiV1AmeliorationsCompteurGet, compterLesFilsApiV1BuilderFilsCompteurGet } from "@/client";
import { lireClientsRelation } from "@/components/mark/relation/lecture-clients";
import { useAuth } from "@/lib/auth";

import type { Espace } from "./navigation-studio";
import type { CompteurMenu } from "./sidebar-studio";

/**
 * Compteurs de la barre latérale, branchés sur des routes réelles (ordre 18). Un compteur sans source n'est pas
 * affiché (jamais de fausse valeur) :
 *  - Relation clients › Messages : somme des messages non lus des clients (`/relation/clients`, une seule lecture
 *    partagée avec la page). Urgent, comme la maquette.
 *  - Chat : le nombre de conversations du builder qui attendent la personne (changements à valider, travail fini),
 *    `/builder/fils/compteur` ;
 *  - À améliorer : problèmes « à trier » + éléments « à juger », `/ameliorations/compteur`. Les deux routes partent
 *    ENSEMBLE, une fois par changement de page, dans le Labo et chez un client (rouge dans le Labo, gris chez le client,
 *    comme la maquette). Une lecture refusée ou à zéro n'affiche rien.
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
    const [boucle, setBoucle] = useState<{ chat: number; aAmeliorer: number }>({ chat: 0, aAmeliorer: 0 });
    useEffect(() => {
        if (espace === "relation" || loading || !user) return;
        let actif = true;
        Promise.all([compterLesFilsApiV1BuilderFilsCompteurGet(), compterLesAmeliorationsApiV1AmeliorationsCompteurGet()])
            .then(([chat, amelioration]) => {
                if (!actif) return;
                setBoucle({ chat: chat.data?.en_attente ?? 0, aAmeliorer: amelioration.data?.total ?? 0 });
            })
            .catch(() => undefined);
        return () => {
            actif = false;
        };
    }, [espace, cle, loading, user]);
    if (espace === "relation") return messages > 0 ? { "relation-messages": { n: messages, urgent: true } } : {};
    const urgent = espace === "labo";
    return {
        ...(boucle.chat > 0 ? { chat: { n: boucle.chat, urgent } } : {}),
        ...(boucle.aAmeliorer > 0 ? { "a-ameliorer": { n: boucle.aAmeliorer, urgent } } : {}),
    };
}
