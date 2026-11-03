import { Suspense } from 'react';

import {
    getAgentsServisApiV1OrganizationsAgentsServisGet,
    getWorkflowsApiV1WorkflowFetchGet,
    lireLesGroupesApiV1WorkflowGroupesGet,
    listFoldersApiV1FolderGet,
} from '@/client/sdk.gen';
import type { FolderResponse, LienDeGroupe, WorkflowListResponse } from '@/client/types.gen';
import { ListeAgents } from '@/components/mark/agent/ListeAgents';
import { EtatVide } from '@/components/mark/studio/etat-vide';
import { getServerAccessToken, getServerAuthProvider } from '@/lib/auth/server';
import logger from '@/lib/logger';

import WorkflowLayout from "./WorkflowLayout";

export const dynamic = 'force-dynamic';

// Server component for workflow list
async function WorkflowList({ dossierOuvertId }: { dossierOuvertId: number | null }) {
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

    try {
        // Fetch both active and archived workflows in a single request
        const response = await getWorkflowsApiV1WorkflowFetchGet({
            headers: {
                'Authorization': `Bearer ${accessToken}`,
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
            const headers = { 'Authorization': `Bearer ${accessToken}` };
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

export default async function WorkflowPage({
    searchParams,
}: {
    searchParams?: Promise<{ dossier?: string }>;
}) {
    // [.mark] Lot 12: arriving from « Graph with specialised agents », the group's sub-folder is open.
    const brut = Number((await searchParams)?.dossier);
    const dossierOuvertId = Number.isInteger(brut) && brut > 0 ? brut : null;
    return (
        <WorkflowLayout showFeaturesNav={true}>
            <Suspense fallback={<EtatVide cas="chargement" lignes={6} />}>
                <WorkflowList dossierOuvertId={dossierOuvertId} />
            </Suspense>
        </WorkflowLayout>

    );
}
