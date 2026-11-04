import { notFound } from 'next/navigation';
import { Suspense } from 'react';

import {
    getAgentsServisApiV1OrganizationsAgentsServisGet,
    getWorkflowsApiV1WorkflowFetchGet,
    lireLesGroupesApiV1WorkflowGroupesGet,
    listerLesEspacesApiV1EspacesGet,
    listFoldersApiV1FolderGet,
} from '@/client/sdk.gen';
import type { FolderResponse, LienDeGroupe, WorkflowListResponse } from '@/client/types.gen';
import { ListeAgents } from '@/components/mark/agent/ListeAgents';
import { EtatVide } from '@/components/mark/studio/etat-vide';
import { getServerAccessToken, getServerAuthProvider } from '@/lib/auth/server';
import { ENTETE_ESPACE, ENTETE_ORGANISATION } from '@/lib/espaceCourant';
import logger from '@/lib/logger';

import WorkflowLayout from "./WorkflowLayout";

/**
 * [.mark] V1 : cette liste se lit côté serveur, donc sans l'en-tête que le navigateur pose seul. Sans lui, `/clients/2/agents`
 * montrait les agents du Labo sous le nom du client. L'organisation vient de l'adresse (`/clients/<id>/…`) ; sur `/labo/…`,
 * c'est le Labo que disent les espaces du compte ; autrement, le serveur garde l'organisation du compte (comme avant).
 */
export async function enteteOrganisation(accessToken: string | null | undefined, org: string | undefined, labo: boolean): Promise<Record<string, string>> {
    if (org && /^\d+$/.test(org)) return { [ENTETE_ORGANISATION]: org };
    if (!labo) return {};
    // R3 M1 : l'en-tête d'espace part toujours depuis le Labo ; si l'identifiant manque, le serveur lit le Labo ou refuse,
    // il ne retombe jamais sur l'organisation par défaut du compte (qui peut être un client).
    try {
        const r = await listerLesEspacesApiV1EspacesGet({ headers: { Authorization: `Bearer ${accessToken}` } });
        const id = (r.data?.espaces as Array<{ id: number; espace: string }> | undefined)?.find((e) => e.espace === 'labo')?.id;
        return id ? { [ENTETE_ESPACE]: 'labo', [ENTETE_ORGANISATION]: String(id) } : { [ENTETE_ESPACE]: 'labo' };
    } catch (err) {
        logger.error(`Error reading the spaces: ${err}`);
        return { [ENTETE_ESPACE]: 'labo' };
    }
}

// Server component for workflow list
async function WorkflowList({ dossierOuvertId, org, labo }: { dossierOuvertId: number | null; org?: string; labo: boolean }) {
    const authProvider = await getServerAuthProvider();
    const accessToken = await getServerAccessToken();

    if (!accessToken) {
        // If no token, user needs to sign in
        const { redirect } = await import('next/navigation');
        if (authProvider === 'stack') {
            redirect('/');
        } else {
            // For OSS mode, this shouldn't happen as token is auto-generated
            return (
                <div className="text-destructive">
                    Authentication required. Please refresh the page.
                </div>
            );
        }
    }

    const organisation = await enteteOrganisation(accessToken, org, labo);
    try {
        // Fetch both active and archived workflows in a single request
        const response = await getWorkflowsApiV1WorkflowFetchGet({
            headers: {
                'Authorization': `Bearer ${accessToken}`,
                ...organisation,
            },
            query: {
                status: 'active,archived'
            }
        });

        const allWorkflowData = response.data ? (Array.isArray(response.data) ? response.data : [response.data]) : [];

        // Separate active and archived workflows
        const activeWorkflows = allWorkflowData
            .filter((w: WorkflowListResponse) => w.status === 'active')
            .sort((a: WorkflowListResponse, b: WorkflowListResponse) => new Date(b.created_at).getTime() - new Date(a.created_at).getTime());

        const archivedWorkflows = allWorkflowData
            .filter((w: WorkflowListResponse) => w.status === 'archived')
            .sort((a: WorkflowListResponse, b: WorkflowListResponse) => new Date(b.created_at).getTime() - new Date(a.created_at).getTime());

        // Fetch folders for grouping active agents. A failure here shouldn't
        // break the page — fall back to an empty list (flat, ungrouped view).
        let folders: FolderResponse[] = [];
        try {
            const foldersResponse = await listFoldersApiV1FolderGet({
                headers: {
                    'Authorization': `Bearer ${accessToken}`,
                    ...organisation,
                },
            });
            folders = foldersResponse.data ?? [];
        } catch (folderErr) {
            logger.error(`Error fetching folders: ${folderErr}`);
        }

        // [.mark] Lots 10 and 12 (agents-specialises): the groups of agents and what each serves, to draw
        // the group cards. Best effort like the folders: a failure leaves the list as it was.
        let liens: LienDeGroupe[] = [];
        let servis: Array<{ id: number; numeros: string[]; etablissementId: string | null }> = [];
        try {
            const headers = { 'Authorization': `Bearer ${accessToken}`, ...organisation };
            const [liensResponse, servisResponse] = await Promise.all([
                lireLesGroupesApiV1WorkflowGroupesGet({ headers }),
                getAgentsServisApiV1OrganizationsAgentsServisGet({ headers }),
            ]);
            liens = liensResponse.data?.agents ?? [];
            servis = (servisResponse.data?.agents ?? []).map((a) => ({
                id: a.id,
                numeros: a.numeros ?? [],
                etablissementId: a.etablissement_id ?? null,
            }));
        } catch (groupErr) {
            logger.error(`Error fetching agent groups: ${groupErr}`);
        }

        return (
            <ListeAgents
                actifs={activeWorkflows}
                archives={archivedWorkflows}
                dossiers={folders}
                liens={liens}
                dossierOuvertId={dossierOuvertId}
            />
        );
    } catch (err) {
        logger.error(`Error fetching workflows: ${err}`);
        return (
            <div className="text-destructive">
                Failed to load Workflows. Please Try Again Later.
            </div>
        );
    }
}

export async function PageDesAgents({
    searchParams,
    params,
    labo = false,
}: {
    searchParams?: Promise<{ dossier?: string }>;
    params?: Promise<{ org?: string }>;
    labo?: boolean;
}) {
    const org = (await params)?.org;
    // R3 : `/clients/<pas un nombre>` est une page introuvable, jamais l'espace retenu ni celui du compte.
    if (org !== undefined && !/^\d+$/.test(org)) notFound();
    // [.mark] Lot 12: arriving from « Graph with specialised agents », the group's sub-folder is open.
    const brut = Number((await searchParams)?.dossier);
    const dossierOuvertId = Number.isInteger(brut) && brut > 0 ? brut : null;
    return (
        <WorkflowLayout showFeaturesNav={true}>
            <Suspense fallback={<EtatVide cas="chargement" lignes={6} />}>
                <WorkflowList dossierOuvertId={dossierOuvertId} org={org} labo={labo} />
            </Suspense>
        </WorkflowLayout>

    );
}
