/**
 * [.mark] Clôture, SA-3 : un agent qui ne se charge pas.
 *
 * Questions : un agent d'un autre espace est-il dit « dans l'espace … » avec un lien (et non « introuvable ») ? Un agent
 * vraiment absent garde-t-il la phrase d'erreur de la page ? Le menu suit-il l'espace retenu sur une adresse neutre ?
 */
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { espaceAffiche } from "@/components/mark/studio/base-espace";

import { AgentIntrouvable } from "./AgentIntrouvable";

const m = vi.hoisted(() => ({ espace: vi.fn(), retenir: vi.fn() }));
vi.mock("@/lib/auth", () => ({ useAuth: () => ({ user: { id: "u" }, loading: false }) }));
vi.mock("@/client/sdk.gen", () => ({ espaceDUnAgentApiV1EspacesAgentWorkflowIdGet: m.espace }));
vi.mock("@/lib/espaceCourant", async (original) => ({ ...(await original<typeof import("@/lib/espaceCourant")>()), retenirEspace: m.retenir }));

afterEach(() => {
    cleanup();
    vi.clearAllMocks();
});

describe("AgentIntrouvable", () => {
    it("dit l'espace de l'agent et l'ouvre avec un lien", async () => {
        m.espace.mockResolvedValue({ data: { workflow_id: 4, id: 1, nom: "Labo", espace: "labo", selectionne: false } });
        const assign = vi.fn();
        vi.stubGlobal("location", { ...window.location, assign, pathname: "/agents/4/settings", search: "" });
        render(<AgentIntrouvable agentId={4}>Workflow not found</AgentIntrouvable>);
        await waitFor(() => expect(screen.getByRole("status").textContent).toMatch(/dans l'espace|in the Lab space/));
        expect(screen.queryByText("Workflow not found")).toBeNull();
        fireEvent.click(screen.getByRole("button"));
        expect(m.retenir).toHaveBeenCalledWith("/labo");
        expect(assign).toHaveBeenCalledWith("/agents/4/settings");
        vi.unstubAllGlobals();
    });

    it("garde la phrase de la page quand l'agent n'est dans aucun espace ouvert", async () => {
        m.espace.mockResolvedValue({ error: { detail: "Agent not found" } });
        render(<AgentIntrouvable agentId={9}>Workflow not found</AgentIntrouvable>);
        await waitFor(() => expect(m.espace).toHaveBeenCalled());
        expect(screen.getByText("Workflow not found")).toBeTruthy();
    });
});

describe("espaceAffiche", () => {
    it("une adresse neutre prend l'espace retenu, une adresse qui le dit fait foi", () => {
        expect(espaceAffiche("/agents/1/settings", 2)).toMatchObject({ espace: "client", base: "/clients/2" });
        expect(espaceAffiche("/agents/1/settings", "labo").espace).toBe("labo");
        expect(espaceAffiche("/agents/1/settings", null).espace).toBe("labo");
        expect(espaceAffiche("/labo/agents", 2).espace).toBe("labo");
        expect(espaceAffiche("/clients/3/agents", 2)).toMatchObject({ espace: "client", base: "/clients/3" });
        expect(espaceAffiche("/relation", 2).espace).toBe("relation");
    });
});
