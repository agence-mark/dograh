"use client";

/**
 * [.mark] T6 : la racine de l'espace où l'on se trouve (`/labo` ou `/clients/<org>`), pour qu'une flèche retour ramène à la
 * liste DU MÊME espace : une adresse neutre (`/conversations/3`, `/campaigns/9`) ne dit pas l'espace, l'onglet le retient.
 * Les anciennes adresses neutres redirigent vers le Labo (`lib/redirections.ts`) : sans cette lecture, un retour depuis un
 * client atterrirait chez le Labo.
 */
import { usePathname } from "next/navigation";
import { useEffect, useState } from "react";

import { espaceDeAdresse, espaceRetenu } from "@/lib/espaceCourant";

import { espaceDe } from "./navigation-studio";

/** Pure : la racine pour une adresse et l'espace retenu par l'onglet (jamais `/relation`, qui a sa propre racine). */
export function baseDeEspace(pathname: string, retenu: number | "labo" | null): string {
    const { espace, base } = espaceDe(pathname);
    if (espace === "relation") return base;
    const dite = espaceDeAdresse(pathname);
    if (dite !== null) return base;
    if (typeof retenu === "number") return `/clients/${retenu}`;
    return "/labo";
}

export function useBaseEspace(): string {
    const pathname = usePathname() ?? "";
    return baseDeEspace(pathname, espaceRetenu());
}

/**
 * Clôture, SA-3 : l'espace AFFICHÉ (menu, miettes, nom de l'espace). Une adresse qui le dit (`/labo/...`, `/clients/<id>/...`)
 * fait foi ; une adresse neutre (`/agents/1/settings`) prend l'espace que l'onglet a retenu : sans cela, l'agent d'un client
 * se lisait dans le menu du Labo. Lu après l'affichage (le stockage de l'onglet n'existe pas côté serveur : pas de décalage).
 */
export function espaceAffiche(pathname: string, retenu: number | "labo" | null): ReturnType<typeof espaceDe> {
    const lu = espaceDe(pathname);
    if (lu.espace === "relation" || espaceDeAdresse(pathname) !== null) return lu;
    if (typeof retenu === "number") return { espace: "client", base: `/clients/${retenu}`, org: String(retenu) };
    return lu;
}

export function useEspaceAffiche(pathname: string): ReturnType<typeof espaceDe> {
    const [retenu, setRetenu] = useState<number | "labo" | null>(null);
    useEffect(() => setRetenu(espaceRetenu()), [pathname]);
    return espaceAffiche(pathname, retenu);
}
