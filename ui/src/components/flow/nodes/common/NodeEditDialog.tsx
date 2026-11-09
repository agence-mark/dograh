import { AlertCircle, Sparkles } from "lucide-react";
import { ReactNode, useCallback, useEffect, useRef, useState } from "react";

import { useWorkflowOptional } from "@/app/workflow/[workflowId]/contexts/WorkflowContext";
import { FlowNodeData } from "@/components/flow/types";
import { useLangue } from "@/components/mark/langue/langue";
import {
    AlertDialog,
    AlertDialogAction,
    AlertDialogCancel,
    AlertDialogContent,
    AlertDialogDescription,
    AlertDialogFooter,
    AlertDialogHeader,
    AlertDialogTitle,
} from "@/components/ui/alert-dialog";
import { Button } from "@/components/ui/button";
import { Dialog, DialogContent, DialogTitle } from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";

import { type AnnexeDeLEtape, ContexteAnnexes, type RegistreDesAnnexes } from "./annexes-de-l-etape";

interface NodeEditDialogProps {
    open: boolean;
    onOpenChange: (open: boolean) => void;
    nodeData: FlowNodeData;
    /** Le titre lu par les lecteurs d'écran (le nom de l'étape en est le titre visible). */
    title: string;
    children: ReactNode;
    onSave?: () => void;
    error?: string | null;
    isDirty?: boolean;
    /** Le type de l'étape, en petit devant son nom (« Début », « Étape », « Fin »…). */
    typeLabel?: string;
    /** Le nom de l'étape, modifiable dans l'en-tête ; absent, l'en-tête n'a pas de champ de nom. */
    nom?: string;
    onNomChange?: (nom: string) => void;
    /** « Demander au builder » : cite l'étape dans le panneau du builder. */
    onDemanderAuBuilder?: () => void;
}

/**
 * [.mark] K2 : la fenêtre d'un nœud, reprise de la maquette (`modale-noeud.tsx`, E55) : l'en-tête reste en haut (type, nom,
 * « Demander au builder »), le pied en bas (Annuler, Enregistrer), le milieu défile. Centrée, corps blanc.
 */
export const NodeEditDialog = ({
    open,
    onOpenChange,
    nodeData,
    title,
    children,
    onSave,
    error,
    isDirty = false,
    typeLabel,
    nom,
    onNomChange,
    onDemanderAuBuilder,
}: NodeEditDialogProps) => {
    const { t } = useLangue();
    const readOnly = useWorkflowOptional()?.readOnly ?? false;
    const [showDiscardAlert, setShowDiscardAlert] = useState(false);

    const handleClose = () => onOpenChange(false);

    // Les blocs de la fenêtre qui portent un réglage de l'agent : un seul pied les enregistre avec l'étape.
    const annexes = useRef<Map<string, AnnexeDeLEtape>>(new Map());
    const [annexesModifiees, setAnnexesModifiees] = useState(false);
    const [annexesInvalides, setAnnexesInvalides] = useState(false);
    const inscrireAnnexe = useCallback<RegistreDesAnnexes>((id, annexe) => {
        if (annexe) annexes.current.set(id, annexe);
        else annexes.current.delete(id);
        const toutes = [...annexes.current.values()];
        setAnnexesModifiees(toutes.some((a) => a.modifie));
        setAnnexesInvalides(toutes.some((a) => a.invalide));
    }, []);
    const modifie = isDirty || annexesModifiees;

    const handleSave = useCallback(async () => {
        for (const annexe of annexes.current.values()) {
            if (annexe.modifie && !(await annexe.enregistrer())) return;
        }
        if (onSave) {
            onSave();
        }
    }, [onSave]);

    // Intercept dialog close attempts when dirty
    const handleOpenChange = useCallback(
        (newOpen: boolean) => {
            if (!newOpen && modifie) {
                setShowDiscardAlert(true);
                return;
            }
            onOpenChange(newOpen);
        },
        [modifie, onOpenChange],
    );

    const handleConfirmDiscard = useCallback(() => {
        setShowDiscardAlert(false);
        onOpenChange(false);
    }, [onOpenChange]);

    // Handle Cmd+S / Ctrl+S keyboard shortcut to save
    useEffect(() => {
        if (!open || readOnly) return;

        const handleKeyDown = (e: KeyboardEvent) => {
            if ((e.metaKey || e.ctrlKey) && e.key === "s") {
                e.preventDefault();
                e.stopImmediatePropagation();
                handleSave();
            }
        };

        window.addEventListener("keydown", handleKeyDown, true);
        return () => window.removeEventListener("keydown", handleKeyDown, true);
    }, [open, readOnly, handleSave]);

    return (
        <Dialog open={open} onOpenChange={handleOpenChange}>
            <DialogContent className="flex max-h-[92vh] flex-col gap-0 overflow-hidden p-0 sm:max-w-3xl" data-fenetre="noeud" onOpenAutoFocus={(e) => e.preventDefault()}>
                <div className="shrink-0 px-6 pb-3 pr-12 pt-5">
                    <DialogTitle className="sr-only">{title}</DialogTitle>
                    <div className="flex items-center gap-2">
                        {typeLabel && <span className="text-[10px] font-medium uppercase tracking-wider text-muted-foreground">{typeLabel}</span>}
                        {onNomChange && (
                            <Input
                                value={nom ?? ""}
                                onChange={(e) => onNomChange(e.target.value)}
                                disabled={readOnly}
                                aria-label={t({ en: "Step name", fr: "Nom de l'étape" })}
                                className="h-8 max-w-72 border-transparent px-1 text-lg font-semibold shadow-none hover:border-input"
                            />
                        )}
                        <div className="ml-auto flex items-center gap-1">
                            {onDemanderAuBuilder && !readOnly && (
                                <Button variant="ghost" size="sm" onClick={onDemanderAuBuilder}>
                                    <Sparkles className="size-3.5 text-(--acc)" /> {t({ en: "Ask the builder", fr: "Demander au builder" })}
                                </Button>
                            )}
                        </div>
                    </div>
                    {nodeData.invalid && nodeData.validationMessage && (
                        <div className="mt-2 flex items-center gap-2 text-sm text-destructive">
                            <AlertCircle className="size-4" />
                            <span>{nodeData.validationMessage}</span>
                        </div>
                    )}
                </div>
                <div className="flex min-h-0 flex-1 flex-col bg-background">
                    <ContexteAnnexes.Provider value={inscrireAnnexe}>{children}</ContexteAnnexes.Provider>
                    {error && (
                        <div className="flex items-center gap-2 px-6 pb-4 text-sm text-destructive">
                            <AlertCircle className="size-4 shrink-0" />
                            <span>{error}</span>
                        </div>
                    )}
                </div>
                <div className="flex shrink-0 items-center justify-end gap-2 border-t px-6 py-3">
                    <Button variant="outline" onClick={modifie ? () => setShowDiscardAlert(true) : handleClose}>
                        {t({ en: "Cancel", fr: "Annuler" })}
                    </Button>
                    <Button onClick={() => void handleSave()} disabled={readOnly || annexesInvalides}>
                        {readOnly ? t({ en: "Read only", fr: "Lecture seule" }) : t({ en: "Save", fr: "Enregistrer" })}
                    </Button>
                </div>
            </DialogContent>

            {/* Discard changes confirmation dialog */}
            <AlertDialog open={showDiscardAlert} onOpenChange={setShowDiscardAlert}>
                <AlertDialogContent>
                    <AlertDialogHeader>
                        <AlertDialogTitle>{t({ en: "Discard changes?", fr: "Abandonner les changements ?" })}</AlertDialogTitle>
                        <AlertDialogDescription>
                            {t({ en: "You have unsaved changes. Discard them?", fr: "Des changements ne sont pas enregistrés. Les abandonner ?" })}
                        </AlertDialogDescription>
                    </AlertDialogHeader>
                    <AlertDialogFooter>
                        <AlertDialogCancel>{t({ en: "Keep editing", fr: "Continuer" })}</AlertDialogCancel>
                        <AlertDialogAction onClick={handleConfirmDiscard} className="bg-destructive text-white hover:bg-destructive/90">
                            {t({ en: "Discard", fr: "Abandonner" })}
                        </AlertDialogAction>
                    </AlertDialogFooter>
                </AlertDialogContent>
            </AlertDialog>
        </Dialog>
    );
};
