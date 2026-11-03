// [.mark] U2 : les espaces (le Labo et les clients) que le rôle du compte ouvre. Enveloppe du client d'API généré.
import {
    listerLesEspacesApiV1EspacesGet,
    reglerUnEspaceApiV1EspacesOrganizationIdPut,
} from "@/client/sdk.gen";
import { detailFromError } from "@/lib/apiError";
import { definirLabo, preparerLabo } from "@/lib/espaceCourant";

export type Espace = { id: number; nom: string; provider_id: string; espace: "labo" | "client"; selectionne: boolean };

export async function listerEspaces(): Promise<Espace[]> {
    const { data, error } = await listerLesEspacesApiV1EspacesGet();
    if (error || !data) throw new Error(detailFromError(error, "Failed to list the spaces"));
    const espaces = data.espaces as Espace[];
    // L'identifiant du Labo sert à toutes les requêtes faites depuis /labo.
    definirLabo(espaces.find((e) => e.espace === "labo")?.id ?? null);
    return espaces;
}

export async function reglerEspace(id: number, corps: { nom_affichage?: string | null; labo?: boolean }) {
    const { data, error } = await reglerUnEspaceApiV1EspacesOrganizationIdPut({ path: { organization_id: id }, body: corps });
    if (error || !data) throw new Error(detailFromError(error, "Failed to update the space"));
    return data;
}

export const adresseDe = (e: Pick<Espace, "id" | "espace">) => (e.espace === "labo" ? "/labo" : `/clients/${e.id}`);

preparerLabo(listerEspaces);
