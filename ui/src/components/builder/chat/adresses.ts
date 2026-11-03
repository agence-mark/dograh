"use client";

/**
 * [.mark] U2 quater (E57) : le builder et le chat vivent dans le Labo ET dans l'espace d'un client, le même écran. Les adresses
 * que l'écran fabrique (ouvrir une conversation) suivent l'espace où l'on est : `/labo/builder/<id>` au Labo,
 * `/clients/<org>/chat/<id>` chez un client. Une seule lecture de l'adresse, ici.
 */
import { usePathname } from "next/navigation";

import { espaceDe } from "@/components/mark/studio/navigation-studio";
import { useNomEspace } from "@/components/mark/studio/nom-espace";

export type AdressesDuBuilder = {
    /** `true` dans l'espace d'un client : le builder y est cloisonné à cette organisation. */
    client: boolean;
    /** Le nom du client (rien tant que la liste des espaces n'est pas lue, et rien au Labo). */
    nomDuClient: string | null;
    fil: (id: number) => string;
    /** La liste des chats de l'espace. */
    liste: string;
    /** Les réglages du builder : propres au Labo (le coût se prend sur la clé du Labo). */
    reglages: string | null;
};

export const adressesDe = (pathname: string): Omit<AdressesDuBuilder, "nomDuClient"> & { org: string | null } => {
    const { espace, base, org } = espaceDe(pathname);
    return espace === "client"
        ? { client: true, org, fil: (id) => `${base}/chat/${id}`, liste: `${base}/chat`, reglages: null }
        : { client: false, org: null, fil: (id) => `/labo/builder/${id}`, liste: "/labo/builder", reglages: "/labo/reglages" };
};

export function useAdressesDuBuilder(): AdressesDuBuilder {
    const { org, ...adresses } = adressesDe(usePathname() ?? "/labo");
    const nom = useNomEspace(adresses.client ? "client" : "labo", org);
    return { ...adresses, nomDuClient: adresses.client ? nom : null };
}
