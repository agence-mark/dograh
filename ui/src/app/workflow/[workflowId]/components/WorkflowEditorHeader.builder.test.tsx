/**
 * [.mark] La barre d'un agent, onglet Parcours (U3, E37, E46).
 *
 * Questions de ce fichier :
 *
 *     « Builder IA » est dans la barre quand le builder est branché, absent sinon ? « Publier » est grisé AVEC sa raison
 *     tant que les changements du builder sont à relire, et pas autrement ? Les cinq onglets sont là, chacun un lien ?
 *     « Essayer » ouvre le bon onglet du panneau d'essai ? « Exporter vers un client » n'est pas encore là (H2) ?
 */
import { cleanup, fireEvent, render, screen, within } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { WorkflowEditorHeader } from "./WorkflowEditorHeader";

vi.mock("next/navigation", () => ({ useRouter: () => ({ push: vi.fn() }) }));
vi.mock("next/link", () => ({ default: ({ children, href, ...r }: { children: React.ReactNode; href: string }) => <a href={href} {...r}>{children}</a> }));
vi.mock("sonner", () => ({ toast: Object.assign(vi.fn(), { promise: vi.fn(), success: vi.fn(), error: vi.fn() }) }));
vi.mock("@/client/sdk.gen", () => ({
    duplicateWorkflowEndpointApiV1WorkflowWorkflowIdDuplicatePost: vi.fn(),
    publishWorkflowApiV1WorkflowWorkflowIdPublishPost: vi.fn(),
    lireUnGroupeApiV1WorkflowWorkflowIdGroupeGet: vi.fn(async () => ({ data: {} })),
    lireLesEtiquettesApiV1EtiquettesGet: vi.fn(async () => ({ data: { etiquettes: [{ nom: "Recette", nb_agents: 1 }], par_agent: { "5": ["Recette"] } } })),
    poserLesEtiquettesApiV1EtiquettesAgentsWorkflowIdPut: vi.fn(),
}));
vi.mock("@/lib/auth", () => ({ useAuth: () => ({ user: { id: "u" }, loading: false }) }));
vi.mock("@/components/ui/sidebar", () => ({ useSidebar: () => ({ toggleSidebar: vi.fn() }) }));

afterEach(cleanup);

const base = {
    workflowName: "Agent",
    isDirty: false,
    workflowValidationErrors: [],
    rfInstance: { current: null },
    workflowId: 5,
    saveWorkflow: vi.fn(),
    user: { id: "u" },
    onPhoneCallClick: vi.fn(),
    onTestAgentClick: vi.fn(),
    isViewingHistoricalVersion: false,
    onBackToDraft: vi.fn(),
    hasDraft: true,
    onPublished: vi.fn(),
    renameWorkflow: vi.fn(),
};

const ouvrir = async (declencheur: HTMLElement) => {
    fireEvent.pointerDown(declencheur, { button: 0, ctrlKey: false });
    fireEvent.click(declencheur);
    return await screen.findByRole("menu");
};

describe("la barre du haut avec le builder", () => {
    it("montre « Builder IA » quand le builder est branché, et « Publier » est actif sans raison", () => {
        const onToggle = vi.fn();
        render(<WorkflowEditorHeader {...base} builder={{ ouvert: false, onToggle, raisonDeBlocage: null }} />);
        fireEvent.click(screen.getByRole("button", { name: "Builder AI" }));
        expect(onToggle).toHaveBeenCalledTimes(1);
        expect((screen.getByRole("button", { name: /Publish/ }) as HTMLButtonElement).disabled).toBe(false);
    });

    it("grise « Publier » avec la raison tant que les changements du builder sont à relire", () => {
        render(
            <WorkflowEditorHeader
                {...base}
                builder={{ ouvert: true, onToggle: vi.fn(), raisonDeBlocage: "Review the builder's changes first." }}
            />,
        );
        const publier = screen.getByRole("button", { name: /Publish/ }) as HTMLButtonElement;
        expect(publier.disabled).toBe(true);
        expect(publier.title).toBe("Review the builder's changes first.");
        expect(document.querySelector("[data-raison-publication]")?.textContent).toBe("Review the builder's changes first.");
    });

    it("sans builder branché, la barre n'a pas le bouton", () => {
        render(<WorkflowEditorHeader {...base} />);
        expect(screen.queryByRole("button", { name: "Builder AI" })).toBeNull();
        expect((screen.getByRole("button", { name: /Publish/ }) as HTMLButtonElement).disabled).toBe(false);
    });
});

describe("la ligne d'onglets et les menus de la barre", () => {
    it("a les cinq onglets, chacun un lien vers son adresse, le Parcours étant l'actif", () => {
        render(<WorkflowEditorHeader {...base} />);
        const onglets = within(screen.getByRole("tablist")).getAllByRole("tab");
        expect(onglets.map((o) => o.getAttribute("data-onglet"))).toEqual(["parcours", "reglages", "tests", "appels", "versions"]);
        expect(onglets.map((o) => o.getAttribute("href"))).toEqual([
            "/agents/5",
            "/agents/5/settings",
            "/agents/5/tests",
            "/agents/5/runs",
            "/agents/5/versions",
        ]);
        expect(onglets.map((o) => o.getAttribute("aria-selected"))).toEqual(["true", "false", "false", "false", "false"]);
        expect(screen.queryByRole("tab", { name: /Around the call|Autour de l'appel/ })).toBeNull();
    });

    it("« Essayer » propose navigateur, téléphone, clavier, appelant simulé et jouer les tests", async () => {
        const onTestAgentClick = vi.fn();
        const onPhoneCallClick = vi.fn();
        render(<WorkflowEditorHeader {...base} onTestAgentClick={onTestAgentClick} onPhoneCallClick={onPhoneCallClick} />);
        const menu = await ouvrir(document.querySelector("[data-menu-essayer]") as HTMLElement);
        fireEvent.click(within(menu).getByText("In the browser"));
        expect(onTestAgentClick).toHaveBeenLastCalledWith("audio");

        const menu2 = await ouvrir(document.querySelector("[data-menu-essayer]") as HTMLElement);
        fireEvent.click(within(menu2).getByText("With the keyboard"));
        expect(onTestAgentClick).toHaveBeenLastCalledWith("text");

        const menu3 = await ouvrir(document.querySelector("[data-menu-essayer]") as HTMLElement);
        fireEvent.click(within(menu3).getByText("With a simulated caller"));
        expect(onTestAgentClick).toHaveBeenLastCalledWith("simulated");

        const menu4 = await ouvrir(document.querySelector("[data-menu-essayer]") as HTMLElement);
        fireEvent.click(within(menu4).getByText("By phone"));
        expect(onPhoneCallClick).toHaveBeenCalledTimes(1);

        const menu5 = await ouvrir(document.querySelector("[data-menu-essayer]") as HTMLElement);
        expect(within(menu5).getByText("Play the tests").closest("a")?.getAttribute("href")).toBe("/agents/5/tests");
    });

    it("grise « Par téléphone » tant que le parcours n'est pas enregistré, et le cache sur une version passée", async () => {
        render(<WorkflowEditorHeader {...base} isDirty />);
        const menu = await ouvrir(document.querySelector("[data-menu-essayer]") as HTMLElement);
        expect(within(menu).getByText("By phone").closest("[role=menuitem]")?.getAttribute("aria-disabled")).toBe("true");
        cleanup();
        render(<WorkflowEditorHeader {...base} isViewingHistoricalVersion />);
        const menu2 = await ouvrir(document.querySelector("[data-menu-essayer]") as HTMLElement);
        expect(within(menu2).queryByText("By phone")).toBeNull();
    });

    it("le menu ⋮ garde appels, dupliquer, télécharger et copier l'UUID ; « Exporter » n'y est pas encore", async () => {
        render(<WorkflowEditorHeader {...base} workflowUuid="abc" />);
        const menu = await ouvrir(screen.getByRole("button", { name: "Agent menu" }));
        expect(within(menu).getByText("Calls").closest("a")?.getAttribute("href")).toBe("/agents/5/runs");
        expect(within(menu).getByText("Duplicate")).toBeTruthy();
        expect(within(menu).getByText("Download (JSON)")).toBeTruthy();
        expect(within(menu).getByText("Copy the UUID")).toBeTruthy();
        expect(within(menu).queryByText(/Export|Exporter/)).toBeNull();
    });

    it("⋮ › Étiquettes ouvre la fenêtre des étiquettes de l'agent, avec celles qu'il porte déjà cochées", async () => {
        render(<WorkflowEditorHeader {...base} />);
        const menu = await ouvrir(screen.getByRole("button", { name: "Agent menu" }));
        fireEvent.click(within(menu).getByText("Labels"));
        const fenetre = await screen.findByRole("dialog");
        expect(fenetre.getAttribute("data-fenetre")).toBe("etiquettes");
        const recette = await within(fenetre).findByRole("checkbox", { name: "Recette" });
        expect(recette.getAttribute("aria-checked")).toBe("true");
    });

    it("la version est un menu qui mène à l'onglet Versions, et « non enregistré » se lit dans la ligne d'onglets", async () => {
        render(<WorkflowEditorHeader {...base} isDirty activeVersionLabel="v4 (Draft)" />);
        expect(document.querySelector("[data-ligne-onglets] [data-non-enregistre]")).toBeTruthy();
        const menu = await ouvrir(screen.getByRole("button", { name: /v4 \(Draft\)/ }));
        expect(within(menu).getByText("All versions").closest("a")?.getAttribute("href")).toBe("/agents/5/versions");
    });

    it("sur une version passée : bandeau lecture seule et retour au brouillon, ni Publier ni Enregistrer", () => {
        const onBackToDraft = vi.fn();
        render(<WorkflowEditorHeader {...base} isViewingHistoricalVersion activeVersionLabel="v2" onBackToDraft={onBackToDraft} />);
        fireEvent.click(screen.getByRole("button", { name: "Back to draft" }));
        expect(onBackToDraft).toHaveBeenCalledTimes(1);
        expect(screen.getByText(/Read only/)).toBeTruthy();
        expect(screen.queryByRole("button", { name: /Publish/ })).toBeNull();
        expect(screen.queryByRole("button", { name: "Save" })).toBeNull();
        // Le nom ne se renomme plus.
        expect(screen.queryByRole("button", { name: /Rename the agent/ })).toBeNull();
    });

    it("un clic sur le nom le renomme (Entrée enregistre)", async () => {
        const renameWorkflow = vi.fn(async () => undefined);
        render(<WorkflowEditorHeader {...base} renameWorkflow={renameWorkflow} />);
        fireEvent.click(screen.getByRole("button", { name: /Rename the agent/ }));
        const champ = screen.getByLabelText("Agent name");
        fireEvent.change(champ, { target: { value: "Accueil v2" } });
        fireEvent.keyDown(champ, { key: "Enter" });
        await vi.waitFor(() => expect(renameWorkflow).toHaveBeenCalledWith("Accueil v2"));
    });
});
