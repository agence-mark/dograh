"use client";

/**
 * [.mark] T6 : la racine de l'espace où l'on se trouve (`/labo` ou `/clients/<org>`), pour qu'une flèche retour ramène à la
 * liste DU MÊME espace : une adresse neutre (`/conversations/3`, `/campaigns/9`) ne dit pas l'espace, l'onglet le retient.
 * Les anciennes adresses neutres redirigent vers le Labo (`lib/redirections.ts`) : sans cette lecture, un retour depuis un
 * client atterrirait chez le Labo.
 */
import { usePathname } from "next/navigation";

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
