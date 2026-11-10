// [.mark] U2 : les espaces (le Labo et les clients) que le rôle du compte ouvre. Enveloppe du client d'API généré.
import {
    listerLesEspacesApiV1EspacesGet,
    reglerUnEspaceApiV1EspacesOrganizationIdPut,
    remplacerLeLogoApiV1EspacesOrganizationIdLogoPut,
    retirerLeLogoApiV1EspacesOrganizationIdLogoDelete,
} from "@/client/sdk.gen";
import { detailFromError } from "@/lib/apiError";
import { definirLabo, preparerLabo } from "@/lib/espaceCourant";
import { signalerChangementDEspaces } from "@/lib/espaces-changes";
import { memoriserLogos } from "@/lib/logos-espaces";

export type Espace = { id: number; nom: string; provider_id: string; espace: "labo" | "client"; selectionne: boolean; logo_version?: string | null };

// Deux lectures peuvent se croiser (un renommage, un logo posé puis retiré) : la plus ancienne répond parfois en dernier.
// Seule une lecture plus récente que la dernière appliquée met à jour les logos (sinon un logo posé disparaîtrait de l'écran).
let lecturesLancees = 0;
let derniereAppliquee = 0;

export async function listerEspaces(): Promise<Espace[]> {
    const rang = ++lecturesLancees;
    const { data, error } = await listerLesEspacesApiV1EspacesGet();
    if (error || !data) throw new Error(detailFromError(error, "Failed to list the spaces"));
    const espaces = data.espaces as Espace[];
    if (rang > derniereAppliquee) {
        derniereAppliquee = rang;
        memoriserLogos(espaces);
    }
    // L'identifiant du Labo sert à toutes les requêtes faites depuis /labo.
    definirLabo(espaces.find((e) => e.espace === "labo")?.id ?? null);
    return espaces;
}

export async function reglerEspace(id: number, corps: { nom_affichage?: string | null; labo?: boolean }) {
    const { data, error } = await reglerUnEspaceApiV1EspacesOrganizationIdPut({ path: { organization_id: id }, body: corps });
    if (error || !data) throw new Error(detailFromError(error, "Failed to update the space"));
    // Le nom (ou le rôle de Labo) a changé : le sélecteur, les miettes et le menu relisent, sans recharger la page.
    signalerChangementDEspaces();
    return data;
}

/** Un refus du serveur sur le logo : `code` est le `detail` stable (`logo_format`, `logo_ratio`…), jamais montré tel quel. */
export class ErreurLogoServeur extends Error {
    constructor(
        readonly statut: number,
        readonly code: string,
    ) {
        super(code);
    }
}

/** Pose ou remplace le logo d'un client (le serveur relit le type réel et contrôle tout) ; les pastilles se relisent seules. */
export async function poserLogo(id: number, fichier: File) {
    const { data, error, response } = await remplacerLeLogoApiV1EspacesOrganizationIdLogoPut({
        path: { organization_id: id },
        body: { fichier },
    });
    if (error || !data) throw new ErreurLogoServeur(response?.status ?? 0, detailFromError(error, "logo_echec"));
    signalerChangementDEspaces();
    return data;
}

export async function retirerLogo(id: number) {
    const { data, error } = await retirerLeLogoApiV1EspacesOrganizationIdLogoDelete({ path: { organization_id: id } });
    if (error || !data) throw new Error(detailFromError(error, "Failed to remove the logo"));
    signalerChangementDEspaces();
    return data;
}

export const adresseDe = (e: Pick<Espace, "id" | "espace">) => (e.espace === "labo" ? "/labo" : `/clients/${e.id}`);

preparerLabo(listerEspaces);
