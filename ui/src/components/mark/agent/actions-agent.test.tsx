/**
 * [.mark] La barre d'un agent (U3, E37, E46), refaite sur la maquette (K2) : les actions (`ActionsAgent`) et la ligne d'onglets.
 *
 * Questions de ce fichier :
 *
 *     « Builder IA » est dans la barre quand l'éditeur le branche, et mène au Parcours sinon ? « Publier » est grisé AVEC sa
 *     raison tant que les changements du builder sont à relire ? Les cinq onglets sont là, chacun un lien ? « Essayer »
 *     ouvre le bon onglet du panneau d'essai (ou le Parcours depuis un autre onglet) ? Le menu « ⋯ » garde appels, étiquettes,
 *     dupliquer, télécharger, identifiant, et « Exporter vers un client » y ouvre sa fenêtre (H2) ?
 */
import { cleanup, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { ActionsAgent, type EditeurAgent } from "./ActionsAgent";
import { OngletsAgent } from "./OngletsAgent";

const m = vi.hoisted(() => ({ push: vi.fn() }));
vi.mock("next/navigation", () => ({ useRouter: () => ({ push: m.push, refresh: vi.fn() }) }));
vi.mock("next/link", () => ({ default: ({ children, href, ...r }: { children: React.ReactNode; href: string }) => <a href={href} {...r}>{children}</a> }));
vi.mock("sonner", () => ({ toast: Object.assign(vi.fn(), { promise: vi.fn(), success: vi.fn(), error: vi.fn() }) }));
vi.mock("@/client/sdk.gen", () => ({
    duplicateWorkflowEndpointApiV1WorkflowWorkflowIdDuplicatePost: vi.fn(async () => ({ data: { id: 9 } })),
    publishWorkflowApiV1WorkflowWorkflowIdPublishPost: vi.fn(),
    controlesDePublicationApiV1BuilderPublicationWorkflowIdGet: vi.fn(async () => ({ data: { version: 2, bloque: false, controles: [], liste_vocale: [], deploiement_actif: false, forcable: true } })),
    getWorkflowVersionsApiV1WorkflowWorkflowIdVersionsGet: vi.fn(async () => ({ data: [{ id: 1, version_number: 1, status: "published" }] })),
    lireUnGroupeApiV1WorkflowWorkflowIdGroupeGet: vi.fn(async () => ({ data: {} })),
    lireLesEtiquettesApiV1EtiquettesGet: vi.fn(async () => ({ data: { etiquettes: [{ nom: "Recette", nb_agents: 1 }], par_agent: { "5": ["Recette"] } } })),
    poserLesEtiquettesApiV1EtiquettesAgentsWorkflowIdPut: vi.fn(),
    ciblesApiV1ExportAgentWorkflowIdCiblesGet: vi.fn(async () => ({ data: { sens: "exporter", cibles: [{ id: 7, nom: "Nuances de Feu", deja_copie: null }] } })),
    releveApiV1ExportAgentWorkflowIdReleveGet: vi.fn(),
    copierApiV1ExportAgentWorkflowIdCopierPost: vi.fn(),
    lireLesBranchesApiV1BuilderBranchesWorkflowIdGet: vi.fn(async () => ({
        data: {
            repartition_active: true,
            branches: [
                { id: 1, nom: "Principale", principale: true, protegee: false, part: 90, version_en_ligne: 3, versions: [{ id: 30, numero: 3, publiee_le: null }], brouillons: [] },
                { id: 2, nom: "Accueil court", principale: false, protegee: false, part: 10, version_en_ligne: 1, versions: [], brouillons: [] },
            ],
        },
    })),
    creerUneBrancheApiV1BuilderBranchesWorkflowIdPost: vi.fn(),
    reglerLaRepartitionApiV1BuilderBranchesWorkflowIdRepartitionPut: vi.fn(),
}));
vi.mock("@/lib/auth", () => ({ useAuth: () => ({ user: { id: "u" }, loading: false }) }));
vi.mock("../site/useAgentDeSite", () => ({ useAgentDeSite: () => false }));

afterEach(() => {
    cleanup();
    m.push.mockClear();
});

const editeur = (surcharge: Partial<EditeurAgent> = {}): EditeurAgent => ({
    estModifie: false,
    erreursDuParcours: 0,
    rfInstance: { current: null },
    enregistrer: vi.fn(async () => undefined),
    onEssayer: vi.fn(),
    onTelephone: vi.fn(),
    onPublie: vi.fn(),
    builder: { ouvert: false, onToggle: vi.fn(), raisonDeBlocage: null },
    renommer: vi.fn(async () => undefined),
    versionPassee: false,
    retourAuBrouillon: vi.fn(),
    ...surcharge,
});

const base = { agentId: 5, nom: "Agent", versionNumero: 2, versionStatut: "draft", aUnBrouillon: true };

const ouvrir = async (declencheur: HTMLElement) => {
    fireEvent.pointerDown(declencheur, { button: 0, ctrlKey: false });
    fireEvent.click(declencheur);
    return await screen.findByRole("menu");
};

describe("les actions de la barre avec l'éditeur", () => {
    it("« Builder IA » bascule le panneau, et « Publier » est actif sans raison", () => {
        const ed = editeur();
        render(<ActionsAgent {...base} editeur={ed} />);
        fireEvent.click(screen.getByRole("button", { name: "Builder AI" }));
        expect(ed.builder.onToggle).toHaveBeenCalledTimes(1);
        expect((screen.getByRole("button", { name: /Publish/ }) as HTMLButtonElement).disabled).toBe(false);
    });

    it("« Publier » ouvre la fenêtre « Publier vX » au lieu de publier tout de suite (U11)", async () => {
        render(<ActionsAgent {...base} editeur={editeur()} />);
        fireEvent.click(screen.getByRole("button", { name: /Publish/ }));
        expect(await screen.findByText("Publish v2")).toBeTruthy();
    });

    it("grise « Publier » avec la raison tant que les changements du builder sont à relire", () => {
        render(<ActionsAgent {...base} editeur={editeur({ builder: { ouvert: true, onToggle: vi.fn(), raisonDeBlocage: "Review the builder's changes first." } })} />);
        const publier = screen.getByRole("button", { name: /Publish/ }) as HTMLButtonElement;
        expect(publier.disabled).toBe(true);
        expect(publier.title).toBe("Review the builder's changes first.");
        // N2 : la raison est aussi écrite à côté du bouton, pas seulement au survol
        expect(document.querySelector("[data-raison-publier]")?.textContent).toBe("Review the builder's changes first.");
    });

    it("N2 : un changement non enregistré dit sa raison en clair, et sans blocage aucune raison n'est écrite", () => {
        render(<ActionsAgent {...base} editeur={editeur({ estModifie: true })} />);
        expect(document.querySelector("[data-raison-publier]")?.textContent).toBe("Save the changes before publishing.");
        cleanup();
        render(<ActionsAgent {...base} editeur={editeur()} />);
        expect(document.querySelector("[data-raison-publier]")).toBeNull();
    });

    it("sans brouillon, pas de « Publier »", () => {
        render(<ActionsAgent {...base} aUnBrouillon={false} editeur={editeur()} />);
        expect(screen.queryByRole("button", { name: /Publish/ })).toBeNull();
    });

    it("« Essayer » propose navigateur, téléphone, clavier, appelant simulé et jouer les tests", async () => {
        const ed = editeur();
        render(<ActionsAgent {...base} editeur={ed} />);
        const menu = await ouvrir(document.querySelector("[data-menu-essayer]") as HTMLElement);
        fireEvent.click(within(menu).getByText("Call in the browser"));
        expect(ed.onEssayer).toHaveBeenLastCalledWith("audio");
        const menu2 = await ouvrir(document.querySelector("[data-menu-essayer]") as HTMLElement);
        fireEvent.click(within(menu2).getByText("With the keyboard"));
        expect(ed.onEssayer).toHaveBeenLastCalledWith("text");
        const menu3 = await ouvrir(document.querySelector("[data-menu-essayer]") as HTMLElement);
        fireEvent.click(within(menu3).getByText("Simulated caller"));
        expect(ed.onEssayer).toHaveBeenLastCalledWith("simulated");
        const menu4 = await ouvrir(document.querySelector("[data-menu-essayer]") as HTMLElement);
        fireEvent.click(within(menu4).getByText("Phone call"));
        expect(ed.onTelephone).toHaveBeenCalledTimes(1);
        const menu5 = await ouvrir(document.querySelector("[data-menu-essayer]") as HTMLElement);
        expect(within(menu5).getByText("Play the tests").closest("a")?.getAttribute("href")).toBe("/agents/5/tests");
    });

    it("grise « Appel téléphonique » tant que le parcours n'est pas enregistré, et le cache sur une version passée", async () => {
        render(<ActionsAgent {...base} editeur={editeur({ estModifie: true })} />);
        const menu = await ouvrir(document.querySelector("[data-menu-essayer]") as HTMLElement);
        expect(within(menu).getByText("Phone call").closest("[role=menuitem]")?.getAttribute("aria-disabled")).toBe("true");
        cleanup();
        render(<ActionsAgent {...base} editeur={editeur({ versionPassee: true })} />);
        const menu2 = await ouvrir(document.querySelector("[data-menu-essayer]") as HTMLElement);
        expect(within(menu2).queryByText("Phone call")).toBeNull();
    });

    it("R3 : espace inconnu (onglet neuf) : ni « Exporter » (Labo) ni « Ramener » (client) ne sont montrés", async () => {
        window.sessionStorage.clear();
        render(<ActionsAgent {...base} workflowUuid="abc" editeur={editeur()} />);
        const menu = await ouvrir(screen.getByRole("button", { name: "Agent menu" }));
        expect(within(menu).queryByText("Export to a client")).toBeNull();
        expect(within(menu).queryByText(/Bring back/i)).toBeNull();
    });

    it("le menu ⋯ garde appels, étiquettes, dupliquer, télécharger, identifiant ; « Exporter » y ouvre la fenêtre de l'export", async () => {
        window.sessionStorage.setItem("mark:espace-courant", "labo");
        render(<ActionsAgent {...base} workflowUuid="abc" editeur={editeur()} />);
        const menu = await ouvrir(screen.getByRole("button", { name: "Agent menu" }));
        expect(within(menu).getByText("See the calls").closest("a")?.getAttribute("href")).toBe("/agents/5/runs");
        expect(within(menu).getByText("Labels")).toBeTruthy();
        expect(within(menu).getByText("Duplicate")).toBeTruthy();
        expect(within(menu).getByText("Download (JSON)")).toBeTruthy();
        expect(within(menu).getByText("Copy the identifier")).toBeTruthy();
        const exporter = within(menu).getByText("Export to a client").closest("[role=menuitem]");
        expect(exporter?.getAttribute("aria-disabled")).toBeNull();
        fireEvent.click(within(menu).getByText("Export to a client"));
        const fenetre = await screen.findByRole("dialog");
        expect(within(fenetre).getByText("Export to a client")).toBeTruthy();
        expect(await within(fenetre).findByText("Nuances de Feu")).toBeTruthy();
    });

    it("A-5 : Dupliquer propose « Avec ses tests » coché et envoie le nom tapé", async () => {
        const sdk = await import("@/client/sdk.gen");
        const dupliquer = sdk.duplicateWorkflowEndpointApiV1WorkflowWorkflowIdDuplicatePost as unknown as ReturnType<typeof vi.fn>;
        dupliquer.mockClear();
        render(<ActionsAgent {...base} editeur={editeur()} />);
        const menu = await ouvrir(screen.getByRole("button", { name: "Agent menu" }));
        fireEvent.click(within(menu).getByText("Duplicate"));
        const fenetre = await screen.findByRole("dialog");
        const interrupteur = within(fenetre).getByRole("switch", { name: "With its tests" });
        expect(interrupteur.getAttribute("aria-checked")).toBe("true");
        fireEvent.change(within(fenetre).getByLabelText("Name of the copy"), { target: { value: "Ma variante B" } });
        fireEvent.click(within(fenetre).getByRole("button", { name: "Duplicate" }));
        await waitFor(() => expect(dupliquer).toHaveBeenCalled());
        expect((dupliquer.mock.calls[0] as unknown as [{ query: unknown }])[0].query).toEqual({ avec_tests: true, nom: "Ma variante B" });
    });

    it("⋯ › Étiquettes ouvre la fenêtre des étiquettes de l'agent, avec celles qu'il porte déjà cochées", async () => {
        render(<ActionsAgent {...base} editeur={editeur()} />);
        const menu = await ouvrir(screen.getByRole("button", { name: "Agent menu" }));
        fireEvent.click(within(menu).getByText("Labels"));
        const fenetre = await screen.findByRole("dialog");
        expect(fenetre.getAttribute("data-fenetre")).toBe("etiquettes");
        const recette = await within(fenetre).findByRole("checkbox", { name: "Recette" });
        expect(recette.getAttribute("aria-checked")).toBe("true");
    });

    it("la version est un menu qui mène à l'onglet Versions, et « non enregistré » se lit dans la barre", async () => {
        render(<ActionsAgent {...base} editeur={editeur({ estModifie: true })} />);
        expect(document.querySelector("[data-non-enregistre]")).toBeTruthy();
        const menu = await ouvrir(document.querySelector("[data-menu-version]") as HTMLElement);
        expect(within(menu).getByText("Working draft").closest("a")?.getAttribute("href")).toBe("/agents/5/versions");
    });

    it("branche et version forment un seul repère : le sélecteur est collé à la version, « Toutes les versions » est en bas de son menu, aucun bouton « Versions » à part", async () => {
        render(<ActionsAgent {...base} editeur={editeur()} />);
        const selecteur = await screen.findByRole("button", { name: "Branch : Principale · Live 90 %" });
        expect((selecteur as HTMLButtonElement).disabled).toBe(false);
        expect(selecteur.parentElement).toBe(document.querySelector("[data-menu-version]")?.parentElement);
        expect(screen.queryByRole("button", { name: "Versions" })).toBeNull();
        const menu = await ouvrir(document.querySelector("[data-menu-version]") as HTMLElement);
        const dernier = within(menu).getAllByRole("menuitem").at(-1) as HTMLElement;
        expect(dernier.textContent?.trim()).toBe("All versions");
        fireEvent.click(dernier);
        expect(await screen.findByText(/Versions of/)).toBeTruthy();
    });

    it("sur une branche ouverte, sa version en ligne (rangée « archived ») porte le point plein d'une version publiée", async () => {
        window.sessionStorage.setItem("mark:branche:5", "2");
        try {
            render(<ActionsAgent {...base} versionStatut="archived" aUnBrouillon={false} editeur={editeur()} />);
            await screen.findByRole("button", { name: "Branch : Accueil court · Live 10 %" });
            expect(document.querySelector("[data-menu-version] [data-etat]")?.getAttribute("data-etat")).toBe("publie");
        } finally {
            window.sessionStorage.clear();
        }
        cleanup();
        render(<ActionsAgent {...base} versionStatut="archived" aUnBrouillon={false} editeur={editeur()} />);
        expect(document.querySelector("[data-menu-version] [data-etat]")?.getAttribute("data-etat")).toBe("brouillon");
    });

    it("⋯ › Répartition du trafic ouvre la fenêtre de la répartition entre branches", async () => {
        render(<ActionsAgent {...base} editeur={editeur()} />);
        await screen.findByRole("button", { name: /Branch :/ });
        const menu = await ouvrir(screen.getByRole("button", { name: "Agent menu" }));
        fireEvent.click(within(menu).getByText("Traffic split"));
        expect(await screen.findByLabelText("Accueil court")).toBeTruthy();
    });

    it("sur une version passée : lecture seule et retour au brouillon, ni Publier ni Enregistrer ni Renommer", async () => {
        const ed = editeur({ versionPassee: true });
        render(<ActionsAgent {...base} editeur={ed} />);
        fireEvent.click(screen.getByRole("button", { name: "Back to draft" }));
        expect(ed.retourAuBrouillon).toHaveBeenCalledTimes(1);
        expect(screen.getByText(/Read only/)).toBeTruthy();
        expect(screen.queryByRole("button", { name: /Publish/ })).toBeNull();
        expect(screen.queryByRole("button", { name: "Save" })).toBeNull();
        const menu = await ouvrir(screen.getByRole("button", { name: "Agent menu" }));
        expect(within(menu).queryByText("Rename")).toBeNull();
    });

    it("⋯ › Renommer ouvre une fenêtre à un champ qui enregistre le nouveau nom", async () => {
        const ed = editeur();
        render(<ActionsAgent {...base} editeur={ed} />);
        const menu = await ouvrir(screen.getByRole("button", { name: "Agent menu" }));
        fireEvent.click(within(menu).getByText("Rename"));
        const fenetre = await screen.findByRole("dialog");
        fireEvent.change(within(fenetre).getByLabelText("Agent name"), { target: { value: "Accueil v2" } });
        fireEvent.click(within(fenetre).getByRole("button", { name: "Rename" }));
        await vi.waitFor(() => expect(ed.renommer).toHaveBeenCalledWith("Accueil v2"));
    });
});

describe("les actions depuis un onglet autre que le Parcours", () => {
    it("« Essayer » et « Builder IA » ouvrent le Parcours là où l'éditeur les prend", async () => {
        render(<ActionsAgent {...base} />);
        expect(screen.getByRole("link", { name: "Builder AI" }).getAttribute("href")).toBe("/agents/5?builder=1");
        const menu = await ouvrir(document.querySelector("[data-menu-essayer]") as HTMLElement);
        fireEvent.click(within(menu).getByText("With the keyboard"));
        expect(m.push).toHaveBeenCalledWith("/agents/5?essai=text");
    });
});

describe("la ligne d'onglets", () => {
    it("a les cinq onglets, chacun un lien vers son adresse, le Parcours étant l'actif", () => {
        render(<OngletsAgent agentId={5} actif="parcours" />);
        const onglets = within(screen.getByRole("tablist")).getAllByRole("tab");
        expect(onglets.map((o) => o.getAttribute("data-onglet"))).toEqual(["parcours", "reglages", "tests", "appels", "versions"]);
        expect(onglets.map((o) => o.getAttribute("href"))).toEqual(["/agents/5", "/agents/5/settings", "/agents/5/tests", "/agents/5/runs", "/agents/5/versions"]);
        expect(onglets.map((o) => o.getAttribute("aria-selected"))).toEqual(["true", "false", "false", "false", "false"]);
    });
});
