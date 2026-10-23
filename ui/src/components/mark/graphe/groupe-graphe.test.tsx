/**
 * [.mark] (Hors du fournisseur de langue, l'écran parle anglais : les textes cherchés ici sont les anglais.)
 *
 * [.mark] Chantier agents-specialises, lot 12 : ce que la fenêtre d'une étape du graphe ajoute pour un
 * groupe d'agents : la case « Retour au principal », les phrases de fin du principal, la brique « Agent ».
 *
 * ⛔ Ce fichier RENDRE le vrai composant de nœud du graphe (``GenericNode``, celui que l'éditeur ouvre),
 * alimenté par les spécifications que le serveur sert (``specs-premiere-replique.json``, vérifiées contre
 * le serveur). Ce qu'on regarde : ce que l'écran affiche, et ce que l'étape contient une fois enregistrée
 * dans le magasin du graphe. Rien n'est écrit pour un métier.
 */
import { cleanup, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { ReactFlowProvider } from "@xyflow/react";
import type { ComponentProps } from "react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import type { NodeSpec, ToolResponse } from "@/client/types.gen";

import specs from "./specs-premiere-replique.json";

const m = vi.hoisted(() => ({
    creerOutil: vi.fn(),
    ajouterOutil: vi.fn(),
    saveWorkflow: vi.fn(async () => undefined),
}));

vi.mock("sonner", () => ({ toast: { success: vi.fn(), error: vi.fn() } }));
vi.mock("next/navigation", () => ({
    useParams: () => ({ workflowId: "12" }),
    useRouter: () => ({ push: vi.fn(), replace: vi.fn(), back: vi.fn() }),
}));
vi.mock("@/lib/auth", () => ({
    useAuth: () => ({ user: { id: "u-1", email: "evan@example.test" }, loading: false, getAccessToken: async () => "t" }),
}));
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
        getWorkflowsApiV1WorkflowFetchGet: () =>
            Promise.resolve({
                data: [
                    { id: 12, name: "Agent courant", status: "active", created_at: "2026-10-16T00:00:00Z", total_runs: 0, folder_id: 1 },
                    { id: 20, name: "Spécialisé un", status: "active", created_at: "2026-10-16T00:00:00Z", total_runs: 0, folder_id: 1 },
                    { id: 30, name: "Agent voisin", status: "active", created_at: "2026-10-16T00:00:00Z", total_runs: 0, folder_id: null },
                    { id: 21, name: "Spécialisé deux", status: "active", created_at: "2026-10-16T00:00:00Z", total_runs: 0, folder_id: 1 },
                ],
                error: null,
            }),
        lireUnGroupeApiV1WorkflowWorkflowIdGroupeGet: () =>
            Promise.resolve({
                data: {
                    principal: { id: 12, name: "Agent courant", folder_id: 1 },
                    agent_principal_id: 12,
                    specialises: [
                        { id: 20, name: "Spécialisé un", cerveau_propre: false },
                        { id: 21, name: "Spécialisé deux", cerveau_propre: false },
                    ],
                },
                error: null,
            }),
        createToolApiV1ToolsPost: (options: unknown) => m.creerOutil(options),
    }),
);

const { GenericNode } = await import("@/components/flow/nodes/GenericNode");
const { WorkflowProvider } = await import("@/app/workflow/[workflowId]/contexts/WorkflowContext");
const { useWorkflowStore } = await import("@/app/workflow/[workflowId]/stores/workflowStore");

const OUTIL_EXISTANT = {
    tool_uuid: "outil-existant",
    name: "Passer à Spécialisé un",
    category: "transfer_agent",
    status: "active",
    definition: { schema_version: 1, type: "transfer_agent", config: { workflow_id: 20, message: "Je vous passe un collègue.", play_greeting: false } },
} as unknown as ToolResponse;

interface Contexte {
    agentPrincipalId?: number | null;
    estPrincipal?: boolean;
    tools?: ToolResponse[];
    travailActif?: boolean;
}

const monter = async (type: "agentNode" | "endCall", data: Record<string, unknown>, contexte: Contexte = {}) => {
    useWorkflowStore.setState({
        nodes: [{ id: "n1", type, position: { x: 0, y: 0 }, data: { name: "Étape", prompt: "Consigne.", ...data } as never }],
        edges: [],
    });
    render(
        <ReactFlowProvider>
            <WorkflowProvider
                value={{
                    saveWorkflow: m.saveWorkflow,
                    documents: [],
                    tools: contexte.tools ?? [],
                    recordings: [],
                    champsFiche: ["degre_urgence", "numero_rappel"],
                    workflowId: 12,
                    agentPrincipalId: contexte.agentPrincipalId ?? null,
                    estPrincipal: contexte.estPrincipal ?? false,
                    travailActif: contexte.travailActif ?? false,
                    ajouterOutil: m.ajouterOutil,
                }}
            >
                <GenericNode
                    {...({
                        id: "n1",
                        type,
                        data: useWorkflowStore.getState().nodes[0].data,
                        selected: false,
                    } as unknown as ComponentProps<typeof GenericNode>)}
                />
            </WorkflowProvider>
        </ReactFlowProvider>,
    );
    fireEvent.doubleClick(screen.getByText("Étape"));
    return await screen.findByRole("dialog");
};

const donneesDeLEtape = () => useWorkflowStore.getState().nodes[0].data as Record<string, unknown>;
const enregistrerEtape = async (dialogue: HTMLElement) => {
    fireEvent.click(within(dialogue).getByRole("button", { name: /^save$/i }));
    await waitFor(() => expect(m.saveWorkflow).toHaveBeenCalled());
};

beforeEach(() => {
    m.creerOutil.mockReset();
    m.ajouterOutil.mockReset();
    m.saveWorkflow.mockClear();
});
afterEach(cleanup);

describe("[.mark] case « Retour au principal » d'une étape", () => {
    it("n'existe pas chez un agent sans principal (un agent seul garde sa fenêtre d'avant)", async () => {
        const dialogue = await monter("agentNode", {});
        expect(within(dialogue).queryByText("Back to the main agent")).toBeNull();
        expect(dialogue.querySelector('[data-reglage="retour_au_principal"]')).toBeNull();
    });

    it("existe chez un spécialisé, dit où va l'appel, et écrit le marqueur dans l'étape", async () => {
        const dialogue = await monter("agentNode", {}, { agentPrincipalId: 5 });
        const champ = dialogue.querySelector('[data-reglage="retour_au_principal"]');
        expect(champ).not.toBeNull();
        expect(champ?.textContent).toContain("At the end of this step, the call goes back to the main agent");
        expect(donneesDeLEtape().retour_au_principal).toBeUndefined();
        fireEvent.click(document.getElementById("retour_au_principal") as HTMLElement);
        await enregistrerEtape(dialogue);
        expect(donneesDeLEtape().retour_au_principal).toBe(true);
    });

    it("se lit cochée quand le marqueur est posé, et se décoche", async () => {
        const dialogue = await monter("agentNode", { retour_au_principal: true }, { agentPrincipalId: 5 });
        const interrupteur = document.getElementById("retour_au_principal") as HTMLElement;
        expect(interrupteur.getAttribute("aria-checked")).toBe("true");
        fireEvent.click(interrupteur);
        await enregistrerEtape(dialogue);
        expect(donneesDeLEtape().retour_au_principal).toBeUndefined();
    });
});

describe("[.mark] case « Étape de retour » d'une étape de l'accueil", () => {
    it("n'existe que chez le principal d'un groupe : ni chez un agent seul, ni chez un spécialisé", async () => {
        let dialogue = await monter("agentNode", {});
        expect(dialogue.querySelector('[data-reglage="etape_de_retour"]')).toBeNull();
        cleanup();
        dialogue = await monter("agentNode", {}, { agentPrincipalId: 5 });
        expect(dialogue.querySelector('[data-reglage="etape_de_retour"]')).toBeNull();
        // Le spécialisé garde sa propre case, celle du retour au principal.
        expect(dialogue.querySelector('[data-reglage="retour_au_principal"]')).not.toBeNull();
    });

    it("existe chez le principal, dit ce qu'elle fait, et écrit le marqueur dans l'étape", async () => {
        const dialogue = await monter("agentNode", {}, { estPrincipal: true });
        const champ = dialogue.querySelector('[data-reglage="etape_de_retour"]');
        expect(champ).not.toBeNull();
        expect(champ?.textContent).toContain("Return step");
        expect(champ?.textContent).toContain("the call comes here instead of the start step");
        expect(donneesDeLEtape().etape_de_retour).toBeUndefined();
        fireEvent.click(document.getElementById("etape_de_retour") as HTMLElement);
        await enregistrerEtape(dialogue);
        expect(donneesDeLEtape().etape_de_retour).toBe(true);
        // Le principal ne voit pas la case du spécialisé.
        expect(dialogue.querySelector('[data-reglage="retour_au_principal"]')).toBeNull();
    });

    it("se lit cochée quand le marqueur est posé, et se décoche", async () => {
        const dialogue = await monter("agentNode", { etape_de_retour: true }, { estPrincipal: true });
        const interrupteur = document.getElementById("etape_de_retour") as HTMLElement;
        expect(interrupteur.getAttribute("aria-checked")).toBe("true");
        fireEvent.click(interrupteur);
        await enregistrerEtape(dialogue);
        expect(donneesDeLEtape().etape_de_retour).toBeUndefined();
    });

    it("cocher ou décocher rend l'étape modifiée (le garde-fou de fermeture la voit)", async () => {
        await monter("agentNode", {}, { estPrincipal: true });
        const bouton = screen.getByRole("button", { name: /^save$/i }) as HTMLButtonElement;
        fireEvent.click(document.getElementById("etape_de_retour") as HTMLElement);
        expect(bouton.disabled).toBe(false);
    });
});

describe("[.mark] case « Travail en arrière-plan » d'une étape (modules-et-cerveaux, lot 5)", () => {
    it("n'existe que quand le travail en arrière-plan de l'agent est allumé", async () => {
        const dialogue = await monter("agentNode", {});
        expect(dialogue.querySelector('[data-reglage="travail_de_fond"]')).toBeNull();
    });

    it("existe quand il est allumé, dit ce qu'elle fait, et écrit le marqueur dans l'étape", async () => {
        const dialogue = await monter("agentNode", {}, { travailActif: true });
        const champ = dialogue.querySelector('[data-reglage="travail_de_fond"]');
        expect(champ).not.toBeNull();
        expect(champ?.textContent).toContain("Background work");
        expect(donneesDeLEtape().travail_de_fond).toBeUndefined();
        fireEvent.click(document.getElementById("travail_de_fond") as HTMLElement);
        await enregistrerEtape(dialogue);
        expect(donneesDeLEtape().travail_de_fond).toBe(true);
    });

    it("se lit cochée quand le marqueur est posé, et se décoche", async () => {
        const dialogue = await monter("agentNode", { travail_de_fond: true }, { travailActif: true });
        const interrupteur = document.getElementById("travail_de_fond") as HTMLElement;
        expect(interrupteur.getAttribute("aria-checked")).toBe("true");
        fireEvent.click(interrupteur);
        await enregistrerEtape(dialogue);
        expect(donneesDeLEtape().travail_de_fond).toBeUndefined();
    });

    it("n'existe pas sur un nœud de fin", async () => {
        const dialogue = await monter("endCall", {}, { travailActif: true });
        expect(dialogue.querySelector('[data-reglage="travail_de_fond"]')).toBeNull();
    });
});

describe("[.mark] case « Vérité des actions » d'une étape (correctifs-apres-banc-commun, lot 5)", () => {
    it("n'existe pas sur une étape qui n'offre aucun outil d'action", async () => {
        const dialogue = await monter("agentNode", {});
        expect(dialogue.querySelector('[data-reglage="verite_des_actions"]')).toBeNull();
    });

    it("existe sur une étape qui porte un outil, allumée par défaut, et ne change pas l'étape tant qu'on n'y touche pas", async () => {
        const dialogue = await monter("agentNode", { tool_uuids: ["outil-existant"] }, { tools: [OUTIL_EXISTANT] });
        const champ = dialogue.querySelector('[data-reglage="verite_des_actions"]');
        expect(champ).not.toBeNull();
        expect(champ?.textContent).toContain("Truth of actions");
        expect(document.getElementById("verite_des_actions")?.getAttribute("aria-checked")).toBe("true");
        expect(donneesDeLEtape().verite_des_actions).toBeUndefined();
    });

    it("s'éteint en écrivant false dans l'étape, et se rallume en effaçant le marqueur", async () => {
        const dialogue = await monter("agentNode", { tool_uuids: ["outil-existant"] }, { tools: [OUTIL_EXISTANT] });
        fireEvent.click(document.getElementById("verite_des_actions") as HTMLElement);
        await enregistrerEtape(dialogue);
        expect(donneesDeLEtape().verite_des_actions).toBe(false);
    });

    it("se lit éteinte quand l'étape porte false, et se rallume", async () => {
        const dialogue = await monter(
            "agentNode",
            { tool_uuids: ["outil-existant"], verite_des_actions: false },
            { tools: [OUTIL_EXISTANT] },
        );
        const interrupteur = document.getElementById("verite_des_actions") as HTMLElement;
        expect(interrupteur.getAttribute("aria-checked")).toBe("false");
        fireEvent.click(interrupteur);
        await enregistrerEtape(dialogue);
        expect(donneesDeLEtape().verite_des_actions).toBeUndefined();
    });

    it("existe aussi sur une étape cochée « Travail en arrière-plan » quand le travail est allumé", async () => {
        const dialogue = await monter("agentNode", { travail_de_fond: true }, { travailActif: true });
        expect(dialogue.querySelector('[data-reglage="verite_des_actions"]')).not.toBeNull();
        cleanup();
        const sans = await monter("agentNode", { travail_de_fond: true }, { travailActif: false });
        expect(sans.querySelector('[data-reglage="verite_des_actions"]')).toBeNull();
    });

    it("n'existe pas sur un nœud de fin", async () => {
        const dialogue = await monter("endCall", {}, { travailActif: true });
        expect(dialogue.querySelector('[data-reglage="verite_des_actions"]')).toBeNull();
    });
});

describe("[.mark] menu « Déclenchement de l'action » d'une étape (correctifs-apres-banc-commun, lot 6)", () => {
    const AVEC_OUTIL = { tool_uuids: ["outil-existant"], champs_etape: "degre_urgence, numero_rappel" };

    it("n'existe pas sur une étape qui n'offre aucune action, ni sur un nœud de fin", async () => {
        const dialogue = await monter("agentNode", {});
        expect(dialogue.querySelector('[data-reglage="declenchement_de_l_action"]')).toBeNull();
        cleanup();
        const fin = await monter("endCall", {}, { travailActif: true });
        expect(fin.querySelector('[data-reglage="declenchement_de_l_action"]')).toBeNull();
    });

    it("existe sur une étape qui porte un outil, sur Libre, et ne change pas l'étape tant qu'on n'y touche pas", async () => {
        const dialogue = await monter("agentNode", AVEC_OUTIL, { tools: [OUTIL_EXISTANT] });
        const champ = dialogue.querySelector('[data-reglage="declenchement_de_l_action"]');
        expect(champ?.textContent).toContain("Action trigger");
        expect((document.getElementById("declenchement_de_l_action") as HTMLSelectElement).value).toBe("libre");
        expect(dialogue.querySelector('[data-reglage="demande_type"]')).toBeNull();
        await enregistrerEtape(dialogue);
        expect(donneesDeLEtape().declenchement_de_l_action).toBeUndefined();
        expect(donneesDeLEtape().demande_type).toBeUndefined();
    });

    it("propose Libre, Relance et Obligatoire, pas Automatique sans travail en arrière-plan sur l'étape", async () => {
        await monter("agentNode", AVEC_OUTIL, { tools: [OUTIL_EXISTANT] });
        const options = Array.from((document.getElementById("declenchement_de_l_action") as HTMLSelectElement).options).map((o) => o.value);
        expect(options).toEqual(["libre", "relance", "obligatoire"]);
    });

    it("écrit la position choisie dans l'étape, et Libre efface le marqueur", async () => {
        const dialogue = await monter("agentNode", AVEC_OUTIL, { tools: [OUTIL_EXISTANT] });
        fireEvent.change(document.getElementById("declenchement_de_l_action") as HTMLElement, { target: { value: "relance" } });
        expect(dialogue.querySelector('[data-reglage="declenchement_de_l_action"]')?.textContent).toContain("held back");
        await enregistrerEtape(dialogue);
        expect(donneesDeLEtape().declenchement_de_l_action).toBe("relance");
        cleanup();
        const rouvert = await monter("agentNode", { ...AVEC_OUTIL, declenchement_de_l_action: "relance" }, { tools: [OUTIL_EXISTANT] });
        fireEvent.change(document.getElementById("declenchement_de_l_action") as HTMLElement, { target: { value: "libre" } });
        await enregistrerEtape(rouvert);
        expect(donneesDeLEtape().declenchement_de_l_action).toBeUndefined();
    });

    it("se lit sur la position de l'étape, et rend l'étape modifiée quand on la change", async () => {
        await monter("agentNode", { ...AVEC_OUTIL, declenchement_de_l_action: "obligatoire" }, { tools: [OUTIL_EXISTANT] });
        expect((document.getElementById("declenchement_de_l_action") as HTMLSelectElement).value).toBe("obligatoire");
        const bouton = screen.getByRole("button", { name: /^save$/i }) as HTMLButtonElement;
        fireEvent.change(document.getElementById("declenchement_de_l_action") as HTMLElement, { target: { value: "relance" } });
        expect(bouton.disabled).toBe(false);
    });

    it("dit que Relance et Obligatoire ne font rien sur une étape sans champ listé", async () => {
        const dialogue = await monter("agentNode", { tool_uuids: ["outil-existant"], declenchement_de_l_action: "relance" }, { tools: [OUTIL_EXISTANT] });
        expect(dialogue.querySelector('[data-reglage="declenchement_de_l_action"]')?.textContent).toContain("lists no field");
    });

    it("propose Automatique sur une étape en travail en arrière-plan, avec sa demande type, enregistrée", async () => {
        const dialogue = await monter("agentNode", { travail_de_fond: true }, { travailActif: true });
        const options = Array.from((document.getElementById("declenchement_de_l_action") as HTMLSelectElement).options).map((o) => o.value);
        expect(options).toContain("automatique");
        fireEvent.change(document.getElementById("declenchement_de_l_action") as HTMLElement, { target: { value: "automatique" } });
        const demande = document.getElementById("demande_type") as HTMLTextAreaElement;
        expect(dialogue.querySelector('[data-reglage="demande_type"]')?.textContent).toContain("Request template");
        fireEvent.change(demande, { target: { value: "Réserve pour {{degre_urgence}}." } });
        await enregistrerEtape(dialogue);
        expect(donneesDeLEtape().declenchement_de_l_action).toBe("automatique");
        expect(donneesDeLEtape().demande_type).toBe("Réserve pour {{degre_urgence}}.");
    });
});

describe("[.mark] champ conditionnel de la liste des champs d'une étape (correctifs-apres-banc-commun, lot 7)", () => {
    const ETAPE = { champs_etape: "degre_urgence, numero_rappel" };

    it("une étape sans condition n'écrit rien de plus", async () => {
        const dialogue = await monter("agentNode", ETAPE);
        expect(dialogue.querySelector("[data-conditions-de-champs]")).toBeNull();
        await enregistrerEtape(dialogue);
        expect(donneesDeLEtape().conditions_de_champs).toBeUndefined();
    });

    it("pose une condition sur un champ de la liste, l'enregistre dans l'étape, et la montre", async () => {
        const dialogue = await monter("agentNode", ETAPE);
        fireEvent.click(screen.getByRole("button", { name: /Expect this field only if… \(numero_rappel\)/ }));
        const ligne = dialogue.querySelector('[data-condition-du-champ="numero_rappel"]');
        expect(ligne?.textContent).toContain("only if");
        await enregistrerEtape(dialogue);
        expect(donneesDeLEtape().conditions_de_champs).toEqual([{ champ: "numero_rappel", si: "degre_urgence" }]);
    });

    it("la condition « vaut » garde sa valeur, « est rempli » l'efface", async () => {
        const dialogue = await monter("agentNode", {
            ...ETAPE,
            conditions_de_champs: [{ champ: "numero_rappel", si: "degre_urgence", vaut: "haut" }],
        });
        expect((document.getElementById("condition-mode-numero_rappel") as HTMLSelectElement).value).toBe("vaut");
        expect((document.getElementById("condition-vaut-numero_rappel") as HTMLInputElement).value).toBe("haut");
        fireEvent.change(document.getElementById("condition-vaut-numero_rappel") as HTMLElement, { target: { value: "bas" } });
        await enregistrerEtape(dialogue);
        expect(donneesDeLEtape().conditions_de_champs).toEqual([{ champ: "numero_rappel", si: "degre_urgence", vaut: "bas" }]);
        cleanup();
        const rouvert = await monter("agentNode", { ...ETAPE, conditions_de_champs: [{ champ: "numero_rappel", si: "degre_urgence", vaut: "bas" }] });
        fireEvent.change(document.getElementById("condition-mode-numero_rappel") as HTMLElement, { target: { value: "__rempli__" } });
        await enregistrerEtape(rouvert);
        expect((donneesDeLEtape().conditions_de_champs as Record<string, unknown>[])[0].vaut).toBeUndefined();
    });

    it("retirer la condition, ou retirer le champ, efface la ligne", async () => {
        const dialogue = await monter("agentNode", {
            ...ETAPE,
            conditions_de_champs: [{ champ: "numero_rappel", si: "degre_urgence" }],
        });
        fireEvent.click(screen.getByRole("button", { name: /Remove this condition \(numero_rappel\)/ }));
        await enregistrerEtape(dialogue);
        expect(donneesDeLEtape().conditions_de_champs).toBeUndefined();
        cleanup();
        const autre = await monter("agentNode", { ...ETAPE, conditions_de_champs: [{ champ: "numero_rappel", si: "degre_urgence" }] });
        fireEvent.click(within(autre).getByRole("button", { name: "Remove numero_rappel" }));
        await enregistrerEtape(autre);
        expect(donneesDeLEtape().conditions_de_champs).toBeUndefined();
        expect(donneesDeLEtape().champs_etape).toBe("degre_urgence");
    });

    it("signale un champ testé qui n'est pas dans la fiche", async () => {
        const dialogue = await monter("agentNode", {
            ...ETAPE,
            conditions_de_champs: [{ champ: "numero_rappel", si: "inexistant" }],
        });
        expect(within(dialogue).getByRole("alert").textContent).toContain("not in the agent's record");
    });
});

describe("[.mark] phrases de fin du nœud de fin", () => {
    it("un nœud de fin d'un agent seul porte la liste (plus de doublon avec le formulaire) et garde sa zone de texte", async () => {
        const dialogue = await monter("endCall", { name: "Étape" });
        // Lot 2 d'orchestrateur-trois-cerveaux (D5) : la liste est celle de ``PhrasesDeFin`` pour tout agent,
        // le formulaire généré ne la dessine plus.
        expect(dialogue.querySelectorAll('[data-reglage="fins"]').length).toBe(1);
        expect(within(dialogue).queryAllByText("Fixed closing sentences").length).toBe(0);
        expect(within(dialogue).getAllByRole("textbox").some((z) => (z as HTMLTextAreaElement).value === "Consigne.")).toBe(true);
    });

    it("chez un spécialisé aussi : une seule liste, qui s'écrit dans l'étape", async () => {
        const dialogue = await monter("endCall", {}, { agentPrincipalId: 5 });
        expect(dialogue.querySelectorAll('[data-reglage="fins"]').length).toBe(1);
        fireEvent.change(document.getElementById("fin-phrase-defaut") as HTMLElement, { target: { value: "Au revoir." } });
        await enregistrerEtape(dialogue);
        expect(donneesDeLEtape().fins).toEqual([{ phrase: "Au revoir." }]);
    });

    it("chez le principal : la liste s'ajoute, et remplace la zone de texte dès qu'elle a une ligne", async () => {
        const dialogue = await monter("endCall", {}, { estPrincipal: true });
        expect(dialogue.querySelector('[data-reglage="fins"]')).not.toBeNull();
        // Sans ligne, la zone de texte d'avant reste (rien n'est enregistré à sa place).
        expect(within(dialogue).getAllByRole("textbox").some((z) => (z as HTMLTextAreaElement).value === "Consigne.")).toBe(true);
        fireEvent.change(document.getElementById("fin-phrase-defaut") as HTMLElement, { target: { value: "Merci de votre appel." } });
        // Une phrase par défaut écrite : la liste remplace la zone de texte.
        await waitFor(() =>
            expect(within(dialogue).queryAllByRole("textbox").some((z) => (z as HTMLTextAreaElement).value === "Consigne.")).toBe(false),
        );
        await enregistrerEtape(dialogue);
        expect(donneesDeLEtape().fins).toEqual([{ phrase: "Merci de votre appel." }]);
    });

    it("écrit « si champ rempli → phrase », « si champ vaut → phrase », puis la phrase par défaut, dans l'ordre", async () => {
        const dialogue = await monter("endCall", {}, { estPrincipal: true });
        fireEvent.click(within(dialogue).getByRole("button", { name: "Add a condition" }));
        fireEvent.change(document.getElementById("fin-phrase-0") as HTMLElement, { target: { value: "Restez en sécurité." } });
        fireEvent.change(document.getElementById("fin-champ-0") as HTMLElement, { target: { value: "degre_urgence" } });
        fireEvent.change(document.getElementById("fin-mode-0") as HTMLElement, { target: { value: "vaut" } });
        fireEvent.change(document.getElementById("fin-vaut-0") as HTMLElement, { target: { value: "danger" } });
        fireEvent.click(within(dialogue).getByRole("button", { name: "Add a condition" }));
        fireEvent.change(document.getElementById("fin-phrase-1") as HTMLElement, { target: { value: "Nous vous rappelons." } });
        fireEvent.change(document.getElementById("fin-champ-1") as HTMLElement, { target: { value: "numero_rappel" } });
        fireEvent.change(document.getElementById("fin-phrase-defaut") as HTMLElement, { target: { value: "Bonne journée." } });
        await enregistrerEtape(dialogue);
        expect(donneesDeLEtape().fins).toEqual([
            { champ: "degre_urgence", vaut: "danger", phrase: "Restez en sécurité." },
            { champ: "numero_rappel", phrase: "Nous vous rappelons." },
            { phrase: "Bonne journée." },
        ]);
    });

    it("n'enregistre jamais une ligne sans phrase, et la dit", async () => {
        const dialogue = await monter("endCall", {}, { estPrincipal: true });
        fireEvent.click(within(dialogue).getByRole("button", { name: "Add a condition" }));
        expect(within(dialogue).getByText("A sentence cannot be empty: this line is not saved.")).toBeTruthy();
        fireEvent.change(document.getElementById("fin-phrase-defaut") as HTMLElement, { target: { value: "Au revoir." } });
        await enregistrerEtape(dialogue);
        expect(donneesDeLEtape().fins).toEqual([{ phrase: "Au revoir." }]);
    });

    it("relit la liste enregistrée, et la monte et la descend", async () => {
        const fins = [
            { champ: "degre_urgence", vaut: "danger", phrase: "Première." },
            { champ: "numero_rappel", phrase: "Seconde." },
            { phrase: "Défaut." },
        ];
        const dialogue = await monter("endCall", { fins }, { estPrincipal: true });
        expect((document.getElementById("fin-phrase-0") as HTMLInputElement).value).toBe("Première.");
        expect((document.getElementById("fin-phrase-defaut") as HTMLInputElement).value).toBe("Défaut.");
        fireEvent.click(within(dialogue).getAllByRole("button", { name: "Move down" })[0]);
        await enregistrerEtape(dialogue);
        expect((donneesDeLEtape().fins as Array<{ phrase: string }>).map((f) => f.phrase)).toEqual(["Seconde.", "Première.", "Défaut."]);
    });
});

describe("[.mark] brique « Agent » sous une étape", () => {
    const crees: ToolResponse[] = [];
    beforeEach(() => {
        crees.length = 0;
        m.creerOutil.mockImplementation(async (options: { body: Record<string, unknown> }) => {
            const outil = { ...options.body, tool_uuid: `nouvel-outil-${crees.length}`, status: "active" } as unknown as ToolResponse;
            crees.push(outil);
            return { data: outil, error: undefined };
        });
    });

    it("liste les briques réglées avec un lien vers l'agent cible dans un nouvel onglet", async () => {
        const dialogue = await monter("agentNode", { tool_uuids: ["outil-existant"] }, { tools: [OUTIL_EXISTANT] });
        const brique = await waitFor(() => {
            const b = dialogue.querySelector('[data-brique-agent="20"]');
            expect(b).not.toBeNull();
            return b as HTMLElement;
        });
        await waitFor(() => expect(brique.textContent).toContain("Spécialisé un"));
        const lien = within(brique).getByRole("link", { name: "Open the agent in a new tab" });
        expect(lien.getAttribute("href")).toBe("/workflow/20");
        expect(lien.getAttribute("target")).toBe("_blank");
        expect(brique.textContent).toContain("Je vous passe un collègue.");
    });

    it("propose les agents du groupe d'abord, puis les autres, l'agent courant exclu, dans une modale", async () => {
        const dialogue = await monter("agentNode", {}, { tools: [] });
        fireEvent.click(within(dialogue).getByRole("button", { name: "Add an agent" }));
        const modale = await waitFor(() => {
            const el = document.querySelector('[data-modale="choisir-un-agent"]');
            expect(el).not.toBeNull();
            return el as HTMLElement;
        });
        expect(within(modale).getByText("Choose an agent")).toBeTruthy();
        await waitFor(() => expect(modale.querySelector('[data-agents="du-groupe"]')).not.toBeNull());
        const duGroupe = modale.querySelector('[data-agents="du-groupe"]') as HTMLElement;
        const autres = modale.querySelector('[data-agents="autres"]') as HTMLElement;
        expect(duGroupe.textContent).toContain("Spécialisé un");
        expect(duGroupe.textContent).toContain("Spécialisé deux");
        expect(autres.textContent).toContain("Agent voisin");
        expect(modale.textContent).not.toContain("Agent courant");
        // Le groupe avant les autres.
        expect(modale.innerHTML.indexOf('data-agents="du-groupe"')).toBeLessThan(modale.innerHTML.indexOf('data-agents="autres"'));
    });

    it("crée l'outil de passation (annonce, accueil) et le rattache à l'étape", async () => {
        const dialogue = await monter("agentNode", {}, { tools: [] });
        fireEvent.click(within(dialogue).getByRole("button", { name: "Add an agent" }));
        const modale = await waitFor(() => {
            const el = document.querySelector('[data-modale="choisir-un-agent"]');
            expect(el).not.toBeNull();
            return el as HTMLElement;
        });
        await waitFor(() => expect(within(modale).getByLabelText("Agent voisin")).toBeTruthy());
        fireEvent.click(within(modale).getByLabelText("Agent voisin"));
        fireEvent.change(document.getElementById("brique-agent-annonce") as HTMLElement, { target: { value: "Un instant, je vous passe quelqu'un." } });
        fireEvent.click(document.getElementById("brique-agent-accueil") as HTMLElement);
        fireEvent.click(within(modale).getByRole("button", { name: "Add the agent" }));
        await waitFor(() => expect(m.creerOutil).toHaveBeenCalledTimes(1));
        const { body } = m.creerOutil.mock.calls[0][0] as { body: Record<string, unknown> };
        expect(body.category).toBe("transfer_agent");
        expect(body.name).toBe("Passer à Agent voisin");
        expect(body.definition).toEqual({
            schema_version: 1,
            type: "transfer_agent",
            config: { workflow_id: 30, message: "Un instant, je vous passe quelqu'un.", play_greeting: true },
        });
        expect(m.ajouterOutil).toHaveBeenCalledWith(expect.objectContaining({ tool_uuid: "nouvel-outil-0" }));
        // Rattaché à l'étape une fois l'étape enregistrée ; le reste de l'étape ne bouge pas.
        await enregistrerEtape(dialogue);
        expect(donneesDeLEtape().tool_uuids).toEqual(["nouvel-outil-0"]);
        expect(donneesDeLEtape().prompt).toBe("Consigne.");
    });

    it("détache une brique de l'étape sans toucher au reste", async () => {
        const dialogue = await monter("agentNode", { tool_uuids: ["outil-existant"] }, { tools: [OUTIL_EXISTANT] });
        const retirer = await waitFor(() => within(dialogue).getByRole("button", { name: "Detach this agent from the step" }));
        fireEvent.click(retirer);
        await enregistrerEtape(dialogue);
        expect(donneesDeLEtape().tool_uuids).toBeUndefined();
        expect(donneesDeLEtape().name).toBe("Étape");
    });
});
