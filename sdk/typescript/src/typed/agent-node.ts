// GENERATED — do not edit by hand.
//
// Regenerate with `npm run codegen` against the target Dograh backend.
// Source of truth: the backend's model-backed node-spec catalog served
// from `/api/v1/node-types`.

/**
 * Each entry declares one variable to capture, with its name, data type, and extraction hint. Call outcomes are configured separately in workflow settings.
 */
export interface AgentNodeExtraction_variablesRow {
    /**
     * snake_case identifier used downstream.
     */
    name: string;
    /**
     * Data type of the extracted value.
     */
    type: "string" | "number" | "boolean";
    /**
     * Per-variable hint describing what to look for.
     */
    prompt?: string;
}

/**
 * Conversational step — the LLM runs one focused exchange.
 *
 * LLM hint: Mid-call step executed by the LLM. Most workflows are a chain of agent nodes connected by edges that describe transition conditions. Each agent node can invoke tools and reference documents.
 */
export interface AgentNode {
    type: "agentNode";
    /**
     * Short identifier for this step (e.g., 'Qualify Budget'). Appears in call logs and edge transition tools.
     */
    name?: string;
    /**
     * Agent system prompt for this step. Supports {{template_variables}} from extraction or pre-call fetch.
     */
    prompt: string;
    /**
     * What the agent says first when it arrives at this step. Used only when "Transitions in the reply" is on. Supports {{template_variables}}.
     */
    premiere_replique?: string;
    /**
     * Record fields this step gathers, in order of priority, separated by commas. Used only when "Show the model what is known and what is expected" is on in the agent's settings: the code then names the missing ones ("Still expected: …"), and the step's tools wait until they are known.
     */
    champs_etape?: string;
    /**
     * Agent (default): the model alone takes the exits. Collection: the code takes the first exit once every field of the step is gathered. Choice: the code takes the exit whose condition on the record holds, else the arbiter chooses. Free: the agent leads, the arbiter is the safety net.
     */
    qui_decide_du_passage?: "agent" | "collecte" | "choix" | "libre";
    /**
     * After the reply (default): the code passes once the agent has answered. Wait for the last field: when a single field is missing, the request waits (briefly) for the clerk to read the caller's last words, and the next step speaks at once.
     */
    moment_du_passage?: "apres_la_reponse" | "attendre_le_dernier_champ";
    /**
     * How long the agent's reply may wait for the clerk (Wait for the last field) or for the arbiter, before it leaves without them. Default 1.5.
     */
    delai_du_passage?: number;
    /**
     * A separate small model, asked as the caller finishes speaking, which exit (if any) their words call for. The agent's reply waits for it (bounded); when it is sure, the next step answers at once. Empty: off, except on a Choice or Free step.
     */
    arbitre?: boolean;
    /**
     * Lowest confidence at which the arbiter's choice is taken (0 to 1). Default 0.8.
     */
    seuil_de_l_arbitre?: number;
    /**
     * When true, the user can interrupt the agent mid-utterance. Set false for non-interruptible disclosures.
     */
    allow_interrupt?: boolean;
    /**
     * When true and a Global node exists, prepends the global prompt to this node's prompt at runtime.
     */
    add_global_prompt?: boolean;
    /**
     * When true, runs an LLM extraction pass for this node.
     */
    extraction_enabled?: boolean;
    /**
     * Overall instructions guiding variable extraction.
     */
    extraction_prompt?: string;
    /**
     * Each entry declares one variable to capture, with its name, data type, and extraction hint. Call outcomes are configured separately in workflow settings.
     */
    extraction_variables?: Array<AgentNodeExtraction_variablesRow>;
    /**
     * Tools the agent can invoke during this step.
     *
     * LLM hint: List of tool UUIDs from `list_tools`.
     */
    tool_uuids?: string[];
    /**
     * Documents the agent can reference during this step.
     *
     * LLM hint: List of document UUIDs from `list_documents`.
     */
    document_uuids?: string[];
}

/** Factory — sets `type` for you so you don't repeat the discriminator. */
export function agentNode(input: Omit<AgentNode, "type">): AgentNode {
    return { type: "agentNode", ...input };
}
