'use client';

import {
    Archive,
    ChevronRight,
    Folder as FolderIcon,
    FolderOpen,
    Inbox,
    MoreVertical,
    Pencil,
    Trash2,
} from 'lucide-react';
import { useRouter } from 'next/navigation';
import { type ReactNode, useState } from 'react';
import { notifier } from "@/components/mark/notifications";

import {
    deleteFolderApiV1FolderFolderIdDelete,
    renameFolderApiV1FolderFolderIdPut,
} from '@/client/sdk.gen';
import type { FolderResponse, WorkflowListResponse } from '@/client/types.gen';
import { ActionsSousDossier, DialogueNouveauSousDossier, NoteSuppressionSousDossier } from '@/components/mark/groupe/ActionsSousDossier';
import type { RoleAffiche } from '@/components/mark/groupe/BadgeGroupe';
import {
    AlertDialog,
    AlertDialogAction,
    AlertDialogCancel,
    AlertDialogContent,
    AlertDialogDescription,
    AlertDialogFooter,
    AlertDialogHeader,
    AlertDialogTitle,
} from '@/components/ui/alert-dialog';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import {
    Collapsible,
    CollapsibleContent,
    CollapsibleTrigger,
} from '@/components/ui/collapsible';
import {
    DropdownMenu,
    DropdownMenuContent,
    DropdownMenuItem,
    DropdownMenuTrigger,
} from '@/components/ui/dropdown-menu';
import logger from '@/lib/logger';
import { cn } from '@/lib/utils';

import { WorkflowTable } from '../WorkflowTable';
import { FolderFormDialog } from './FolderFormDialog';

/**
 * - `folder`        — a real, renameable/deletable folder of active agents
 * - `uncategorized` — active agents with no folder
 * - `archived`      — archived agents (restore-only; not a move target)
 */
type SectionKind = 'folder' | 'uncategorized' | 'archived';

interface FolderSectionProps {
    kind: SectionKind;
    /** Required when kind === 'folder'; ignored otherwise. */
    folder?: FolderResponse | null;
    workflows: WorkflowListResponse[];
    /** All folders, passed through so each row's "Move to folder" menu has targets. */
    allFolders?: FolderResponse[];
    /** Defaults to open only for Uncategorized; folders and Archived start collapsed. */
    defaultOpen?: boolean;
    /**
     * [.mark] Lots 10 and 12: the sub-folders, drawn under the agents; the groups of the folder
     * (a card per main agent), drawn above them; the roles of the agents (badges); and the number
     * of agents to show when the groups hold some of them.
     */
    children?: ReactNode;
    groupes?: ReactNode;
    roles?: Map<number, RoleAffiche>;
    /** [.mark] U3 (E30): the labels of the agents by id, drawn on the rows. */
    etiquettes?: Record<string, string[]>;
    nombre?: number;
}

export function FolderSection({
    kind,
    folder = null,
    workflows,
    allFolders = [],
    defaultOpen,
    children,
    groupes,
    roles,
    etiquettes,
    nombre,
}: FolderSectionProps) {
    const router = useRouter();
    const [open, setOpen] = useState(defaultOpen ?? kind === 'uncategorized');
    const [isRenaming, setIsRenaming] = useState(false);
    const [confirmDelete, setConfirmDelete] = useState(false);
    const [creatingSubFolder, setCreatingSubFolder] = useState(false);
    const isDeleting = false;

    const isFolder = kind === 'folder';
    const isArchived = kind === 'archived';
    const count = nombre ?? workflows.length;
    const title = isFolder ? (folder?.name ?? '') : isArchived ? 'Archived' : 'Uncategorized';

    const handleRename = async (name: string) => {
        if (!folder) return;
        const response = await renameFolderApiV1FolderFolderIdPut({
            path: { folder_id: folder.id },
            body: { name },
        });
        if (response.error) {
            const detail =
                (response.error as { detail?: string })?.detail ??
                'Failed to rename folder';
            notifier.echec({ fr: "Dossier non renommé. Réessayez.", en: "Folder not renamed. Try again." }, { erreur: detail });
            throw new Error(detail);
        }
        notifier.succes({ fr: "Dossier renommé.", en: "Folder renamed." });
        router.refresh();
    };

    // Suppression différée de 5 s (« Annuler ») : le dossier disparaît de l'écran, le serveur n'est appelé qu'ensuite.
    const [masque, setMasque] = useState(false);
    const handleDelete = () => {
        if (!folder) return;
        const { id, name } = folder;
        setConfirmDelete(false);
        setMasque(true);
        notifier.annulable(
            { fr: `Dossier « ${name} » supprimé.`, en: `Folder "${name}" deleted.` },
            {
                restaurer: () => setMasque(false),
                executer: async () => {
                    try {
                        const response = await deleteFolderApiV1FolderFolderIdDelete({ path: { folder_id: id } });
                        if (response.error) throw response.error;
                        router.refresh();
                    } catch (err) {
                        logger.error(`Error deleting folder: ${err}`);
                        setMasque(false);
                        notifier.echec({ fr: "Dossier non supprimé. Réessayez.", en: "Folder not deleted. Try again." }, { erreur: err });
                    }
                },
            },
        );
    };

    if (masque) return null;

    return (
        <div className="mb-3">
            <Collapsible open={open} onOpenChange={setOpen}>
                <div className="flex items-center gap-1">
                    <CollapsibleTrigger asChild>
                        <button
                            className="group flex flex-1 items-center gap-2.5 rounded-md px-2 py-2 text-left transition-colors hover:bg-accent"
                            aria-label={`Toggle ${title}`}
                        >
                            <ChevronRight
                                size={16}
                                className={cn(
                                    'shrink-0 text-muted-foreground transition-transform duration-200',
                                    open && 'rotate-90',
                                )}
                            />
                            {isFolder ? (
                                open ? (
                                    <FolderOpen size={17} className="shrink-0 text-muted-foreground" />
                                ) : (
                                    <FolderIcon size={17} className="shrink-0 text-muted-foreground" />
                                )
                            ) : isArchived ? (
                                <Archive size={16} className="shrink-0 text-muted-foreground" />
                            ) : (
                                <Inbox size={17} className="shrink-0 text-muted-foreground" />
                            )}
                            <span
                                className={cn('font-medium', !isFolder && 'text-muted-foreground')}
                            >
                                {title}
                            </span>
                            <Badge variant="secondary" className="ml-1 font-normal">
                                {count}
                            </Badge>
                        </button>
                    </CollapsibleTrigger>

                    {isFolder && (
                        <DropdownMenu>
                            <DropdownMenuTrigger asChild>
                                <Button
                                    variant="ghost"
                                    size="icon"
                                    className="h-8 w-8 text-muted-foreground"
                                    aria-label="Folder actions"
                                >
                                    <MoreVertical size={16} />
                                </Button>
                            </DropdownMenuTrigger>
                            <DropdownMenuContent align="end">
                                <DropdownMenuItem onClick={() => setIsRenaming(true)}>
                                    <Pencil size={14} className="mr-2" />
                                    Rename
                                </DropdownMenuItem>
                                {folder && (
                                    <ActionsSousDossier
                                        dossier={folder}
                                        tous={allFolders}
                                        ouvrirCreation={() => setCreatingSubFolder(true)}
                                    />
                                )}
                                <DropdownMenuItem
                                    onClick={() => setConfirmDelete(true)}
                                    className="text-destructive focus:text-destructive"
                                >
                                    <Trash2 size={14} className="mr-2" />
                                    Delete
                                </DropdownMenuItem>
                            </DropdownMenuContent>
                        </DropdownMenu>
                    )}
                </div>

                <CollapsibleContent className="data-[state=open]:animate-in data-[state=open]:fade-in-0 data-[state=open]:slide-in-from-top-1">
                    <div className="pl-7 pt-2">
                        {groupes && <div className="mb-3 space-y-4">{groupes}</div>}
                        {workflows.length > 0 ? (
                            <WorkflowTable
                                workflows={workflows}
                                showArchived={isArchived}
                                // Archived agents are restore-only — not a move target.
                                folders={isArchived ? undefined : allFolders}
                                currentFolderId={folder?.id ?? null}
                                roles={roles}
                                etiquettes={etiquettes}
                            />
                        ) : count > 0 || children ? null : (
                            <div className="rounded-lg border border-dashed bg-muted/30 p-6 text-center text-sm text-muted-foreground">
                                {isArchived
                                    ? 'No archived agents.'
                                    : isFolder
                                      ? 'This folder is empty. Use “Move to folder” on an agent to add it here.'
                                      : 'No uncategorized agents.'}
                            </div>
                        )}
                        {children && <div className="mt-2 space-y-1">{children}</div>}
                    </div>
                </CollapsibleContent>
            </Collapsible>

            {isFolder && folder && (
                <>
                    <FolderFormDialog
                        open={isRenaming}
                        onOpenChange={setIsRenaming}
                        title="Rename folder"
                        initialName={folder.name}
                        submitLabel="Rename"
                        onSubmit={handleRename}
                    />
                    <DialogueNouveauSousDossier
                        parentId={folder.id}
                        ouvert={creatingSubFolder}
                        onOuvertChange={setCreatingSubFolder}
                    />
                    <AlertDialog open={confirmDelete} onOpenChange={setConfirmDelete}>
                        <AlertDialogContent>
                            <AlertDialogHeader>
                                <AlertDialogTitle>Delete “{folder.name}”?</AlertDialogTitle>
                                <AlertDialogDescription>
                                    The {count} agent{count === 1 ? '' : 's'} in this folder
                                    won’t be deleted - they’ll move to Uncategorized.
                                    {folder.parent_id != null && <NoteSuppressionSousDossier />}
                                </AlertDialogDescription>
                            </AlertDialogHeader>
                            <AlertDialogFooter>
                                <AlertDialogCancel disabled={isDeleting}>
                                    Cancel
                                </AlertDialogCancel>
                                <AlertDialogAction
                                    onClick={(e) => {
                                        e.preventDefault();
                                        handleDelete();
                                    }}
                                    disabled={isDeleting}
                                    className="bg-destructive text-white hover:bg-destructive/90"
                                >
                                    {isDeleting ? 'Deleting...' : 'Delete folder'}
                                </AlertDialogAction>
                            </AlertDialogFooter>
                        </AlertDialogContent>
                    </AlertDialog>
                </>
            )}
        </div>
    );
}
