/**
 * [.mark] A simulated call followed live (chantier direct-et-passe-muette, lot A, P2, P4, P5).
 *
 * The questions this file answers:
 *
 *     Are the caller's interim and final transcriptions folded into one line, and the agent's
 *     pieces into one bubble? Is the live view read from the last event seen, until the call ends,
 *     then pointed at the saved transcript? Does a live view that cannot be read say so?
 */
import { render, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import type { RealtimeFeedbackEvent } from "@/components/workflow/conversation/types";

import { DirectAppelSimule, regrouperLeDirect } from "./appelant-simule/DirectAppelSimule";

const m = vi.hoisted(() => ({ direct: vi.fn() }));
vi.mock("@/client", () => ({
    directAppelSimuleApiV1AppelSimuleRunsWorkflowRunIdDirectGet: (...a: unknown[]) => m.direct(...a),
}));

const evenement = (type: string, payload: Record<string, unknown>, i: number): RealtimeFeedbackEvent =>
    ({ type, payload, timestamp: `2026-10-06T10:00:0${i}.000Z`, turn: null }) as unknown as RealtimeFeedbackEvent;

beforeEach(() => {
    vi.clearAllMocks();
    // jsdom has no scrolling; Dograh's timeline scrolls to the last line.
    Element.prototype.scrollIntoView = vi.fn();
});

describe("[.mark] folding the live channel", () => {
    it("folds the caller's pieces into one line, keeps what is being said, and leaves out mute signals", () => {
        const plie = regrouperLeDirect([
            evenement("rtf-user-transcription", { text: "J'ai une", final: false }, 0),
            evenement("rtf-user-transcription", { text: "J'ai une panne", final: true }, 1),
            evenement("rtf-user-mute-started", {}, 2),
            evenement("rtf-user-transcription", { text: "de poêle", final: true }, 3),
            evenement("rtf-bot-text", { text: "D'accord." }, 4),
            evenement("rtf-user-transcription", { text: "Je m'appelle", final: false }, 5),
        ]);
        expect(plie.map((e) => [e.type, e.payload.text, e.payload.final])).toEqual([
            ["rtf-user-transcription", "J'ai une panne de poêle", true],
            ["rtf-bot-text", "D'accord.", undefined],
            ["rtf-user-transcription", "Je m'appelle", false],
        ]);
    });
});

describe("[.mark] the live view of a simulated call", () => {
    it("reads from the last event seen until the call ends, then points at the saved transcript", async () => {
        m.direct
            .mockResolvedValueOnce({
                data: {
                    evenements: [
                        evenement("rtf-user-transcription", { text: "Bonjour, j'ai une panne", final: true }, 0),
                        evenement("rtf-bot-text", { text: "Bonjour," }, 1),
                        evenement("rtf-bot-text", { text: "je note votre panne." }, 2),
                    ],
                    suivant: 3,
                    fini: false,
                },
            })
            .mockResolvedValueOnce({ data: { evenements: [], suivant: 4, fini: true } });
        render(<DirectAppelSimule runId={1201} workflowId={34} />);
        expect(await screen.findByText("Bonjour, j'ai une panne")).toBeTruthy();
        expect(screen.getByText("Bonjour, je note votre panne.")).toBeTruthy();
        expect(screen.getByText("Live transcript")).toBeTruthy();
        await waitFor(() => expect(screen.getByText("Call transcript")).toBeTruthy(), { timeout: 3000 });
        expect(m.direct.mock.calls.map((c) => c[0])).toEqual([
            { path: { workflow_run_id: 1201 }, query: { depuis: 0 } },
            { path: { workflow_run_id: 1201 }, query: { depuis: 3 } },
        ]);
        const lien = screen.getByText("Saved transcript and verdict: run window") as HTMLAnchorElement;
        expect(lien.getAttribute("href")).toBe("/workflow/34/run/1201");
        await new Promise((r) => setTimeout(r, 1300));
        expect(m.direct).toHaveBeenCalledTimes(2);
    });

    it("says when the live view cannot be read, and keeps trying", async () => {
        m.direct
            .mockResolvedValueOnce({ error: { detail: "Live view unavailable; the call goes on and its transcript is saved at the end." } })
            .mockResolvedValueOnce({ data: { evenements: [], suivant: 0, fini: true } });
        render(<DirectAppelSimule runId={7} workflowId={34} />);
        expect((await screen.findByRole("alert")).textContent).toContain("Live view unavailable");
        await waitFor(() => expect(screen.queryByRole("alert")).toBeNull(), { timeout: 3000 });
    });
});

describe("[.mark] the live view, when things go wrong (review of lot A)", () => {
    it("keeps reading after a network cut, and says when the live view was truncated", async () => {
        m.direct
            .mockRejectedValueOnce(new TypeError("Failed to fetch"))
            .mockResolvedValueOnce({
                data: {
                    evenements: [
                        evenement("rtf-bot-text", { text: "Bonjour." }, 0),
                        evenement("mark-direct-tronque", { max: 2000 }, 1),
                    ],
                    suivant: 2,
                    fini: true,
                },
            });
        render(<DirectAppelSimule runId={8} workflowId={34} />);
        expect((await screen.findByRole("alert")).textContent).toContain("Live view unavailable");
        expect(await screen.findByText(/Live view truncated/, undefined, { timeout: 3000 })).toBeTruthy();
        expect(screen.queryByRole("alert")).toBeNull();
        expect(screen.getByText("Bonjour.")).toBeTruthy();
    });
});
