'use client';

import { FolderPlus } from 'lucide-react';
import { useRouter } from 'next/navigation';
import { useState } from 'react';
import { notifier } from "@/components/mark/notifications";

import { createFolderApiV1FolderPost } from '@/client/sdk.gen';
import { Button } from '@/components/ui/button';

import { FolderFormDialog } from './FolderFormDialog';

export function CreateFolderButton() {
    const router = useRouter();
    const [isOpen, setIsOpen] = useState(false);

    const handleCreate = async (name: string) => {
        const response = await createFolderApiV1FolderPost({ body: { name } });
        if (response.error) {
            // 409 = duplicate name; surface the server's message when present.
            const detail =
                (response.error as { detail?: string })?.detail ??
                'Failed to create folder';
            notifier.echec({ fr: "Dossier non créé. Réessayez.", en: "Folder not created. Try again." }, { erreur: detail });
            throw new Error(detail);
        }
        notifier.succes({ fr: `Dossier « ${name} » créé.`, en: `Folder "${name}" created.` });
        router.refresh();
    };

    return (
        <>
            <Button variant="outline" onClick={() => setIsOpen(true)}>
                <FolderPlus className="w-4 h-4 mr-2" />
                New Folder
            </Button>
            <FolderFormDialog
                open={isOpen}
                onOpenChange={setIsOpen}
                title="Create folder"
                submitLabel="Create"
                onSubmit={handleCreate}
            />
        </>
    );
}
