/**
 * [.mark] Partie 3, sous-lot 9 : la fenêtre de création d'agent UNIQUE. Un test par chemin de création : rien de ce que savaient
 * faire les deux fenêtres d'avant (`ModaleNouvelAgent`, `ModaleCreationAgent`) ne se perd.
 *
 * | Chemin | Route appelée | Ce qui s'ouvre |
 * |---|---|---|
 * | groupe, avec le builder | `POST /workflow/groupe` (nom, dossier, recette) | le principal, panneau du builder ouvert |
 * | groupe, depuis une recette | `POST /workflow/groupe` | le principal, sans le builder |
 * | un agent, avec le builder | `POST /workflow/create/template` (description) puis le nom | l'agent, panneau ouvert |
 * | un agent, vide | `POST /workflow/create/template` sans description | l'agent |
 * | temps réel | le groupe est grisé ; l'agent reçoit `model_overrides.is_realtime` | l'agent |
 * | installation d'un client | chaque requête porte l'organisation du client | rien : l'appelant reçoit l'agent |
 */
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

const m = vi.hoisted(() => ({
    push: vi.fn(),
    groupe: vi.fn(async (_o?: unknown) => ({ data: { workflow_id: 13, folder_id: 8 }, error: undefined as unknown })),
    agent: vi.fn(async (_o?: unknown) => ({
        data: { id: 12, workflow_configurations: { mark_reglage: 1, model_overrides: { tts: { voice: "v" } } } },
        error: undefined as unknown,
    })),
    maj: vi.fn(async (_o?: unknown) => ({ data: {}, error: undefined })),
    depot: vi.fn(async (_o?: unknown) => ({ data: {}, error: undefined as unknown })),
    recettes: vi.fn(async (_o?: unknown) => ({
        data: { defaut: "a", recettes: [{ slug: "a", nom: "Recette A", quand: "Quand A.", prouvee: true }] },
        error: undefined,
    })),
}));
// Clôture, SA-3 (Evan, 09/11) : AUCUN choix de recette à la création ; le serveur pose celle de la bibliothèque, le builder l'applique.

vi.mock("sonner", () => ({ toast: { success: vi.fn(), error: vi.fn() } }));
vi.mock("next/navigation", () => ({ useRouter: () => ({ refresh: vi.fn(), push: m.push, replace: vi.fn(), back: vi.fn() }) }));
vi.mock("@/client/sdk.gen", async (importOriginal) => {
    return (await import("../sdk-factice")).sdkFactice(await importOriginal(), {
        listerLesRecettesApiV1BuilderRecettesGet: (o: unknown) => m.recettes(o),
        creerUnGroupeApiV1WorkflowGroupePost: (o: unknown) => m.groupe(o),
        createWorkflowFromTemplateApiV1WorkflowCreateTemplatePost: (o: unknown) => m.agent(o),
        updateWorkflowApiV1WorkflowWorkflowIdPut: (o: unknown) => m.maj(o),
        deposerUnFichierApiV1BuilderDepotWorkflowIdPost: (o: unknown) => m.depot(o),
    });
});

const { FenetreCreationAgent } = await import("./FenetreCreationAgent");

afterEach(() => {
    cleanup();
    vi.clearAllMocks();
});

type Appel = { body: Record<string, unknown>; headers?: Record<string, string>; path?: Record<string, number> };
const corps = (f: { mock: { calls: unknown[][] } }, i = 0) => f.mock.calls[i][0] as Appel;

async function ouvrir(props: Partial<Parameters<typeof FenetreCreationAgent>[0]> = {}) {
    const fermer = vi.fn();
    render(<FenetreCreationAgent ouvert fermer={fermer} dossierId={4} {...props} />);
    await screen.findByLabelText("Name");
    return fermer;
}

const nommer = (nom: string) => fireEvent.change(screen.getByLabelText("Name"), { target: { value: nom } });

describe("fenêtre de création unique : chaque chemin", () => {
    it("ne propose aucun choix de recette et ne lit même pas la liste des recettes", async () => {
        await ouvrir();
        expect(document.querySelector('[data-section="recette"]')).toBeNull();
        expect(screen.queryByText("Recette A")).toBeNull();
        expect(screen.queryByText("Recipe")).toBeNull();
        expect(m.recettes).not.toHaveBeenCalled();
    });

    it("groupe avec le builder : crée le principal dans son dossier sans choisir de recette, ouvre le parcours panneau ouvert", async () => {
        const fermer = await ouvrir();
        nommer("Accueil Garnier");
        fireEvent.click(screen.getByText("Start the builder"));
        await waitFor(() => expect(m.groupe).toHaveBeenCalledTimes(1));
        expect(corps(m.groupe).body).toEqual({ name: "Accueil Garnier", folder_id: 4, recette: null });
        await waitFor(() => expect(m.push).toHaveBeenCalledWith("/agents/13?builder=1"));
        expect(fermer).toHaveBeenCalled();
        expect(m.agent).not.toHaveBeenCalled();
    });

    it("avec le builder : description et dossiers d'audit sont déposés dans l'agent créé (É52)", async () => {
        await ouvrir();
        nommer("Accueil Garnier");
        fireEvent.change(screen.getByLabelText("What the company does and what the agent must do, in a few lines."), { target: { value: "Chauffagiste." } });
        const entree = document.querySelector("[data-depot-creation]") as HTMLInputElement;
        fireEvent.change(entree, { target: { files: [new File(["x"], "audit.pdf", { type: "application/pdf" })] } });
        expect(screen.getByText("audit.pdf")).toBeTruthy();
        fireEvent.click(screen.getByText("Start the builder"));
        await waitFor(() => expect(m.depot).toHaveBeenCalledTimes(2));
        const noms = m.depot.mock.calls.map((c) => ((c[0] as { body: { fichier: File } }).body.fichier).name).sort();
        expect(noms).toEqual(["audit.pdf", "description-de-l-entreprise.txt"]);
        expect(corps(m.depot).path).toEqual({ workflow_id: 13 });
    });

    it("sans le builder : aucun dépôt", async () => {
        await ouvrir();
        nommer("Accueil");
        fireEvent.click(screen.getByText("From a recipe"));
        expect(document.querySelector("[data-depart-builder]")).toBeNull();
        fireEvent.click(screen.getByText("Create the draft"));
        await waitFor(() => expect(m.push).toHaveBeenCalled());
        expect(m.depot).not.toHaveBeenCalled();
    });

    it("groupe depuis une recette : le principal s'ouvre sans le builder", async () => {
        await ouvrir();
        nommer("Accueil");
        fireEvent.click(screen.getByText("From a recipe"));
        fireEvent.click(screen.getByText("Create the draft"));
        await waitFor(() => expect(m.push).toHaveBeenCalledWith("/agents/13"));
    });

    it("un agent avec le builder : la description part avec la demande, le nom donné est gardé", async () => {
        await ouvrir();
        nommer("Mon agent");
        fireEvent.click(screen.getByText("One agent"));
        fireEvent.change(screen.getByLabelText("What the company does and what the agent must do, in a few lines."), { target: { value: "Plombier." } });
        fireEvent.click(screen.getByText("Start the builder"));
        await waitFor(() => expect(m.push).toHaveBeenCalledWith("/agents/12?builder=1"));
        expect(corps(m.agent).body).toEqual({ call_type: "inbound", use_case: "Mon agent", activity_description: "Plombier.", recette: null });
        expect(corps(m.maj).body).toEqual({ name: "Mon agent" });
    });

    it("un agent vide : le gabarit neutre, sans description ni builder", async () => {
        await ouvrir();
        nommer("Vide");
        fireEvent.click(screen.getByText("One agent"));
        fireEvent.click(screen.getByText("Empty"));
        expect(screen.queryByLabelText("What the company does and what the agent must do, in a few lines.")).toBeNull();
        fireEvent.click(screen.getByText("Create the draft"));
        await waitFor(() => expect(m.push).toHaveBeenCalledWith("/agents/12"));
        expect(corps(m.agent).body.activity_description).toBe("");
    });

    it("temps réel : le groupe est grisé, les fonctions de chaîne sont listées, l'agent reçoit le cerveau temps réel sans perdre ses réglages", async () => {
        await ouvrir();
        nommer("Rapide");
        fireEvent.click(screen.getByText("Real time"));
        expect((screen.getByText("Group with specialists").closest("button") as HTMLButtonElement).disabled).toBe(true);
        expect(screen.getByText("One agent").closest("button")?.getAttribute("aria-pressed")).toBe("true");
        expect(screen.getByText("Only works in chain")).toBeTruthy();
        expect(screen.getByText("Clerk")).toBeTruthy();
        fireEvent.click(screen.getByText("Start the builder"));
        await waitFor(() => expect(m.maj).toHaveBeenCalledTimes(2));
        expect(m.groupe).not.toHaveBeenCalled();
        const pose = corps(m.maj, 1);
        expect(pose.path).toEqual({ workflow_id: 12 });
        expect(pose.body.workflow_configurations).toEqual({ mark_reglage: 1, model_overrides: { tts: { voice: "v" }, is_realtime: true } });
    });

    it("installation d'un client : chaque requête va à ce client, rien ne s'ouvre, l'appelant reçoit l'agent", async () => {
        const surCree = vi.fn();
        await ouvrir({ organisationId: 77, surCree, departParDefaut: "recette" });
        expect(screen.getByText("From a recipe").closest("button")?.getAttribute("aria-pressed")).toBe("true");
        nommer("Accueil du client");
        fireEvent.click(screen.getByText("Create the draft"));
        await waitFor(() => expect(surCree).toHaveBeenCalledWith({ workflowId: 13, nom: "Accueil du client" }));
        expect(corps(m.groupe).headers).toEqual({ "X-Mark-Organisation": "77" });
        expect(m.push).not.toHaveBeenCalled();
    });

    it("sans nom : l'erreur s'affiche sous le champ, rien n'est créé", async () => {
        await ouvrir();
        fireEvent.click(screen.getByText("Start the builder"));
        expect(await screen.findByText("Give the agent a name.")).toBeTruthy();
        expect(m.groupe).not.toHaveBeenCalled();
        expect(m.agent).not.toHaveBeenCalled();
    });

    it("refus du serveur : rien ne s'ouvre", async () => {
        m.groupe.mockResolvedValueOnce({ data: undefined as unknown as { workflow_id: number; folder_id: number }, error: { detail: "x" } });
        const fermer = await ouvrir();
        nommer("Refusé");
        fireEvent.click(screen.getByText("Start the builder"));
        await waitFor(() => expect(m.groupe).toHaveBeenCalled());
        expect(m.push).not.toHaveBeenCalled();
        expect(fermer).not.toHaveBeenCalled();
    });
});
