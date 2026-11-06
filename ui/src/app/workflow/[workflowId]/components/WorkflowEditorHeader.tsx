"use client";

/**
 * [.mark] La barre d'un agent, onglet Parcours (U3, E37, E46), refaite sur la maquette (K2) : le nom, le membre du groupe, les
 * onglets, puis version ⌄ · Essayer ⌄ · Builder IA · Publier · ⋮, tous posés dans la barre du cadre. Les actions sont celles de
 * `ActionsAgent`, branchées ici sur l'éditeur (essai, builder, enregistrement). L'historique des versions est l'onglet Versions.
 */
import { ReactFlowInstance } from "@xyflow/react";

import { WorkflowError } from "@/client/types.gen";
import { FlowEdge, FlowNode } from "@/components/flow/types";
import { ActionsAgent } from "@/components/mark/agent/ActionsAgent";
import { EnteteAgent } from "@/components/mark/agent/EnteteAgent";

export type ModeEssai = "audio" | "text" | "simulated";

interface WorkflowEditorHeaderProps {
    workflowName: string;
    isDirty: boolean;
    workflowValidationErrors: WorkflowError[];
    rfInstance: React.RefObject<ReactFlowInstance<FlowNode, FlowEdge> | null>;
    workflowId: number;
    workflowUuid?: string;
    saveWorkflow: (updateWorkflowDefinition?: boolean) => Promise<void>;
    user: { id: string; email?: string };
    onPhoneCallClick: () => void;
    /** Ouvre le panneau d'essai, sur l'onglet demandé. */
    onTestAgentClick: (mode: ModeEssai) => void;
    versionNumber: number | null;
    versionStatus: string | null;
    isViewingHistoricalVersion: boolean;
    onBackToDraft: () => void;
    hasDraft: boolean;
    onPublished: () => void;
    renameWorkflow: (newName: string) => Promise<void>;
    /** [.mark] builder-agent-vocal (lot 4) : le bouton « Builder IA », et pourquoi « Publier » est grisé. */
    builder?: {
        ouvert: boolean;
        onToggle: () => void;
        raisonDeBlocage: string | null;
    };
}

export const WorkflowEditorHeader = ({
    workflowName,
    isDirty,
    workflowValidationErrors,
    rfInstance,
    saveWorkflow,
    onPhoneCallClick,
    onTestAgentClick,
    versionNumber,
    versionStatus,
    isViewingHistoricalVersion,
    onBackToDraft,
    hasDraft,
    onPublished,
    workflowId,
    workflowUuid,
    renameWorkflow,
    builder,
}: WorkflowEditorHeaderProps) => (
    <EnteteAgent
        agentId={workflowId}
        onglet="parcours"
        nom={workflowName}
        actions={
            <ActionsAgent
                agentId={workflowId}
                nom={workflowName}
                workflowUuid={workflowUuid}
                versionNumero={versionNumber}
                versionStatut={versionStatus}
                aUnBrouillon={hasDraft}
                editeur={{
                    estModifie: isDirty,
                    erreursDuParcours: workflowValidationErrors.length,
                    rfInstance,
                    enregistrer: () => saveWorkflow(),
                    onEssayer: onTestAgentClick,
                    onTelephone: onPhoneCallClick,
                    onPublie: onPublished,
                    builder: builder ?? { ouvert: false, onToggle: () => {}, raisonDeBlocage: null },
                    renommer: renameWorkflow,
                    versionPassee: isViewingHistoricalVersion,
                    retourAuBrouillon: onBackToDraft,
                }}
            />
        }
    />
);
