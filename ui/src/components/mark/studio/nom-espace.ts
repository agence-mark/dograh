"use client";

/** [.mark] Le nom d'affichage de l'espace courant (« Labo », le nom du client), lu une fois dans `GET /espaces`. */
import { useEffect, useState } from "react";

import { useAuth } from "@/lib/auth";
import { type Espace, listerEspaces } from "@/lib/espaces";

let enCours: Promise<Espace[]> | null = null;

export function useNomEspace(espace: "labo" | "client", org: string | null): string | null {
    const { loading, user } = useAuth();
    const [espaces, setEspaces] = useState<Espace[]>([]);
    useEffect(() => {
        if (loading || !user) return;
        enCours ??= listerEspaces().catch(() => {
            enCours = null;
            return [];
        });
        let vivant = true;
        enCours.then((e) => vivant && setEspaces(e));
        return () => {
            vivant = false;
        };
    }, [loading, user]);
    const courant = espaces.find((e) => (espace === "labo" ? e.espace === "labo" : String(e.id) === org));
    return courant?.nom ?? null;
}
