/**
 * [.mark] correctifs-apres-banc-v4, lot 5 (décision 3 d'Evan) : au clavier, les phrases que le CODE a dites s'affichent
 * en gris dans la transcription.
 *
 * Le serveur joint les sorties d'un tour par une ligne vide (`assistant_text`) et trace chaque phrase du code dans
 * `phrases_du_code` (`du_code: true`, `texte`, `tour`). L'écran grise les blocs de la réponse de l'agent dont le texte
 * est celui d'une entrée de la trace ; ce que dit le modèle reste tel quel.
 */
import { cleanup, render } from "@testing-library/react";
import { afterEach, describe, expect, it } from "vitest";

import { lirePhrasesDuCode } from "@/app/workflow/[workflowId]/components/workflow-tester/useTextChatSession";

import { conversationItemsFromTextChatTurns } from "./adapters/fromTextChatTurns";
import { ConversationItemView } from "./ConversationItemView";

afterEach(cleanup);

const SEP = String.fromCharCode(10, 10);

const tour = (texte: string) => ({
    id: "t1",
    created_at: "2026-10-21T10:00:00Z",
    user_message: { text: "Bonjour", created_at: "2026-10-21T10:00:00Z" },
    assistant_message: { text: texte, created_at: "2026-10-21T10:00:01Z" },
    events: [],
});

describe("[.mark] les phrases du code au clavier", () => {
    it("reads the sentences the code said from the trace, and only those flagged du_code", () => {
        expect(
            lirePhrasesDuCode({
                phrases_du_code: [
                    { motif: "outil_echoue", texte: "Je n'arrive pas à réserver.", du_code: true },
                    { motif: "x", texte: "Ancienne trace sans marque." },
                    "illisible",
                    { motif: "y", du_code: true },
                ],
            }),
        ).toEqual(["Je n'arrive pas à réserver."]);
        expect(lirePhrasesDuCode(undefined)).toEqual([]);
        expect(lirePhrasesDuCode({ phrases_du_code: "non" })).toEqual([]);
    });

    it("turns the block of the code grey, and leaves the model's blocks as they are", () => {
        const items = conversationItemsFromTextChatTurns(
            [tour(["Je regarde ça.", "Je n'arrive pas à réserver.", "Voulez-vous un autre créneau ?"].join(SEP))],
            ["Je n'arrive pas à réserver."],
        );
        const messages = items.filter((i) => i.kind === "message" && i.role === "assistant");
        expect(messages).toHaveLength(3);
        expect(messages.map((m) => (m.kind === "message" ? [m.text, m.tone ?? "default", m.duCode ?? false] : null))).toEqual([
            ["Je regarde ça.", "default", false],
            ["Je n'arrive pas à réserver.", "muted", true],
            ["Voulez-vous un autre créneau ?", "default", false],
        ]);
    });

    it("keeps one bubble for a message that holds no sentence of the code (as before), and an empty trace changes nothing", () => {
        const texte = ["Un.", "Deux."].join(SEP);
        const avant = conversationItemsFromTextChatTurns([tour(texte)]);
        const apres = conversationItemsFromTextChatTurns([tour(texte)], ["Autre phrase."]);
        expect(apres).toEqual(avant);
        const message = avant.find((i) => i.kind === "message" && i.role === "assistant");
        expect(message && message.kind === "message" ? message.id : null).toBe("t1-assistant");
        expect(message && message.kind === "message" ? message.text : null).toBe(texte);
    });

    it("draws the grey bubble with its label", () => {
        const items = conversationItemsFromTextChatTurns([tour("Je n'arrive pas à réserver.")], ["Je n'arrive pas à réserver."]);
        const message = items.find((i) => i.kind === "message" && i.role === "assistant");
        expect(message).toBeDefined();
        const { container } = render(<ConversationItemView item={message!} />);
        expect(container.querySelector("[data-phrase-du-code]")?.textContent).toBe("Sentence said by the code");
        expect(container.innerHTML).toContain("border-dashed");
        expect(container.textContent).toContain("Je n'arrive pas à réserver.");
    });
});
