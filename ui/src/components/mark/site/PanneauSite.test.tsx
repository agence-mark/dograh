/**
 * [.mark] U10 / S2 puis V5 : l'entrée « widget du site » de l'écran « Intégrer ». Le formulaire à plat est remplacé par
 * l'éditeur de la maquette (`EditeurWidget`, testé à part) ; ici : le canal et le bouton qui ouvre l'éditeur.
 *
 * | Test | Ce qu'il prouve |
 * |---|---|
 * | agent téléphonique | seul le canal est proposé : pas d'éditeur, rien d'autre n'est lu |
 * | agent de site | « Configurer le widget » ouvre l'éditeur sur CET agent |
 * | canal | basculer le canal appelle la route du canal |
 * | refus | une erreur du serveur se dit par une notification, rien ne casse |
 */
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { FournisseurLangue } from "@/components/mark/langue/langue";

const sdk = vi.hoisted(() => ({ emplacement: vi.fn(), canal: vi.fn() }));
vi.mock("@/client/sdk.gen", async (importOriginal) =>
    (await import("../sdk-factice")).sdkFactice(await importOriginal(), {
        lireLEmplacementApiV1OrganizationsAgentsSiteWorkflowIdGet: sdk.emplacement,
        reglerLeCanalApiV1OrganizationsAgentsSiteWorkflowIdCanalPut: sdk.canal,
    }),
);
vi.mock("@/lib/auth", () => ({ useAuth: () => ({ loading: false, user: { email: "a@b.c" } }) }));
vi.mock("./EditeurWidget", () => ({
    EditeurWidget: ({ workflowId, onFermer }: { workflowId: number; onFermer: () => void }) => (
        <div data-testid="editeur-widget">
            {workflowId}
            <button onClick={onFermer}>fermer</button>
        </div>
    ),
}));

import { lireNotifications, viderNotifications } from "@/components/mark/notifications";

import { PanneauSite } from "./PanneauSite";

const rendre = () => render(<FournisseurLangue><PanneauSite workflowId={42} /></FournisseurLangue>);

beforeEach(() => {
    viderNotifications();
    Object.values(sdk).forEach((f) => f.mockReset());
    sdk.canal.mockResolvedValue({ data: {} });
});
afterEach(cleanup);

describe("PanneauSite", () => {
    it("un agent téléphonique ne montre que le canal", async () => {
        sdk.emplacement.mockResolvedValue({ data: { workflow_id: 42, canal: "telephone", chemins: [] } });
        rendre();
        await screen.findByTestId("panneau-site");
        expect(screen.queryByTestId("configurer-widget")).toBeNull();
        expect(screen.queryByTestId("editeur-widget")).toBeNull();
    });

    it("un agent de site ouvre l'éditeur de la maquette sur cet agent, puis le referme", async () => {
        sdk.emplacement.mockResolvedValue({ data: { workflow_id: 42, canal: "site", embed_token_id: 9, site_id: 3, chemins: ["/"] } });
        rendre();
        fireEvent.click(await screen.findByTestId("configurer-widget"));
        expect(screen.getByTestId("editeur-widget").textContent).toContain("42");
        fireEvent.click(screen.getByText("fermer"));
        expect(screen.queryByTestId("editeur-widget")).toBeNull();
    });

    it("basculer le canal appelle la route du canal", async () => {
        sdk.emplacement.mockResolvedValue({ data: { workflow_id: 42, canal: "telephone", chemins: [] } });
        rendre();
        fireEvent.click(await screen.findByRole("switch"));
        await waitFor(() => expect(sdk.canal).toHaveBeenCalledWith({ path: { workflow_id: 42 }, body: { canal: "site" } }));
        await waitFor(() => expect(lireNotifications().map((n) => n.sorte)).toContain("succes"));
    });

    it("une erreur du serveur se dit par une notification", async () => {
        sdk.emplacement.mockResolvedValue({ data: { workflow_id: 42, canal: "telephone", chemins: [] } });
        sdk.canal.mockResolvedValue({ error: { detail: "This agent still answers a phone number." } });
        rendre();
        fireEvent.click(await screen.findByRole("switch"));
        await waitFor(() => expect(lireNotifications().map((n) => n.detail)).toContain("This agent still answers a phone number."));
    });
});
