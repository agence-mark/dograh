"use client";

import { X } from "lucide-react";
import Link from "next/link";
import { useMemo } from "react";

import type { DocumentResponseSchema } from "@/client/types.gen";
import { type Texte, useLangue } from "@/components/mark/langue/langue";
import { Info } from "@/components/mark/studio/marques";
import { Checkbox } from "@/components/ui/checkbox";
import { Label } from "@/components/ui/label";
import { Popover, PopoverContent, PopoverTrigger } from "@/components/ui/popover";

interface DocumentSelectorProps {
    value: string[];
    onChange: (uuids: string[]) => void;
    documents: DocumentResponseSchema[];
    disabled?: boolean;
    label?: string;
    description?: string;
    showLabel?: boolean;
}

const T = {
    ajouter: { en: "document", fr: "document" },
    aucun: {
        en: "No document available. Add documents to the knowledge base first.",
        fr: "Aucun document disponible. Ajoutez d'abord des documents à la base de connaissances.",
    },
    gerer: { en: "Manage documents", fr: "Gérer les documents" },
    retirer: { en: "Remove", fr: "Retirer" },
} satisfies Record<string, Texte>;

/**
 * [.mark] K2b : les documents d'une étape comme la maquette les dessine (`modale-noeud.tsx`) : les documents choisis en
 * pastilles et « + document » qui ouvre la liste. Les valeurs écrites sont celles d'avant (les identifiants de documents).
 */
export const DocumentSelector = ({
    value,
    onChange,
    documents,
    disabled = false,
    label = "Knowledge Base Documents",
    description = "Select documents that the agent can reference during conversations.",
    showLabel = true,
}: DocumentSelectorProps) => {
    const { t } = useLangue();
    // Only show completed documents
    const completedDocuments = useMemo(() => documents.filter((doc) => doc.processing_status === "completed"), [documents]);
    const choisis = completedDocuments.filter((d) => value.includes(d.document_uuid));

    const handleToggle = (documentUuid: string, checked: boolean) => {
        if (checked) onChange([...value, documentUuid]);
        else onChange(value.filter((uuid) => uuid !== documentUuid));
    };

    return (
        <div className="grid gap-1.5" data-selecteur-documents>
            {showLabel && (
                <Label className="flex items-center gap-1.5">
                    {label}
                    {description && <Info>{description}</Info>}
                </Label>
            )}
            <div className="flex flex-wrap items-center gap-2">
                {choisis.map((doc) => (
                    <span key={doc.document_uuid} className="inline-flex h-6 items-center gap-1 rounded-md border px-2 text-xs">
                        {doc.filename}
                        <button
                            type="button"
                            disabled={disabled}
                            aria-label={`${t(T.retirer)} ${doc.filename}`}
                            className="cursor-pointer text-muted-foreground hover:text-foreground"
                            onClick={() => handleToggle(doc.document_uuid, false)}
                        >
                            <X className="size-3" />
                        </button>
                    </span>
                ))}
                <Popover>
                    <PopoverTrigger asChild>
                        <button
                            type="button"
                            disabled={disabled}
                            className="inline-flex h-6 cursor-pointer items-center gap-1 rounded-md px-2 text-sm text-muted-foreground hover:font-medium hover:text-foreground"
                        >
                            + {t(T.ajouter)}
                        </button>
                    </PopoverTrigger>
                    <PopoverContent align="start" className="w-80 p-1">
                        {completedDocuments.length === 0 && <p className="px-3 py-2 text-sm text-muted-foreground">{t(T.aucun)}</p>}
                        <div className="max-h-64 overflow-y-auto">
                            {completedDocuments.map((doc) => (
                                <label key={doc.document_uuid} className="flex cursor-pointer items-center gap-3 rounded-md px-3 py-2 hover:bg-muted/50">
                                    <Checkbox
                                        checked={value.includes(doc.document_uuid)}
                                        disabled={disabled}
                                        onCheckedChange={(checked) => handleToggle(doc.document_uuid, checked === true)}
                                    />
                                    <span className="min-w-0 flex-1 truncate text-sm">{doc.filename}</span>
                                </label>
                            ))}
                        </div>
                        <Link href="/files" target="_blank" className="block px-3 py-2 text-sm text-muted-foreground hover:font-medium hover:text-foreground">
                            {t(T.gerer)}
                        </Link>
                    </PopoverContent>
                </Popover>
            </div>
        </div>
    );
};
