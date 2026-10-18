import { createContext, useContext } from 'react';

import type { DocumentResponseSchema, ToolResponse } from '@/client/types.gen';
import type { RecordingResponseSchema } from '@/client/types.gen';

interface WorkflowContextType {
    saveWorkflow: (updateWorkflowDefinition?: boolean) => Promise<void>;
    documents?: DocumentResponseSchema[];
    tools?: ToolResponse[];
    updateTool?: (
        toolUuid: string,
        updater: (tool: ToolResponse) => ToolResponse,
    ) => void;
    recordings?: RecordingResponseSchema[];
    readOnly?: boolean;
    /** [.mark] Lot E d'agent-leger-greffier: the agent's record fields (step labels). */
    champsFiche?: string[];
    /** [.mark] Lot 12 (agents-specialises): the id of this agent. */
    workflowId?: number;
    /** [.mark] Lot 12: the main agent of this agent when it is a specialised one (« Back to the main agent »). */
    agentPrincipalId?: number | null;
    /** [.mark] Lot 12: this agent is the main agent of a group (its end step gets the list of closing sentences). */
    estPrincipal?: boolean;
    /** [.mark] modules-et-cerveaux (lot 5): the agent's background work is on (the steps' « Background work » box). */
    travailActif?: boolean;
    /** [.mark] Lot 12: a tool just created from the node window (the « Agent » brick) joins the list. */
    ajouterOutil?: (tool: ToolResponse) => void;
}

const WorkflowContext = createContext<WorkflowContextType | undefined>(undefined);

export const WorkflowProvider = WorkflowContext.Provider;

export const useWorkflow = () => {
    const context = useContext(WorkflowContext);
    if (!context) {
        throw new Error('useWorkflow must be used within a WorkflowProvider');
    }
    return context;
};

// Optional hook that doesn't throw if context is not available
export const useWorkflowOptional = () => {
    return useContext(WorkflowContext);
};
