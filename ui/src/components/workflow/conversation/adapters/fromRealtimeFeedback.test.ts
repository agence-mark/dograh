import { describe, expect, it } from "vitest";

import type { RealtimeFeedbackEvent, TtfbKind } from "../types";
import { conversationItemsFromRealtimeFeedbackEvents, isLlmTtfb } from "./fromRealtimeFeedback";

const timestamp = "2026-09-23T10:00:00.000Z";

function ttfbEvent(seconds: number, kind?: TtfbKind): RealtimeFeedbackEvent {
    return {
        type: "rtf-ttfb-metric",
        payload: { ttfb_seconds: seconds, ...(kind ? { kind } : {}) },
        timestamp,
        turn: 1,
    };
}

describe("reasoning delay", () => {
    it("uses the LLM TTFB in stored runs, not the STT or TTS one around it", () => {
        const items = conversationItemsFromRealtimeFeedbackEvents([
            ttfbEvent(0.3, "stt"),
            ttfbEvent(0.8, "llm"),
            ttfbEvent(0.2, "tts"),
            { type: "rtf-bot-text", payload: { text: "Hello" }, timestamp, turn: 1 },
        ]);

        expect(items[0]).toMatchObject({ role: "assistant", reasoningDurationMs: 800 });
    });

    it("reads TTFB without a kind as the LLM's", () => {
        const items = conversationItemsFromRealtimeFeedbackEvents([
            ttfbEvent(0.8),
            { type: "rtf-bot-text", payload: { text: "Hello" }, timestamp, turn: 1 },
        ]);

        expect(items[0]).toMatchObject({ reasoningDurationMs: 800 });
    });

    // The live hook drops non-LLM TTFB with this before it reaches state.
    it("counts only LLM TTFB, and untagged TTFB as LLM", () => {
        expect(isLlmTtfb("llm")).toBe(true);
        expect(isLlmTtfb(undefined)).toBe(true);
        expect(isLlmTtfb("stt")).toBe(false);
        expect(isLlmTtfb("tts")).toBe(false);
    });
});

// [.mark] Plan postscriptum-note-d-abord (C12).
describe("transition written in the reply", () => {
    it("shows the written transition like a called one, before the step change", () => {
        const items = conversationItemsFromRealtimeFeedbackEvents([
            {
                type: "rtf-node-transition",
                payload: { node_id: "n2", node_name: "coordonnees", previous_node_name: "panne", porte_ecrite: "panne_decrite" },
                timestamp,
                turn: 2,
            },
        ]);
        expect(items[0]).toMatchObject({ kind: "tool-call", functionName: "panne_decrite", status: "completed" });
        expect(items[1]).toMatchObject({ kind: "node-transition", nodeName: "coordonnees" });
    });

    it("adds nothing for a transition without a written transition", () => {
        const items = conversationItemsFromRealtimeFeedbackEvents([
            { type: "rtf-node-transition", payload: { node_id: "n2", node_name: "coordonnees" }, timestamp, turn: 2 },
        ]);
        expect(items).toHaveLength(1);
        expect(items[0]).toMatchObject({ kind: "node-transition" });
    });
});
