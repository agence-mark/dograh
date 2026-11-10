/** [.mark] Correctif écran point 2 : chaque type du « Nouvel outil » a sa tuile colorée, « Action d'un logiciel » trois logos. */
import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { FournisseurLangue } from "../langue/langue";
import { FenetreNouvelOutil } from "./FenetreNouvelOutil";

vi.mock("next/navigation", () => ({ useRouter: () => ({ push: vi.fn() }), usePathname: () => "/labo/outils" }));
vi.mock("@/client/sdk.gen", () => ({
    createToolApiV1ToolsPost: vi.fn(),
    getWorkflowsSummaryApiV1WorkflowSummaryGet: vi.fn(async () => ({ data: [] })),
}));
afterEach(cleanup);

const ouvrir = () =>
    render(
        <FournisseurLangue>
            <FenetreNouvelOutil fermer={() => undefined} cree={() => undefined} />
        </FournisseurLangue>,
    );

describe("[.mark] tuiles du nouvel outil", () => {
    it("une tuile colorée par type, trois logos pour l'action d'un logiciel", () => {
        ouvrir();
        const action = screen.getByTestId("nouvel-outil-integration");
        expect(action.querySelectorAll("img")).toHaveLength(3);
        for (const x of ["http_api", "mcp", "transfer_call", "transfer_agent", "end_call", "native", "calculator"]) {
            const tuile = screen.getByTestId(`nouvel-outil-${x}`).querySelector("span[style*='background']");
            expect(tuile, x).not.toBeNull();
        }
    });
    it("la demande de rappel reste grisée", () => {
        ouvrir();
        expect((screen.getByTestId("nouvel-outil-native") as HTMLButtonElement).disabled).toBe(true);
    });
});
