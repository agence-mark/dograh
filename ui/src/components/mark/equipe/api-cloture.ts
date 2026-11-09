"use client";

/**
 * [.mark] Clôture, lots A et B : les appels de l'écran que le client généré n'a pas encore (accès bloqué, filtres et réglages du journal, rôle et
 * interrupteurs des clés d'API, protection par agent). Le client généré se régénère à la fusion par la fenêtre principale ; ce module s'appuie sur
 * le même client HTTP et se remplace alors par les fonctions générées.
 */
import { client } from "@/client/client.gen";

const JSON_ENTETE = { "Content-Type": "application/json" };

/** Le client rend `{ data, error }` sans jamais lever : une réponse typée à la main (le client généré le fera à la prochaine régénération). */
type Reponse<T> = Promise<{ data?: T; error?: unknown }>;
const lire = <T>(p: Promise<unknown>) => p as Reponse<T>;

export interface FiltresDuJournal {
    membre?: number;
    organization_id?: number;
    action?: string;
    origine?: "ecran" | "api" | "mcp";
    limit: number;
    offset: number;
}

export interface LigneDuJournal {
    id: number;
    quand: string;
    user_id: number | null;
    auteur: string;
    prenom: string | null;
    nom: string | null;
    qui?: string | null;
    sans_nom?: boolean;
    action: string;
    organization_id: number | null;
    detail: Record<string, unknown> | null;
    origine?: "ecran" | "api" | "mcp" | null;
}

export interface ReglagesEquipe {
    message_acces_bloque: { fr: string; en: string; defaut: { fr: string; en: string } };
    journal_mois: number;
    journal_mois_min: number;
    journal_mois_max: number;
}

export const changerLAcces = (userId: number, actif: boolean) =>
    lire<unknown>(client.put({ url: `/api/v1/equipe-mark/membres/${userId}/acces`, body: { actif }, headers: JSON_ENTETE }));

export const lireLeJournalFiltre = (f: FiltresDuJournal) =>
    lire<{ lignes: LigneDuJournal[]; total: number; limit: number; offset: number }>(
        client.get({ url: "/api/v1/equipe-mark/journal", query: { ...f } }),
    );

export const typesDeGestes = () => lire<string[]>(client.get({ url: "/api/v1/equipe-mark/journal/types" }));

export const lireLesReglagesDeLEquipe = () => lire<ReglagesEquipe>(client.get({ url: "/api/v1/equipe-mark/reglages" }));

export const reglerLeMessageBloque = (fr: string, en: string) =>
    lire<ReglagesEquipe>(
        client.put({ url: "/api/v1/equipe-mark/reglages/message-acces-bloque", body: { fr, en }, headers: JSON_ENTETE }),
    );

export const reglerLaDureeDuJournal = (mois: number) =>
    lire<ReglagesEquipe>(client.put({ url: "/api/v1/equipe-mark/reglages/duree-journal", body: { mois }, headers: JSON_ENTETE }));

export type GesteMcp = "publier" | "tests_payants" | "appels_reels";

export interface CleDroits {
    id: number;
    role_id?: number | null;
    role_nom?: string | null;
    suspendue?: boolean;
    mcp_publier?: boolean;
    mcp_tests_payants?: boolean;
    mcp_appels_reels?: boolean;
}

export const changerLeRoleDeLaCle = (id: number, roleId: number | null) =>
    lire<unknown>(client.put({ url: `/api/v1/user/api-keys/${id}/role`, body: { role_id: roleId }, headers: JSON_ENTETE }));

export const suspendreLaCle = (id: number, suspendue: boolean) =>
    lire<unknown>(client.put({ url: `/api/v1/user/api-keys/${id}/suspension`, body: { suspendue }, headers: JSON_ENTETE }));

export const changerLesInterrupteursMcp = (id: number, reglage: Partial<Record<GesteMcp, boolean>>) =>
    lire<unknown>(client.put({ url: `/api/v1/user/api-keys/${id}/mcp`, body: reglage, headers: JSON_ENTETE }));

export const regenererLaClePortail = () =>
    lire<{ id: number; name: string; key_prefix: string; api_key: string; created_at: string }>(
        client.post({ url: "/api/v1/user/api-keys/portail/regenerer" }),
    );

export const changerLaProtection = (workflowId: number, protegee: boolean | null) =>
    lire<{ ok: boolean; protegee: boolean; protegee_par_defaut: boolean; reglee: boolean | null }>(
        client.put({ url: `/api/v1/builder/branches/${workflowId}/principale/protection`, body: { protegee }, headers: JSON_ENTETE }),
    );
