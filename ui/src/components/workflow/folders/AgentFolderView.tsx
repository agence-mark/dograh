'use client';

import type { FolderResponse, WorkflowListResponse } from '@/client/types.gen';
import {
    arbreDesDossiers,
    grouperLesAgents,
    type LienDuGroupe,
    type NoeudDeDossier,
    rolesDesAgents,
} from '@/components/mark/groupe/liens-groupes';
import { VueGroupe } from '@/components/mark/groupe/VueGroupe';

import { WorkflowTable } from '../WorkflowTable';
import { FolderSection } from './FolderSection';

interface AgentFolderViewProps {
    /** Active (non-archived) agents only. */
    workflows: WorkflowListResponse[];
    folders: FolderResponse[];
    /**
     * [.mark] Lots 10 and 12 (agents-specialises): the agents that belong to a group (main agent or
     * specialised), what each serves (numbers, record), and the folder to open at arrival (the one of
     * the group just created). Absent: the list is what it was.
     */
    liens?: LienDuGroupe[];
    servis?: Array<{ id: number; numeros: string[]; etablissementId: string | null }>;
    dossierOuvertId?: number | null;
}

/**
 * Renders active agents grouped into collapsible folder sections.
 *
 * When the organization has no folders yet, this falls back to the original
 * flat table so the feature stays invisible until someone creates a folder.
 *
 * [.mark] Folders nest (a sub-folder per group of agents): the sections are drawn as a tree, collapsed
 * by default at every level. A folder that holds a group shows the group's card (its main agent,
 * its specialised agents beneath), a lone agent keeps its row.
 */
export function AgentFolderView({ workflows, folders, liens = [], servis = [], dossierOuvertId = null }: AgentFolderViewProps) {
    const noms = new Map(workflows.map((w) => [w.id, w.name]));
    const roles = rolesDesAgents(liens, noms);

    // No folders → keep the original flat list (no folder chrome, nowhere to move to).
    if (folders.length === 0) {
        return <WorkflowTable workflows={workflows} showArchived={false} roles={roles} />;
    }

    // Group agents by folder. Agents whose folder_id is null — or points at a
    // folder we didn't get back — fall into "Uncategorized".
    const folderIds = new Set(folders.map((f) => f.id));
    const byFolder = new Map<number, WorkflowListResponse[]>();
    const uncategorized: WorkflowListResponse[] = [];

    for (const wf of workflows) {
        if (wf.folder_id != null && folderIds.has(wf.folder_id)) {
            const bucket = byFolder.get(wf.folder_id) ?? [];
            bucket.push(wf);
            byFolder.set(wf.folder_id, bucket);
        } else {
            uncategorized.push(wf);
        }
    }

    const infos = new Map(servis.map((s) => [s.id, { numeros: s.numeros, etablissementId: s.etablissementId }]));

    // The folder to open at arrival, and the folders above it.
    const aOuvrir = new Set<number>();
    for (let id: number | null = dossierOuvertId; id != null && !aOuvrir.has(id); ) {
        aOuvrir.add(id);
        id = folders.find((f) => f.id === id)?.parent_id ?? null;
    }

    const cartesDesGroupes = (agents: WorkflowListResponse[], dossierId: number | null) => {
        const { groupes, seuls } = grouperLesAgents(agents, liens);
        return {
            seuls,
            cartes:
                groupes.length > 0
                    ? groupes.map((g) => (
                          <VueGroupe
                              key={g.principal.id}
                              principal={g.principal}
                              specialises={g.specialises}
                              roles={roles}
                              servis={infos}
                              dossiers={folders}
                              dossierId={dossierId}
                          />
                      ))
                    : undefined,
        };
    };

    const section = (noeud: NoeudDeDossier) => {
        const agents = byFolder.get(noeud.dossier.id) ?? [];
        const { seuls, cartes } = cartesDesGroupes(agents, noeud.dossier.id);
        return (
            <FolderSection
                key={noeud.dossier.id}
                kind="folder"
                folder={noeud.dossier}
                workflows={seuls}
                nombre={agents.length}
                allFolders={folders}
                defaultOpen={aOuvrir.has(noeud.dossier.id)}
                roles={roles}
                groupes={cartes}
            >
                {noeud.enfants.length > 0 ? noeud.enfants.map(section) : undefined}
            </FolderSection>
        );
    };

    const sansDossier = cartesDesGroupes(uncategorized, null);

    return (
        <div className="space-y-1">
            {arbreDesDossiers(folders).map(section)}
            {uncategorized.length > 0 && (
                <FolderSection
                    kind="uncategorized"
                    workflows={sansDossier.seuls}
                    nombre={uncategorized.length}
                    allFolders={folders}
                    roles={roles}
                    groupes={sansDossier.cartes}
                />
            )}
        </div>
    );
}
