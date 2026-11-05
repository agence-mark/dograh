export enum NodeType {
    START_CALL = 'startCall',
    AGENT_NODE = 'agentNode',
    END_CALL = 'endCall',
    GLOBAL_NODE = 'globalNode',
    TRIGGER = 'trigger',
    WEBHOOK = 'webhook',
    QA = 'qa',
}

export type FlowNodeData = {
    prompt?: string;
    name: string;
    is_start?: boolean;
    is_end?: boolean;
    invalid?: boolean;
    validationMessage?: string | null;
    selected_through_edge?: boolean;
    hovered_through_edge?: boolean;
    runtime_active?: boolean;
    /** [.mark] Sous-lot 20 : part des appels lus qui ont traversé l'étape (posée à l'affichage, jamais enregistrée). */
    stats_part?: number;
    /** N3a : la latence de l'étape sur les appels lus (moyenne pondérée et pire tour, en ms), quand elle a été mesurée. */
    stats_latence?: { moyenne_ms: number; pire_ms: number };
    allow_interrupt?: boolean;
    extraction_enabled?: boolean;
    extraction_prompt?: string;
    extraction_variables?: ExtractionVariable[];
    add_global_prompt?: boolean;
    greeting?: string;
    greeting_type?: 'text' | 'audio';
    greeting_recording_id?: string;
    delayed_start?: boolean;
    delayed_start_duration?: number;
    // Pre-call data fetch (StartCall only)
    pre_call_fetch_mode?: 'disabled' | 'always' | 'inbound' | 'outbound';
    pre_call_fetch_url?: string;
    pre_call_fetch_credential_uuid?: string;
    pre_call_fetch_remplace?: string;
    // Trigger node specific
    trigger_path?: string;
    // Webhook node specific
    enabled?: boolean;
    http_method?: 'GET' | 'POST' | 'PUT' | 'PATCH' | 'DELETE';
    endpoint_url?: string;
    credential_uuid?: string;
    custom_headers?: Array<{ key: string; value: string }>;
    payload_template?: Record<string, unknown>;
    // QA node specific
    qa_enabled?: boolean;
    qa_system_prompt?: string;
    qa_use_workflow_llm?: boolean;
    qa_provider?: string;
    qa_model?: string;
    qa_api_key?: string;
    qa_min_call_duration?: number;
    qa_voicemail_calls?: boolean;
    qa_sample_rate?: number;
    // Tools - array of tool UUIDs that can be invoked by this node
    tool_uuids?: string[];
    // Per-node MCP function allowlist: { toolUuid: [raw MCP tool name, ...] }.
    // Default-none: a toolUuid absent here (or mapped to []) exposes zero
    // functions of that MCP server on this node.
    mcp_tool_filters?: Record<string, string[]>;
    // Documents - array of knowledge base document UUIDs that can be referenced by this node
    document_uuids?: string[];
    [key: string]: unknown;
}

export type FlowNode = {
    id: string;
    type: string;
    position: { x: number; y: number };
    data: FlowNodeData;
    measured?: {
        width: number;
        height: number;
    };
    selected?: boolean;
    dragging?: boolean;
};

// [.mark] passages-fiables (lot A) : la condition d'une porte sur la fiche (étape complète, ou champ = valeur).
export type EdgeRecordCondition = {
    etape_complete?: boolean;
    champ?: string;
    vaut?: string;
    /** [.mark] Partie 3, sous-lot 21 : la même condition, étendue (`components/mark/graphe/conditions-de-porte.ts`). */
    regles?: RegleDePorte[];
    combien?: 'toutes' | 'au_moins_une';
    sinon?: boolean;
    toujours?: boolean;
};

/** [.mark] Sous-lot 21 : une règle de la condition d'une porte (source, champ, comparaison, valeur). */
export type RegleDePorte = {
    source: 'fiche' | 'etape' | 'outil' | 'heure' | 'etablissement' | 'variable';
    champ?: string;
    comparaison: string;
    valeur?: string;
};

export type FlowEdgeData = {
    condition: string;
    label: string;
    condition_sur_la_fiche?: EdgeRecordCondition;
    /** [.mark] L6+ : l'identifiant stable de la porte (le nom de la fonction), gardé quand on renomme le libellé. */
    identifiant?: string;
    transition_speech?: string;
    transition_speech_type?: 'text' | 'audio';
    transition_speech_recording_id?: string;
    invalid?: boolean;
    validationMessage?: string | null;
}

export type FlowEdge = {
    id: string;
    source: string;
    target: string;
    type?: string;
    data: FlowEdgeData;
    animated?: boolean;
    invalid?: boolean;
};

export interface WorkflowDefinition {
    nodes: FlowNode[];
    edges: FlowEdge[];
    viewport: {
        x: number;
        y: number;
        zoom: number;
    };
}

export interface WorkflowData {
    name: string;
    workflow_definition: WorkflowDefinition;
}

export type WorkflowValidationError = {
    kind: 'node' | 'edge' | 'workflow';
    id: string;
    field: string;
    message: string;
}

export type ExtractionVariable = {
    name: string;
    type: 'string' | 'number' | 'boolean';
    prompt?: string;
};

// Credential types for webhook authentication
export type CredentialType = 'none' | 'api_key' | 'bearer_token' | 'basic_auth' | 'custom_header';

export interface Credential {
    uuid: string;
    name: string;
    description?: string;
    credential_type: CredentialType;
    created_at: string;
    updated_at: string;
}
