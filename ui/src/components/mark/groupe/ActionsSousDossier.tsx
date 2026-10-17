"use client";

/**
 * [.mark] Chantier agents-specialises, lot 10 (A9) : ce que le menu d'un dossier ajoute pour les
 * sous-dossiers : « Nouveau sous-dossier » (une modale centrée qui demande le nom) et « Déplacer
 * vers » (un autre dossier, ou le premier niveau ; jamais le dossier lui-même ni ses descendants,
 * que la route refuserait). Les éléments sont rendus dans le menu d'origine du dossier.
 */
import { Check, Folder as FolderIcon, FolderInput, FolderPlus, Home } from "lucide-react";
import { useRouter } from "next/navigation";
import { toast } from "sonner";

import { createFolderApiV1FolderPost, moveFolderApiV1FolderFolderIdParentPut } from "@/client/sdk.gen";
import type { FolderResponse } from "@/client/types.gen";
import {
    DropdownMenuItem,
    DropdownMenuLabel,
    DropdownMenuSeparator,
    DropdownMenuSub,
    DropdownMenuSubContent,
    DropdownMenuSubTrigger,
} from "@/components/ui/dropdown-menu";
import { detailFromError } from "@/lib/apiError";

import { type Texte, useLangue } from "../langue/langue";
import { DialogueNom } from "./DialogueNom";
import { descendants } from "./liens-groupes";

const TEXTES = {
    nouveau: { en: "New sub-folder", fr: "Nouveau sous-dossier" },
    deplacer: { en: "Move to", fr: "Déplacer vers" },
    premierNiveau: { en: "Top level", fr: "Premier niveau" },
    titre: { en: "New sub-folder", fr: "Nouveau sous-dossier" },
    libelle: { en: "Sub-folder name", fr: "Nom du sous-dossier" },
    creer: { en: "Create", fr: "Créer" },
    cree: { en: "Sub-folder created.", fr: "Sous-dossier créé." },
    remonte: {
        en: "This is a sub-folder: its agents and its own sub-folders move up to the parent folder.",
        fr: "C'est un sous-dossier : ses agents et ses propres sous-dossiers remontent dans le dossier parent.",
    },
    deplace: { en: "Folder moved.", fr: "Dossier déplacé." },
    echecCreation: { en: "The sub-folder could not be created.", fr: "Le sous-dossier n'a pas pu être créé." },
    echecDeplacement: { en: "The folder could not be moved.", fr: "Le dossier n'a pas pu être déplacé." },
} satisfies Record<string, Texte>;

export const ActionsSousDossier = ({
    dossier,
    tous,
    ouvrirCreation,
}: {
    dossier: FolderResponse;
    tous: FolderResponse[];
    /** Ouvre la modale du nom (rendue hors du menu, qui se referme au clic). */
    ouvrirCreation: () => void;
}) => {
    const { t } = useLangue();
    const router = useRouter();
    const interdits = descendants(tous, dossier.id);
    const cibles = tous.filter((d) => !interdits.has(d.id));

    const deplacer = async (parentId: number | null) => {
        try {
            const reponse = await moveFolderApiV1FolderFolderIdParentPut({
                path: { folder_id: dossier.id },
                body: { parent_id: parentId },
            });
            if (reponse.error) {
                toast.error(detailFromError(reponse.error, t(TEXTES.echecDeplacement)));
                return;
            }
            toast.success(t(TEXTES.deplace));
            router.refresh();
        } catch {
            toast.error(t(TEXTES.echecDeplacement));
        }
    };

    return (
        <>
            <DropdownMenuItem onClick={ouvrirCreation} data-action="nouveau-sous-dossier">
                <FolderPlus size={14} className="mr-2" />
                {t(TEXTES.nouveau)}
            </DropdownMenuItem>
            <DropdownMenuSub>
                <DropdownMenuSubTrigger data-action="deplacer-le-dossier">
                    <FolderInput size={14} className="mr-2" />
                    {t(TEXTES.deplacer)}
                </DropdownMenuSubTrigger>
                <DropdownMenuSubContent className="w-52">
                    <DropdownMenuLabel>{t(TEXTES.deplacer)}</DropdownMenuLabel>
                    <DropdownMenuSeparator />
                    <DropdownMenuItem disabled={dossier.parent_id == null} onClick={() => void deplacer(null)}>
                        <Home size={14} className="mr-2" />
                        {t(TEXTES.premierNiveau)}
                        {dossier.parent_id == null && <Check size={14} className="ml-auto" />}
                    </DropdownMenuItem>
                    {cibles.map((cible) => (
                        <DropdownMenuItem
                            key={cible.id}
                            disabled={cible.id === dossier.parent_id}
                            onClick={() => void deplacer(cible.id)}
                        >
                            <FolderIcon size={14} className="mr-2" />
                            <span className="truncate">{cible.name}</span>
                            {cible.id === dossier.parent_id && <Check size={14} className="ml-auto shrink-0" />}
                        </DropdownMenuItem>
                    ))}
                </DropdownMenuSubContent>
            </DropdownMenuSub>
        </>
    );
};

/** Dit, sous la question de suppression, où vont les agents et les sous-dossiers d'un sous-dossier. */
export const NoteSuppressionSousDossier = () => {
    const { t } = useLangue();
    return (
        <span className="mt-2 block" data-note="suppression-sous-dossier">
            {t(TEXTES.remonte)}
        </span>
    );
};

export const DialogueNouveauSousDossier = ({
    parentId,
    ouvert,
    onOuvertChange,
}: {
    parentId: number;
    ouvert: boolean;
    onOuvertChange: (ouvert: boolean) => void;
}) => {
    const { t } = useLangue();
    const router = useRouter();
    return (
        <DialogueNom
            ouvert={ouvert}
            onOuvertChange={onOuvertChange}
            titre={TEXTES.titre}
            libelle={TEXTES.libelle}
            valider={TEXTES.creer}
            onValider={async (nom) => {
                try {
                    const reponse = await createFolderApiV1FolderPost({ body: { name: nom, parent_id: parentId } });
                    if (reponse.error) {
                        toast.error(detailFromError(reponse.error, t(TEXTES.echecCreation)));
                        throw new Error("creation");
                    }
                    toast.success(t(TEXTES.cree));
                    router.refresh();
                } catch (erreur) {
                    if (!(erreur instanceof Error && erreur.message === "creation")) toast.error(t(TEXTES.echecCreation));
                    throw erreur;
                }
            }}
        />
    );
};
