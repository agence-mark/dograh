/**
 * [.mark] Lot M (pièce 7 et sauvegarde) : l'écran des recettes d'agent. La liste vient de la bibliothèque (aucun nom en dur à l'écran),
 * le choix part avec la création, la recette d'un agent publié est figée, l'option de sauvegarde s'enregistre à part du cerveau.
 */
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

const creerAgent = vi.fn(async (_o?: unknown) => ({ data: { id: 12 }, error: undefined }));
const creerGroupe = vi.fn(async (_o?: unknown) => ({ data: { workflow_id: 13, folder_id: 1 }, error: undefined }));
const changer = vi.fn(async (_o?: unknown) => ({
    data: { recette: { slug: "b", nom: "Recette B", prouvee: true }, indiquee: true, modifiable: true },
    error: undefined,
}));
const regler = vi.fn(async (o?: { body?: unknown }) => ({ data: o?.body, error: undefined }));
let vueAgent = { recette: { slug: "a", nom: "Recette A", prouvee: false }, indiquee: true, modifiable: true };

const LISTE = {
    defaut: "a",
    recettes: [
        { slug: "a", nom: "Recette A", quand: "Quand A.", prouvee: false, statut: "candidat", capacites: [] },
        { slug: "b", nom: "Recette B", quand: "Quand B.", quand_en: "When B.", prouvee: true, statut: "recette", capacites: [] },
    ],
};

vi.mock("@/components/mark/studio/liste-deroulante", async () => await import("@/components/mark/studio/liste-deroulante-natif-test"));
vi.mock("sonner", () => ({ toast: { success: vi.fn(), error: vi.fn() } }));
vi.mock("next/navigation", () => ({ useRouter: () => ({ refresh: vi.fn(), push: vi.fn(), replace: vi.fn(), back: vi.fn() }) }));
vi.mock("@/client/sdk.gen", async (importOriginal) => {
    return (await import("../sdk-factice")).sdkFactice(await importOriginal(), {
        listerLesRecettesApiV1BuilderRecettesGet: () => Promise.resolve({ data: LISTE, error: undefined }),
        createWorkflowFromTemplateApiV1WorkflowCreateTemplatePost: (o: unknown) => creerAgent(o),
        creerUnGroupeApiV1WorkflowGroupePost: (o: unknown) => creerGroupe(o),
        updateWorkflowApiV1WorkflowWorkflowIdPut: () => Promise.resolve({ data: {}, error: undefined }),
        lireLaRecetteDeLAgentApiV1BuilderAgentsWorkflowIdRecetteGet: () => Promise.resolve({ data: vueAgent, error: undefined }),
        changerLaRecetteDeLAgentApiV1BuilderAgentsWorkflowIdRecettePut: (o: unknown) => changer(o),
        lireLesOptionsApiV1BuilderOptionsGet: () =>
            Promise.resolve({ data: { sauvegarde_avant_modification: false, recette_par_defaut: "" }, error: undefined }),
        reglerLesOptionsApiV1BuilderOptionsPut: (o: { body?: unknown }) => regler(o),
    });
});

const { FenetreCreationAgent } = await import("./FenetreCreationAgent");
const { RecetteDeLAgent } = await import("../reglages-agent/RecetteDeLAgent");
const { OptionsDeConstruction } = await import("../../builder/ecran/OptionsDeConstruction");

afterEach(() => {
    cleanup();
    vi.clearAllMocks();
    vueAgent = { recette: { slug: "a", nom: "Recette A", prouvee: false }, indiquee: true, modifiable: true };
});

describe("fenêtre de création : aucun choix de recette (Evan, 09/11)", () => {
    it("ne liste aucune recette, n'en envoie aucune : le serveur pose celle de la bibliothèque, le builder l'applique", async () => {
        render(<FenetreCreationAgent ouvert fermer={vi.fn()} />);
        await screen.findByLabelText("Name");
        expect(screen.queryByText("Recette A")).toBeNull();
        expect(document.querySelector('[data-section="recette"]')).toBeNull();
        fireEvent.change(screen.getByLabelText("Name"), { target: { value: "Mon agent" } });
        fireEvent.click(screen.getByText("One agent"));
        fireEvent.click(screen.getByText("Start the builder"));
        await waitFor(() => expect(creerAgent).toHaveBeenCalledTimes(1));
        expect((creerAgent.mock.calls[0][0] as { body: { recette: unknown } }).body.recette).toBeNull();
    });
});

describe("recette de l'agent", () => {
    it("se change tant que l'agent n'est pas publié", async () => {
        render(<RecetteDeLAgent workflowId={5} />);
        const select = (await screen.findByLabelText("Recipe")) as HTMLSelectElement;
        expect(select.value).toBe("a");
        fireEvent.change(select, { target: { value: "b" } });
        await waitFor(() => expect(changer).toHaveBeenCalledWith({ path: { workflow_id: 5 }, body: { recette: "b" } }));
    });

    it("SE-6 : après une publication, le changement demande un avertissement, puis part avec la confirmation", async () => {
        vueAgent = { ...vueAgent, modifiable: false };
        changer.mockResolvedValueOnce({
            data: { recette: { slug: "b", nom: "Recette B", prouvee: true }, indiquee: true, modifiable: false, tests_a_rejouer_depuis: "2026-11-04T10:00:00+00:00" },
            error: undefined,
        } as never);
        render(<RecetteDeLAgent workflowId={5} />);
        await screen.findByText("A version is published: changing it asks for a confirmation.");
        fireEvent.change(screen.getByLabelText("Recipe"), { target: { value: "b" } });
        expect(changer).not.toHaveBeenCalled(); // rien n'est envoyé avant la confirmation
        expect(document.querySelector("[data-fenetre-recette-publiee]")).not.toBeNull();
        fireEvent.click(document.querySelector("[data-confirmer-recette]") as HTMLElement);
        await waitFor(() => expect(changer).toHaveBeenCalledWith({ path: { workflow_id: 5 }, body: { recette: "b", confirmer: true } }));
        await screen.findByText("Tests to replay before publishing again.");
    });

    it("SE-6 : annuler l'avertissement ne change rien", async () => {
        vueAgent = { ...vueAgent, modifiable: false };
        render(<RecetteDeLAgent workflowId={5} />);
        fireEvent.change(await screen.findByLabelText("Recipe"), { target: { value: "b" } });
        fireEvent.click(await screen.findByText("Cancel"));
        await waitFor(() => expect(document.querySelector("[data-fenetre-recette-publiee]")).toBeNull());
        expect(changer).not.toHaveBeenCalled();
    });
});

describe("options de la construction", () => {
    it("allumer la sauvegarde l'enregistre tout de suite, sans toucher à la recette par défaut", async () => {
        render(<OptionsDeConstruction />);
        fireEvent.click(await screen.findByLabelText("Backup before the first change"));
        await waitFor(() => expect(regler).toHaveBeenCalled());
        expect(regler.mock.calls[0][0]).toEqual({ body: { sauvegarde_avant_modification: true, recette_par_defaut: "" } });
    });

    it("règle la recette par défaut parmi celles de la bibliothèque", async () => {
        render(<OptionsDeConstruction />);
        const select = (await screen.findByRole("combobox")) as HTMLSelectElement;
        fireEvent.change(select, { target: { value: "b" } });
        await waitFor(() => expect(regler).toHaveBeenCalledWith({ body: { sauvegarde_avant_modification: false, recette_par_defaut: "b" } }));
    });
});
