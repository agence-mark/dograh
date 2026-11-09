/** Clôture D1 (É20) : l'onglet « Tests » de l'agent porte le nombre de tests lu du serveur. */
import { cleanup, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

const m = vi.hoisted(() => ({ tests: vi.fn(async (_o?: unknown) => ({ data: { tests: [{}, {}, {}] }, error: undefined as unknown })) }));
vi.mock("@/client", async (importOriginal) => ({ ...(await importOriginal<object>()), lireLesTestsApiV1BuilderTestsWorkflowIdGet: (o: unknown) => m.tests(o) }));
vi.mock("../site/useAgentDeSite", () => ({ useAgentDeSite: () => false }));
vi.mock("next/link", () => ({ default: ({ children, ...p }: { children: React.ReactNode }) => <a {...(p as object)}>{children}</a> }));

const { OngletsAgent } = await import("./OngletsAgent");
afterEach(() => {
    cleanup();
    vi.clearAllMocks();
});

describe("compteur de l'onglet Tests", () => {
    it("affiche le nombre de tests de l'agent", async () => {
        render(<OngletsAgent agentId={7} actif="parcours" />);
        await waitFor(() => expect(document.querySelector('[data-compteur-onglet="tests"]')?.textContent).toBe("3"));
        expect((m.tests.mock.calls[0][0] as { path: unknown }).path).toEqual({ workflow_id: 7 });
        expect(screen.getAllByRole("tab")).toHaveLength(5);
    });
    it("n'affiche rien quand l'agent n'a aucun test", async () => {
        m.tests.mockResolvedValueOnce({ data: { tests: [] }, error: undefined });
        render(<OngletsAgent agentId={7} actif="parcours" />);
        await waitFor(() => expect(m.tests).toHaveBeenCalled());
        expect(document.querySelector("[data-compteur-onglet]")).toBeNull();
    });
});
