import type { ConversationItem } from "../types";

interface TextChatMessageLike {
    text?: string;
    created_at?: string;
}

interface TextChatEventLike {
    type?: unknown;
    payload?: unknown;
    created_at?: unknown;
}

interface TextChatTurnLike {
    id: string;
    status?: string;
    created_at?: string;
    user_message?: TextChatMessageLike | null;
    assistant_message?: TextChatMessageLike | null;
    events?: Array<Record<string, unknown>>;
}

function asRecord(value: unknown) {
    return value && typeof value === "object" ? (value as Record<string, unknown>) : null;
}

function asString(value: unknown) {
    return typeof value === "string" ? value : undefined;
}

function conversationItemsFromTextChatEvents(
    events: Array<Record<string, unknown>>,
    turnId: string,
    fallbackTimestamp?: string,
) {
    const items: ConversationItem[] = [];
    const toolCallIndexById = new Map<string, number>();

    events.forEach((rawEvent, index) => {
        const event = rawEvent as TextChatEventLike;
        const eventType = asString(event.type);
        const payload = asRecord(event.payload);
        if (!eventType || !payload) {
            return;
        }

        const timestamp = asString(event.created_at) ?? fallbackTimestamp;

        if (eventType === "node_transition") {
            const nodeName = asString(payload.node_name) ?? "Node";
            // [.mark] Plan postscriptum-note-d-abord (C12): the transition written in the reply.
            const porteEcrite = asString(payload.porte_ecrite);
            if (porteEcrite) {
                items.push({
                    kind: "tool-call",
                    id: `${turnId}-porte-${index}`,
                    turnId,
                    timestamp,
                    functionName: porteEcrite,
                    status: "completed",
                    result: "written in the reply",
                });
            }
            items.push({
                kind: "node-transition",
                id: `${turnId}-node-${index}`,
                turnId,
                timestamp,
                nodeId: asString(payload.node_id),
                nodeName,
                previousNodeId: asString(payload.previous_node_id),
                previousNodeName: asString(payload.previous_node_name),
                allowInterrupt: typeof payload.allow_interrupt === "boolean" ? payload.allow_interrupt : undefined,
                // [.mark] Chantier agents-specialises (lot 2): a handoff names the agent.
                agentName: asString(payload.agent),
            });
            return;
        }

        if (eventType === "execution_error") {
            items.push({
                kind: "notice",
                id: `${turnId}-error-${index}`,
                turnId,
                timestamp,
                tone: "error",
                title: "Execution Error",
                text: asString(payload.message) ?? "Execution error",
                fatal: true,
            });
            return;
        }

        if (eventType === "tool_call_started") {
            const functionName = asString(payload.function_name) ?? "tool";
            const toolCallId = asString(payload.tool_call_id);
            items.push({
                kind: "tool-call",
                id: toolCallId ?? `${turnId}-tool-${index}`,
                turnId,
                timestamp,
                functionName,
                toolCallId,
                status: "running",
                arguments: payload.arguments,
            });
            if (toolCallId) {
                toolCallIndexById.set(toolCallId, items.length - 1);
            }
            return;
        }

        if (eventType === "tool_call_result") {
            const functionName = asString(payload.function_name) ?? "tool";
            const toolCallId = asString(payload.tool_call_id);
            const existingIndex = toolCallId ? toolCallIndexById.get(toolCallId) : undefined;

            if (existingIndex !== undefined) {
                const existingItem = items[existingIndex];
                if (existingItem?.kind === "tool-call") {
                    items[existingIndex] = {
                        ...existingItem,
                        status: "completed",
                        result: payload.result,
                    };
                }
                return;
            }

            items.push({
                kind: "tool-call",
                id: toolCallId ?? `${turnId}-tool-result-${index}`,
                turnId,
                timestamp,
                functionName,
                toolCallId,
                status: "completed",
                result: payload.result,
            });
        }
    });

    return items;
}

/**
 * [.mark] correctifs-apres-banc-v4, lot 5 (décision 3): the blocks of the agent's message (joined by a blank line
 * by the server) that are a sentence said by the CODE, found in the session's `phrases_du_code` trace, are shown
 * in grey. Consecutive blocks of the same nature stay in one bubble.
 */
/** Les sorties d'un tour sont jointes par une ligne vide (`text_chat_runner.py`, `assistant_text`). */
const SEPARATEUR_DE_BLOCS = String.fromCharCode(10, 10);

function messagesDeLAgent(turn: TextChatTurnLike, phrasesDuCode: Set<string>): ConversationItem[] {
    const texte = turn.assistant_message?.text ?? "";
    const timestamp = turn.assistant_message?.created_at ?? turn.created_at;
    const blocs = texte.split(SEPARATEUR_DE_BLOCS);
    const groupes: Array<{ duCode: boolean; blocs: string[] }> = [];
    for (const bloc of blocs) {
        const duCode = phrasesDuCode.size > 0 && phrasesDuCode.has(bloc.trim());
        const dernier = groupes.at(-1);
        if (dernier && dernier.duCode === duCode) dernier.blocs.push(bloc);
        else groupes.push({ duCode, blocs: [bloc] });
    }
    return groupes.map((groupe, i) => ({
        kind: "message" as const,
        id: groupes.length === 1 ? `${turn.id}-assistant` : `${turn.id}-assistant-${i}`,
        turnId: turn.id,
        timestamp,
        role: "assistant" as const,
        text: groupe.blocs.join(SEPARATEUR_DE_BLOCS),
        ...(groupe.duCode ? { tone: "muted" as const, duCode: true } : {}),
    }));
}

export function conversationItemsFromTextChatTurns(turns: TextChatTurnLike[], phrasesDuCode: string[] = []) {
    const dites = new Set(phrasesDuCode.map((p) => p.trim()).filter((p) => p !== ""));
    const items: ConversationItem[] = [];

    turns.forEach((turn) => {
        if (turn.user_message?.text) {
            items.push({
                kind: "message",
                id: `${turn.id}-user`,
                turnId: turn.id,
                timestamp: turn.user_message.created_at ?? turn.created_at,
                role: "user",
                text: turn.user_message.text,
            });
        }

        items.push(
            ...conversationItemsFromTextChatEvents(
                turn.events ?? [],
                turn.id,
                turn.created_at,
            ),
        );

        if (turn.assistant_message?.text) {
            items.push(...messagesDeLAgent(turn, dites));
            return;
        }

        if (turn.status === "failed") {
            items.push({
                kind: "message",
                id: `${turn.id}-assistant-failed`,
                turnId: turn.id,
                timestamp: turn.created_at,
                role: "assistant",
                text: "Agent turn failed",
                tone: "muted",
            });
        }
    });

    return items;
}
