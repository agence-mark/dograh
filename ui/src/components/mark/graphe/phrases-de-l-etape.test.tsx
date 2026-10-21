/**
 * [.mark] correctifs-apres-banc-v4, lot 5 (plan 4.11, maquette section 8) : la section « Phrases fixes à cette étape » de la
 * fenêtre d'une étape, rendue dans le VRAI composant de nœud (``GenericNode``) de l'éditeur.
 *
 * | Test | La garantie |
 * |---|---|
 * | liste | les règles propres à l'étape en cartes ; celles de l'agent et du groupe en pastilles « valent aussi ici » |
 * | ajouter | « Ajouter à cette étape » ouvre la même modale, l'endroit déjà choisi ; la règle est écrite avec l'identifiant du nœud et enregistrée tout de suite |
 * | étape de fin | la section n'est offerte qu'aux étapes qui parlent (pas à l'étape de fin) |
 */
import { cleanup, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { ReactFlowProvider } from "@xyflow/react";
import type { ComponentProps } from "react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import type { NodeSpec } from "@/client/types.gen";

import specs from "./specs-premiere-replique.json";

const m = vi.hoisted(() => ({ enregistrer: vi.fn(async () => undefined), saveWorkflow: vi.fn(async () => undefined) }));

vi.mock("sonner", () => ({ toast: { success: vi.fn(), error: vi.fn() } }));
vi.mock("next/navigation", () => ({
    useParams: () => ({ workflowId: "12" }),
    useRouter: () => ({ push: vi.fn(), replace: vi.fn(), back: vi.fn() }),
}));
const auth = vi.hoisted(() => ({ user: { id: "u-1" }, loading: false, getAccessToken: async () => "t" }));
vi.mock("@/lib/auth", () => ({ useAuth: () => auth }));
vi.mock("@/context/AppConfigContext", () => ({ useAppConfig: () => ({ config: null }) }));
vi.mock("@/components/ui/select", () => import("../reglages-agent/references/select-natif"));
vi.mock("@/components/flow/renderer/useNodeSpecs", () => ({
    useNodeSpecs: () => ({
        specs: Object.values(specs),
        loading: false,
        error: null,
        specVersion: "test",
        bySpecName: new Map(Object.entries(specs as Record<string, NodeSpec>)),
    }),
}));
vi.mock("@/client/sdk.gen", async (importOriginal) =>
    (await import("../sdk-factice")).sdkFactice(await importOriginal(), {
        listToolsApiV1ToolsGet: () => Promise.resolve({ data: [{ tool_uuid: "o1", name: "reserver", category: "http_api", definition: { config: { timeout_ms: 4000 } } }] }),
        getEquipeApiV1OrganizationsEquipeGet: () => Promise.resolve({ data: { personnes: [] } }),
    }),
);

const { GenericNode } = await import("@/components/flow/nodes/GenericNode");
const { WorkflowProvider } = await import("@/app/workflow/[workflowId]/contexts/WorkflowContext");
const { useWorkflowStore } = await import("@/app/workflow/[workflowId]/stores/workflowStore");

const ETAPES = [
    { id: "n1", nom: "Étape" },
    { id: "n2", nom: "Conclusion" },
];

const monter = async (type: "agentNode" | "endCall", regles: unknown[] = []) => {
    useWorkflowStore.setState({
        nodes: [{ id: "n1", type, position: { x: 0, y: 0 }, data: { name: "Étape", prompt: "Consigne." } as never }],
        edges: [],
    });
    render(
        <ReactFlowProvider>
            <WorkflowProvider
                value={{
                    saveWorkflow: m.saveWorkflow,
                    documents: [],
                    tools: [],
                    recordings: [],
                    champsFiche: [],
                    workflowId: 12,
                    agentPrincipalId: null,
                    estPrincipal: true,
                    travailActif: false,
                    phrasesDeLEtape: {
                        configuration: { phrases_regles: regles as never },
                        etapes: ETAPES,
                        outilsUuids: ["o1"],
                        peutGroupe: true,
                        enregistrer: m.enregistrer,
                    },
                }}
            >
                <GenericNode
                    {...({ id: "n1", type, data: useWorkflowStore.getState().nodes[0].data, selected: false } as unknown as ComponentProps<typeof GenericNode>)}
                />
            </WorkflowProvider>
        </ReactFlowProvider>,
    );
    fireEvent.doubleClick(screen.getByText("Étape"));
    return await screen.findByRole("dialog");
};

beforeEach(() => m.enregistrer.mockClear());
afterEach(cleanup);

describe("[.mark] section « Phrases fixes à cette étape » de la fenêtre d'une étape", () => {
    it("lists the step's own rules as cards and the agent's and the group's as badges", async () => {
        const dialogue = await monter("agentNode", [
            { motif: "outil_tarde", portee: "etape", etape: "Étape", etape_id: "n1", variantes: ["Je regarde."], delai_s: 1 },
            { motif: "outil_tarde", portee: "etape", etape: "Conclusion", etape_id: "n2", variantes: ["Ailleurs."], delai_s: 1 },
            { motif: "appelant_se_tait", portee: "groupe", variantes: ["Toujours là ?"], delai_s: 10 },
            { motif: "outil_echoue", portee: "agent", variantes: ["Raté."] },
        ]);
        const section = dialogue.querySelector("[data-section-phrases-etape]") as HTMLElement;
        expect(section).not.toBeNull();
        expect(section.querySelectorAll("[data-carte-phrase]")).toHaveLength(1);
        expect(section.textContent).toContain("Je regarde.");
        expect(section.textContent).not.toContain("Ailleurs.");
        const aussi = section.querySelector("[data-vaut-aussi-ici]") as HTMLElement;
        expect(aussi.textContent).toContain("The caller is silent");
        expect(aussi.textContent).toContain("A tool fails");
    });

    it("adds a rule at this step with the node identifier and saves it at once", async () => {
        const dialogue = await monter("agentNode", []);
        fireEvent.click(within(dialogue).getByRole("button", { name: "Add to this step" }));
        const ajout = (await screen.findAllByRole("dialog")).at(-1) as HTMLElement;
        fireEvent.click(within(ajout).getByRole("button", { name: "A tool is working" }));
        const endroit = await waitFor(() => document.getElementById("phrase_endroit") as HTMLSelectElement);
        expect(endroit.value).toBe("etape:n1");
        fireEvent.change(document.getElementById("phrase_variante_0") as HTMLInputElement, { target: { value: "Je vérifie." } });
        fireEvent.click(screen.getByRole("button", { name: "Add" }));
        await waitFor(() => expect(m.enregistrer).toHaveBeenCalledTimes(1));
        const [regles] = m.enregistrer.mock.calls[0] as unknown as [Array<Record<string, unknown>>];
        expect(regles).toHaveLength(1);
        expect(regles[0]).toMatchObject({ motif: "outil_tarde", portee: "etape", etape: "Étape", etape_id: "n1", variantes: ["Je vérifie."], delai_s: 3, active: true });
    });

    it("is not offered to the end step", async () => {
        const dialogue = await monter("endCall", []);
        expect(dialogue.querySelector("[data-section-phrases-etape]")).toBeNull();
    });
});
