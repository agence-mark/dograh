/** [.mark] V2 : « Outil MCP » mène aux serveurs MCP de l'ESPACE courant (le Labo ou le client), pas toujours du Labo. */
import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { FournisseurLangue } from "../langue/langue";
import { FenetreNouvelOutil } from "./FenetreNouvelOutil";

const m = vi.hoisted(() => ({ push: vi.fn(), chemin: "/labo/outils" }));
vi.mock("next/navigation", () => ({ useRouter: () => ({ push: m.push }), usePathname: () => m.chemin }));
vi.mock("@/client/sdk.gen", () => ({
    createToolApiV1ToolsPost: vi.fn(),
    getWorkflowsSummaryApiV1WorkflowSummaryGet: vi.fn(async () => ({ data: [] })),
}));

afterEach(() => {
    cleanup();
    m.push.mockClear();
});

const choisirMcp = () => {
    render(
        <FournisseurLangue>
            <FenetreNouvelOutil fermer={() => undefined} cree={() => undefined} />
        </FournisseurLangue>,
    );
    fireEvent.click(screen.getByRole("button", { name: /Outil MCP/ }));
};

describe("[.mark] nouvel outil MCP", () => {
    it("ouvre les serveurs MCP du Labo depuis le Labo", () => {
        m.chemin = "/labo/outils";
        choisirMcp();
        expect(m.push).toHaveBeenCalledWith("/labo/integrations?onglet=mcp");
    });
    it("ouvre ceux du client depuis l'espace d'un client", () => {
        m.chemin = "/clients/7/outils";
        choisirMcp();
        expect(m.push).toHaveBeenCalledWith("/clients/7/integrations?onglet=mcp");
    });
});
