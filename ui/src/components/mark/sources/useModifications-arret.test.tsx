/**
 * [.mark] R3 mineur 8 : le flux des modifications ne se relance pas sans fin sur « non connecté », « interdit », « introuvable »,
 * mais continue d'essayer après une coupure passagère (erreur 5xx).
 */
import { act, cleanup, render } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

const m = vi.hoisted(() => ({ flux: vi.fn() }));
vi.mock("@/lib/auth", () => ({ useAuth: () => ({ user: { id: 1 }, loading: false }) }));
vi.mock("@/client", () => ({ suivreLesModificationsApiV1BuilderLiveGet: (...a: unknown[]) => m.flux(...a) }));

import { useModifications } from "./useModifications";

function Ecoute() {
    useModifications("agent:1", () => undefined);
    return null;
}

beforeEach(() => {
    vi.useFakeTimers();
    m.flux.mockReset();
});
afterEach(() => {
    cleanup();
    vi.useRealTimers();
});

const laisserPasser = async () => {
    for (let i = 0; i < 6; i++) await act(async () => void (await vi.advanceTimersByTimeAsync(60_000)));
};

describe("flux des modifications", () => {
    it.each([401, 403, 404])("s'arrête sur %i : une seule demande", async (statut) => {
        m.flux.mockResolvedValue({ error: { detail: "non" }, response: { status: statut } });
        render(<Ecoute />);
        await laisserPasser();
        expect(m.flux).toHaveBeenCalledTimes(1);
    });

    it("continue d'essayer après une coupure passagère (503)", async () => {
        m.flux.mockResolvedValue({ error: { detail: "coupure" }, response: { status: 503 } });
        render(<Ecoute />);
        await laisserPasser();
        expect(m.flux.mock.calls.length).toBeGreaterThan(1);
    });
});
