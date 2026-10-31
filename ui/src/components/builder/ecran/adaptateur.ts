/**
 * [.mark] builder-agent-vocal (lot 4): the link between assistant-ui and the builder's route.
 *
 * assistant-ui (MIT) draws the conversation; this adapter is its only door to the server: it sends the person's
 * message to `POST /builder/conversation`, reads the stream, and turns each event into parts of the assistant
 * message (text, and one `tool-call` part per action of the builder, which the panel draws as a card).
 * Side effects of the events on the screen's own state (live operations, refreshed context, the saved draft) are
 * done here too, once, in order.
 */
import type { ChatModelAdapter, ThreadMessageLike } from "@assistant-ui/react";

import { lireLaConversationApiV1BuilderConversationWorkflowIdGet, parlerAuBuilderApiV1BuilderConversationPost } from "@/client";
import { detailFromError } from "@/lib/apiError";

import { ajouterAuxParties, type EvenementDuBuilder, lireLeFlux, type PartieDuMessage } from "./flux";
import type { GrapheDuBuilder } from "./graphe";
import { useBuilderEcran } from "./store";

export interface OptionsDeLAdaptateur {
    workflowId: number;
    lireLeGraphe: () => GrapheDuBuilder;
    recharger: () => Promise<boolean>;
    /** The words shown when the request itself fails (the screen's two languages are the panel's business). */
    echec: string;
}

function texteDe(message: { content: readonly { type: string; text?: string }[] }): string {
    return message.content
        .filter((p) => p.type === "text")
        .map((p) => p.text ?? "")
        .join("\n")
        .trim();
}

/** The effects of an event on the screen. Never throws: the conversation goes on. */
export async function appliquerLEvenement(evenement: EvenementDuBuilder, options: OptionsDeLAdaptateur): Promise<void> {
    const magasin = useBuilderEcran.getState();
    switch (evenement.type) {
        case "operation":
            magasin.recevoirUneOperation(evenement.operation, options.lireLeGraphe());
            break;
        case "resultat":
            await magasin.rafraichirLeContexte(options.workflowId);
            break;
        case "carte":
            if (evenement.carte.type === "changements") {
                const graphe = options.lireLeGraphe();
                await options.recharger();
                const carte = evenement.carte as { version?: number; nombre_operations?: number; noeuds?: number; liaisons?: number };
                useBuilderEcran.getState().brouillonEnregistre(
                    { version: carte.version, nombreOperations: carte.nombre_operations, noeuds: carte.noeuds, liaisons: carte.liaisons },
                    graphe,
                );
            }
            break;
        default:
            break;
    }
}

export function creerLAdaptateur(options: OptionsDeLAdaptateur): ChatModelAdapter {
    return {
        async *run({ messages, abortSignal }) {
            const dernier = [...messages].reverse().find((m) => m.role === "user");
            const message = dernier ? texteDe(dernier) : "";
            if (!message) return;
            const magasin = useBuilderEcran.getState();
            magasin.marquerEnCours(true);
            let parties: PartieDuMessage[] = [];
            try {
                const reponse = await parlerAuBuilderApiV1BuilderConversationPost({
                    body: { workflow_id: options.workflowId, message },
                    parseAs: "stream",
                    signal: abortSignal,
                });
                if (reponse.error || !reponse.data) {
                    yield { content: [{ type: "text", text: detailFromError(reponse.error, options.echec) }] };
                    return;
                }
                for await (const evenement of lireLeFlux(reponse.data as ReadableStream<Uint8Array>)) {
                    parties = ajouterAuxParties(parties, evenement);
                    await appliquerLEvenement(evenement, options);
                    yield { content: parties as never };
                }
            } catch (erreur) {
                if ((erreur as { name?: string })?.name === "AbortError") return;
                yield { content: [...(parties as never[]), { type: "text", text: `\n${options.echec}` }] as never };
            } finally {
                useBuilderEcran.getState().marquerEnCours(false);
                void useBuilderEcran.getState().rafraichirLeContexte(options.workflowId);
            }
        },
    };
}

/** The conversation already kept for this agent, as assistant-ui's initial messages. */
export async function lireLHistorique(workflowId: number): Promise<ThreadMessageLike[]> {
    const reponse = await lireLaConversationApiV1BuilderConversationWorkflowIdGet({ path: { workflow_id: workflowId } });
    if (reponse.error || !reponse.data) return [];
    const messages: ThreadMessageLike[] = [];
    for (const m of reponse.data.messages as { role: string; content?: string; appels?: { id: string; nom: string; arguments: Record<string, unknown> }[] }[]) {
        if (m.role === "user") {
            // The state block the server adds in front of a message is not the person's words.
            const propre = String(m.content ?? "").split("[Message de la personne]\n").pop() ?? "";
            messages.push({ role: "user", content: propre });
        } else if (m.role === "assistant") {
            const parties: unknown[] = [];
            if (m.content) parties.push({ type: "text", text: m.content });
            for (const a of m.appels ?? []) {
                parties.push({
                    type: "tool-call",
                    toolCallId: a.id,
                    toolName: a.nom,
                    args: a.arguments,
                    argsText: JSON.stringify(a.arguments),
                    result: { historique: true },
                });
            }
            if (parties.length) messages.push({ role: "assistant", content: parties as never });
        }
    }
    return messages;
}
