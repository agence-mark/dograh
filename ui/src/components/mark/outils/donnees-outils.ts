"use client";

/**
 * [.mark] Module Restauration, lot 13 (F9) : les appels de la colonne de gauche des Outils (dossiers, kits) aux routes du lot 11
 * (``api/routes/outils_rangement.py``). Types calqués sur ``api/schemas/outils_rangement.py``. Le client généré n'est pas régénéré ici :
 * même client HTTP que ``restauration/donnees.ts``.
 */
import { client } from "@/client/client.gen";
import type { ToolResponse } from "@/client/types.gen";

export interface Dossier {
    id: number;
    name: string;
    parent_id: number | null;
    tool_count: number;
}
export interface OutilDeKit {
    id: number;
    name: string;
    description: string | null;
    category: string;
    version: number;
    /** La définition de l'outil dans le kit (sans compte) : `config.restitution` dit ce que l'agent dit du résultat. */
    definition?: { config?: { restitution?: string } } & Record<string, unknown>;
}
/** Ce que l'agent dit du résultat d'un outil (T-01) : la phrase de l'outil telle quelle, reformulée, ou le conseil de l'outil (auto). */
export type Restitution = "mot_pour_mot" | "reformule" | "auto";
export const restitutionDe = (i: OutilDeKit): Restitution => {
    const r = i.definition?.config?.restitution;
    return r === "mot_pour_mot" || r === "reformule" ? r : "auto";
};
export interface AgentDuKit {
    agent_id: number;
    agent: string;
    outils: number;
    version_recue: number;
    version_du_kit: number;
    a_jour: boolean;
}
export interface Kit {
    id: number;
    name: string;
    description: string | null;
    items: OutilDeKit[];
}
type Reponse<T> = { data?: T; error?: unknown };
const JSON_ENTETE = { "Content-Type": "application/json" };
const lire = <T>(p: Promise<unknown>) => p as Promise<Reponse<T>>;
const T = "/api/v1/tools";

export const lireLesDossiers = () => lire<Dossier[]>(client.get({ url: `${T}/dossiers` }));
export const creerUnDossier = (name: string, parent_id: number | null) =>
    lire<Dossier>(client.post({ url: `${T}/dossiers`, body: { name, parent_id }, headers: JSON_ENTETE }));
export const renommerUnDossier = (id: number, name: string) =>
    lire<Dossier>(client.patch({ url: `${T}/dossiers/${id}`, body: { name }, headers: JSON_ENTETE }));
export const supprimerUnDossier = (id: number) => lire<unknown>(client.delete({ url: `${T}/dossiers/${id}` }));
export const rangerUnOutil = (toolUuid: string, dossierId: number | null) =>
    lire<unknown>(client.put({ url: `${T}/${toolUuid}/dossier`, body: { dossier_id: dossierId }, headers: JSON_ENTETE }));

export const lireLesKits = () => lire<Kit[]>(client.get({ url: `${T}/kits` }));
export const lireLesAgentsDuKit = (kitId: number) => lire<AgentDuKit[]>(client.get({ url: `${T}/kits/${kitId}/agents` }));
export const creerUnKit = (name: string) => lire<Kit>(client.post({ url: `${T}/kits`, body: { name }, headers: JSON_ENTETE }));
export const modifierUnKit = (id: number, corps: { name?: string; description?: string | null }) =>
    lire<Kit>(client.patch({ url: `${T}/kits/${id}`, body: corps, headers: JSON_ENTETE }));
export const supprimerUnKit = (id: number) => lire<unknown>(client.delete({ url: `${T}/kits/${id}` }));
export const ajouterAuKit = (kitId: number, toolUuid: string) =>
    lire<Kit>(client.post({ url: `${T}/kits/${kitId}/outils`, body: { tool_uuid: toolUuid }, headers: JSON_ENTETE }));
export const retirerDuKit = (kitId: number, itemId: number) => lire<Kit>(client.delete({ url: `${T}/kits/${kitId}/outils/${itemId}` }));
export const appliquerLeKit = (kitId: number, dossierId: number | null) =>
    lire<{ crees: string[]; deja_presents: number }>(client.post({ url: `${T}/kits/${kitId}/appliquer`, body: { dossier_id: dossierId }, headers: JSON_ENTETE }));

/** Un dossier et tous ses sous-dossiers : ce que montre la liste quand on ouvre ce dossier. */
export function descendance(dossiers: Dossier[], id: number): Set<number> {
    const ids = new Set<number>([id]);
    let change = true;
    while (change) {
        change = false;
        for (const d of dossiers) {
            if (d.parent_id !== null && ids.has(d.parent_id) && !ids.has(d.id)) {
                ids.add(d.id);
                change = true;
            }
        }
    }
    return ids;
}

export interface PropositionDeKit {
    tool_uuid: string;
    tool_name: string;
    kit_id: number;
    kit_name: string;
    version_recue: number;
    version_du_kit: number;
}
export const lireLesPropositions = () => lire<PropositionDeKit[]>(client.get({ url: `${T}/kits/propositions` }));
export const accepterUneProposition = (toolUuid: string) =>
    lire<unknown>(client.post({ url: `${T}/kits/propositions/accepter`, body: { tool_uuid: toolUuid }, headers: JSON_ENTETE }));

/** Un outil avec son rangement (`folder_id`, `kit_item_id`, `kit_version`) : le client généré les porte depuis la régénération du lot 26. */
export type OutilRange = ToolResponse;
