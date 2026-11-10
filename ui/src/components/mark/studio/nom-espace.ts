"use client";

/** [.mark] Le nom d'affichage de l'espace courant (« Labo », le nom du client), lu une fois dans `GET /espaces`. */
import { useEffect, useState } from "react";

import { useLangue } from "@/components/mark/langue/langue";
import { useAuth } from "@/lib/auth";
import { type Espace, listerEspaces } from "@/lib/espaces";
import { surChangementDEspaces, versionDesEspaces } from "@/lib/espaces-changes";

/** Le nom de l'espace des relations avec les clients (un espace de .mark, sans organisation). */
export const RELATION_CLIENTS = { en: "Customer relations", fr: "Relation clients" };

let enCours: Promise<Espace[]> | null = null;
let versionLue = 0;

/** La lecture partagée : refaite une fois par changement d'espace (renommage), jamais une lecture par lecteur. */
function lecture(): Promise<Espace[]> {
    if (versionLue !== versionDesEspaces()) {
        versionLue = versionDesEspaces();
        enCours = null;
    }
    enCours ??= listerEspaces().catch(() => {
        enCours = null;
        return [];
    });
    return enCours;
}

export function useNomEspace(espace: "labo" | "client" | "relation", org: string | null): string | null {
    const { t } = useLangue();
    const { loading, user } = useAuth();
    const [espaces, setEspaces] = useState<Espace[]>([]);
    useEffect(() => {
        if (loading || !user) return;
        let vivant = true;
        const lire = () => void lecture().then((e) => vivant && setEspaces(e));
        lire();
        const seDesabonner = surChangementDEspaces(lire);
        return () => {
            vivant = false;
            seDesabonner();
        };
    }, [loading, user]);
    if (espace === "relation") return t(RELATION_CLIENTS);
    const courant = espaces.find((e) => (espace === "labo" ? e.espace === "labo" : String(e.id) === org));
    return courant?.nom ?? null;
}
