/**
 * [.mark] Chantier agents-specialises, lots 10 et 12 : la liste d'agents en arbre, la vue d'un groupe,
 * les actions d'un sous-dossier, la modale de création à deux cartes, l'archivage d'un principal.
 *
 * ⛔ Ce fichier RENDRE les vrais composants de la liste (``AgentFolderView``, ``FolderSection``,
 * ``WorkflowTable``) : ce qu'on lit, c'est ce que l'écran montre et les appels que ses boutons envoient.
 * (Hors du fournisseur de langue, l'écran parle anglais : les textes cherchés sont les anglais.)
 */
import { cleanup, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import type { FolderResponse, LienDeGroupe, WorkflowListResponse } from "@/client/types.gen";

import { arbreDesDossiers, descendants, grouperLesAgents, rolesDesAgents } from "./liens-groupes";

const m = vi.hoisted(() => ({
    refresh: vi.fn(),
    push: vi.fn(),
    appels: [] as Array<{ nom: string; options: unknown }>,
}));

vi.mock("sonner", () => ({ toast: { success: vi.fn(), error: vi.fn() } }));
vi.mock("next/navigation", () => ({
    useRouter: () => ({ refresh: m.refresh, push: m.push, replace: vi.fn(), back: vi.fn() }),
}));
vi.mock("@/hooks/useOrganizationTimezone", () => ({ useOrganizationTimezone: () => "Europe/Paris" }));
vi.mock("@/client/sdk.gen", async (importOriginal) => {
    const enregistrer = (nom: string, reponse: unknown = { data: {}, error: undefined }) =>
        (options: unknown) => {
            m.appels.push({ nom, options });
            return Promise.resolve(reponse);
        };
    return (await import("../sdk-factice")).sdkFactice(await importOriginal(), {
        createFolderApiV1FolderPost: enregistrer("createFolder", { data: { id: 99 }, error: undefined }),
        moveFolderApiV1FolderFolderIdParentPut: enregistrer("moveFolder"),
        creerUnSpecialiseApiV1WorkflowWorkflowIdGroupeSpecialisePost: enregistrer("creerUnSpecialise", {
            data: { workflow_id: 77 },
            error: undefined,
        }),
        publierLeGroupeApiV1WorkflowWorkflowIdGroupePublierPost: enregistrer("publierLeGroupe", {
            data: { publies: [{ id: 3, name: "Spécialisé un", version_number: 2 }], deja_a_jour: [], refus: null },
            error: undefined,
        }),
        archiverUnPrincipalApiV1WorkflowWorkflowIdGroupeArchiverPost: enregistrer("archiverUnPrincipal", {
            data: { specialises: [3, 4] },
            error: undefined,
        }),
        creerUnGroupeApiV1WorkflowGroupePost: enregistrer("creerUnGroupe", {
            data: { workflow_id: 50, folder_id: 8 },
            error: undefined,
        }),
        updateWorkflowStatusApiV1WorkflowWorkflowIdStatusPut: enregistrer("statut"),
        deleteFolderApiV1FolderFolderIdDelete: enregistrer("supprimerDossier"),
    });
});

const { AgentFolderView } = await import("@/components/workflow/folders/AgentFolderView");
const { ModaleCreationAgent } = await import("./ModaleCreationAgent");

const agent = (id: number, name: string, folder_id: number | null): WorkflowListResponse => ({
    id,
    name,
    status: "active",
    created_at: "2026-10-16T08:00:00Z",
    total_runs: 0,
    folder_id,
});
const dossier = (id: number, name: string, parent_id: number | null = null): FolderResponse => ({
    id,
    name,
    created_at: "2026-10-16T08:00:00Z",
    parent_id,
});

const DOSSIERS = [dossier(1, "Client"), dossier(2, "Groupe du client", 1), dossier(5, "Autre dossier")];
const AGENTS = [
    agent(1, "Principal", 2),
    agent(3, "Spécialisé un", 2),
    agent(4, "Spécialisé deux", 2),
    agent(9, "Agent seul du groupe", 2),
    agent(6, "Seul", 1),
    agent(7, "Hors dossier", null),
];
const LIENS: LienDeGroupe[] = [
    { id: 1, role: "principal", agents_specialises: [3, 4], agent_principal_id: null, cerveau_propre: false },
    { id: 3, role: "specialise", agent_principal_id: 1, agents_specialises: [], cerveau_propre: false },
    { id: 4, role: "specialise", agent_principal_id: 1, agents_specialises: [], cerveau_propre: true },
];
const SERVIS = [{ id: 1, numeros: ["+33 3 44 00 00 00"], etablissementId: "creil" }];

const monter = (props: Partial<Parameters<typeof AgentFolderView>[0]> = {}) =>
    render(<AgentFolderView workflows={AGENTS} folders={DOSSIERS} liens={LIENS} servis={SERVIS} {...props} />);

const basculer = (nom: string) => fireEvent.click(screen.getByRole("button", { name: `Toggle ${nom}` }));

beforeEach(() => {
    m.appels.length = 0;
    m.refresh.mockClear();
    m.push.mockClear();
});
afterEach(cleanup);

describe("[.mark] lire les groupes et l'arbre (pur)", () => {
    it("range un groupe : le principal puis ses spécialisés dans l'ordre de sa liste ; les autres restent seuls", () => {
        const { groupes, seuls } = grouperLesAgents(AGENTS.slice(0, 4), LIENS);
        expect(groupes).toHaveLength(1);
        expect(groupes[0].principal.id).toBe(1);
        expect(groupes[0].specialises.map((a) => a.id)).toEqual([3, 4]);
        expect(seuls.map((a) => a.id)).toEqual([9]);
    });

    it("un spécialisé dont le principal n'est pas dans la liste reste un agent seul (jamais caché)", () => {
        const { groupes, seuls } = grouperLesAgents([AGENTS[1]], LIENS);
        expect(groupes).toEqual([]);
        expect(seuls.map((a) => a.id)).toEqual([3]);
    });

    it("dresse l'arbre : les racines sans parent, les enfants dessous, jamais un dossier perdu", () => {
        const arbre = arbreDesDossiers([...DOSSIERS, dossier(8, "Orphelin", 404)]);
        expect(arbre.map((n) => n.dossier.name)).toEqual(["Autre dossier", "Client", "Orphelin"]);
        const client = arbre.find((n) => n.dossier.id === 1)!;
        expect(client.enfants.map((n) => n.dossier.name)).toEqual(["Groupe du client"]);
    });

    it("liste un dossier et ses descendants (jamais une cible de déplacement)", () => {
        expect([...descendants(DOSSIERS, 1)].sort()).toEqual([1, 2]);
        expect([...descendants(DOSSIERS, 5)]).toEqual([5]);
    });

    it("donne à chaque agent d'un groupe son rôle et le nom de son principal", () => {
        const roles = rolesDesAgents(LIENS, new Map(AGENTS.map((a) => [a.id, a.name])));
        expect(roles.get(1)?.role).toBe("principal");
        expect(roles.get(3)).toMatchObject({ role: "specialise", principalNom: "Principal", cerveauPropre: false });
        expect(roles.get(4)?.cerveauPropre).toBe(true);
        expect(roles.has(6)).toBe(false);
    });
});

describe("[.mark] la liste d'agents en arbre", () => {
    it("replie les dossiers par défaut à chaque niveau, et déplie le groupe qu'on vient de créer", () => {
        monter();
        // Tous repliés : ni le sous-dossier ni le groupe ne se voient.
        expect(screen.queryByText("Groupe du client")).toBeNull();
        expect(screen.queryByText("Seul")).toBeNull();
        cleanup();
        monter({ dossierOuvertId: 2 });
        // Le dossier du groupe est ouvert, et le dossier au-dessus avec lui.
        expect(document.querySelector('[data-vue-groupe="1"]')).not.toBeNull();
        expect(screen.getByText("Seul")).toBeTruthy();
    });

    it("montre un sous-dossier dans son parent seulement quand le parent est ouvert", () => {
        monter();
        expect(screen.queryByRole("button", { name: "Toggle Groupe du client" })).toBeNull();
        basculer("Client");
        expect(screen.getByRole("button", { name: "Toggle Groupe du client" })).toBeTruthy();
        // Le sous-dossier est replié à son tour.
        expect(document.querySelector('[data-vue-groupe="1"]')).toBeNull();
        basculer("Groupe du client");
        expect(document.querySelector('[data-vue-groupe="1"]')).not.toBeNull();
    });

    it("sans dossier : la liste plate d'avant, sans carte ni arbre", () => {
        render(<AgentFolderView workflows={[AGENTS[4], AGENTS[5]]} folders={[]} />);
        expect(screen.getByText("Seul")).toBeTruthy();
        expect(screen.getByText("Hors dossier")).toBeTruthy();
        expect(document.querySelector("[data-vue-groupe]")).toBeNull();
        expect(document.querySelector("[data-badge-groupe]")).toBeNull();
    });
});

describe("[.mark] la vue d'un groupe", () => {
    const ouvrirLeGroupe = () => {
        monter({ dossierOuvertId: 2 });
        return document.querySelector('[data-vue-groupe="1"]') as HTMLElement;
    };

    it("montre la carte du principal (nom, numéros, fiche) et ses spécialisés dessous avec leur badge", () => {
        const vue = ouvrirLeGroupe();
        expect(within(vue).getAllByText("Principal").length).toBeGreaterThan(0);
        expect(vue.textContent).toContain("+33 3 44 00 00 00");
        expect(vue.textContent).toContain("creil");
        const lignes = within(vue).getAllByRole("link", { name: /^Edit / });
        expect(lignes.map((l) => l.getAttribute("aria-label"))).toEqual(["Edit Principal", "Edit Spécialisé un", "Edit Spécialisé deux"]);
        const badges = [...vue.querySelectorAll("[data-badge-groupe]")].map((b) => `${b.getAttribute("data-badge-groupe")}:${b.textContent}`);
        expect(badges).toContain("principal:Main agent");
        expect(badges).toContain("specialise:Specialised agent of Principal");
        expect(badges).toContain("cerveau-propre:own brain");
    });

    it("garde la ligne d'un agent seul, sans carte, même rangé avec un groupe", () => {
        const vue = ouvrirLeGroupe();
        expect(within(vue).queryByText("Agent seul du groupe")).toBeNull();
        // Le dossier du groupe montre l'agent seul dans sa propre table.
        expect(screen.getByText("Agent seul du groupe")).toBeTruthy();
        expect(screen.getByText("Agent seul du groupe").closest("[data-vue-groupe]")).toBeNull();
    });

    it("« + Agent spécialisé » crée un spécialisé du principal par la route du groupe", async () => {
        const vue = ouvrirLeGroupe();
        fireEvent.click(within(vue).getByRole("button", { name: "Agent" }));
        const modale = await screen.findByRole("dialog");
        expect(modale.getAttribute("data-modale")).toBe("nom");
        fireEvent.change(within(modale).getByLabelText("Agent name"), { target: { value: "Troisième" } });
        fireEvent.click(within(modale).getByRole("button", { name: "Create the agent" }));
        await waitFor(() => expect(m.appels.map((a) => a.nom)).toContain("creerUnSpecialise"));
        const appel = m.appels.find((a) => a.nom === "creerUnSpecialise")!.options as { path: { workflow_id: number }; body: { name: string } };
        expect(appel.path.workflow_id).toBe(1);
        expect(appel.body.name).toBe("Troisième");
        await waitFor(() => expect(m.refresh).toHaveBeenCalled());
    });

    it("« Publier le groupe » publie par la route du groupe", async () => {
        const vue = ouvrirLeGroupe();
        fireEvent.click(within(vue).getByRole("button", { name: "Publish the group" }));
        await waitFor(() => expect(m.appels.map((a) => a.nom)).toContain("publierLeGroupe"));
        expect((m.appels.find((a) => a.nom === "publierLeGroupe")!.options as { path: { workflow_id: number } }).path.workflow_id).toBe(1);
    });

    it("archiver un principal demande quoi faire de ses spécialisés, dans une modale centrée", async () => {
        const vue = ouvrirLeGroupe();
        const ligne = within(vue).getByRole("link", { name: "Edit Principal" });
        fireEvent.click(within(ligne).getByRole("button", { name: /Archive/ }));
        const modale = await screen.findByRole("dialog");
        expect(modale.getAttribute("data-modale")).toBe("archiver-principal");
        // Rien n'est parti : on a demandé.
        expect(m.appels.map((a) => a.nom)).not.toContain("statut");
        expect(m.appels.map((a) => a.nom)).not.toContain("archiverUnPrincipal");
        fireEvent.click(within(modale).getByRole("button", { name: "Archive them too" }));
        await waitFor(() => expect(m.appels.map((a) => a.nom)).toContain("archiverUnPrincipal"));
        const appel = m.appels.find((a) => a.nom === "archiverUnPrincipal")!.options as { path: { workflow_id: number }; body: { specialises: string } };
        expect(appel.path.workflow_id).toBe(1);
        expect(appel.body.specialises).toBe("archiver");
    });

    it("archiver un spécialisé ou un agent seul passe par la route d'état d'avant", async () => {
        const vue = ouvrirLeGroupe();
        const ligne = within(vue).getByRole("link", { name: "Edit Spécialisé un" });
        fireEvent.click(within(ligne).getByRole("button", { name: /Archive/ }));
        await waitFor(() => expect(m.appels.map((a) => a.nom)).toContain("statut"));
        expect(m.appels.map((a) => a.nom)).not.toContain("archiverUnPrincipal");
    });
});

describe("[.mark] actions d'un sous-dossier", () => {
    const ouvrirLeMenu = async (nom: string) => {
        monter();
        const entete = screen.getByRole("button", { name: `Toggle ${nom}` }).closest("div") as HTMLElement;
        const declencheur = within(entete.parentElement as HTMLElement).getAllByRole("button", { name: "Folder actions" })[0];
        fireEvent.pointerDown(declencheur, { button: 0, ctrlKey: false });
        fireEvent.click(declencheur);
        return await screen.findByRole("menu");
    };

    it("« Nouveau sous-dossier » demande un nom puis crée un dossier sous celui-ci", async () => {
        const menu = await ouvrirLeMenu("Client");
        fireEvent.click(within(menu).getByText("New sub-folder"));
        const modale = await screen.findByRole("dialog");
        fireEvent.change(within(modale).getByLabelText("Sub-folder name"), { target: { value: "Nouveau groupe" } });
        fireEvent.click(within(modale).getByRole("button", { name: "Create" }));
        await waitFor(() => expect(m.appels.map((a) => a.nom)).toContain("createFolder"));
        expect((m.appels.find((a) => a.nom === "createFolder")!.options as { body: { name: string; parent_id: number } }).body).toEqual({
            name: "Nouveau groupe",
            parent_id: 1,
        });
    });

    it("« Déplacer vers » n'offre ni le dossier lui-même ni ses descendants", async () => {
        const menu = await ouvrirLeMenu("Client");
        fireEvent.click(within(menu).getByText("Move to"));
        const sous = await screen.findAllByRole("menu");
        const cibles = sous.flatMap((s) => [...s.querySelectorAll('[role="menuitem"]')].map((i) => i.textContent ?? ""));
        expect(cibles.some((t) => t.includes("Autre dossier"))).toBe(true);
        expect(cibles.some((t) => t.includes("Groupe du client"))).toBe(false);
        expect(cibles.filter((t) => t.trim() === "Client").length).toBe(0);
        expect(cibles.some((t) => t.includes("Top level"))).toBe(true);
    });
});

describe("[.mark] la modale de création d'un agent", () => {
    const ouvrir = (extra: Partial<Parameters<typeof ModaleCreationAgent>[0]> = {}) => {
        const props = {
            ouvert: true,
            onOuvertChange: vi.fn(),
            onConstructeur: vi.fn(),
            onToileVierge: vi.fn(),
            ...extra,
        };
        render(<ModaleCreationAgent {...props} />);
        return props;
    };

    it("montre deux cartes : les deux chemins d'aujourd'hui, et le graphe avec agents spécialisés", () => {
        ouvrir();
        const modale = screen.getByRole("dialog");
        expect(modale.getAttribute("data-modale")).toBe("creation-d-agent");
        expect(modale.querySelectorAll("[data-carte]")).toHaveLength(2);
        const noeuds = modale.querySelector('[data-carte="graphe-de-noeuds"]') as HTMLElement;
        expect(within(noeuds).getByText("Node graph")).toBeTruthy();
        expect(within(noeuds).getByText("Use the agent builder")).toBeTruthy();
        expect(within(noeuds).getByText("Blank canvas")).toBeTruthy();
        const groupe = modale.querySelector('[data-carte="graphe-avec-agents-specialises"]') as HTMLElement;
        expect(within(groupe).getByText("Graph with specialised agents")).toBeTruthy();
    });

    it("la carte « Graphe de nœuds » garde ses deux chemins", () => {
        const props = ouvrir();
        fireEvent.click(screen.getByText("Use the agent builder"));
        expect(props.onConstructeur).toHaveBeenCalledTimes(1);
        fireEvent.click(screen.getByText("Blank canvas"));
        expect(props.onToileVierge).toHaveBeenCalledTimes(1);
    });

    it("la carte « Graphe avec agents spécialisés » crée le groupe et l'ouvre dans la liste", async () => {
        const props = ouvrir();
        const bouton = screen.getByRole("button", { name: "Create the group" }) as HTMLButtonElement;
        expect(bouton.disabled).toBe(true);
        fireEvent.change(screen.getByLabelText("Group name"), { target: { value: "Accueil du client" } });
        fireEvent.click(screen.getByRole("button", { name: "Create the group" }));
        await waitFor(() => expect(m.appels.map((a) => a.nom)).toContain("creerUnGroupe"));
        expect((m.appels.find((a) => a.nom === "creerUnGroupe")!.options as { body: unknown }).body).toEqual({ name: "Accueil du client", folder_id: null });
        await waitFor(() => expect(m.push).toHaveBeenCalledWith("/workflow?dossier=8"));
        expect(props.onOuvertChange).toHaveBeenCalledWith(false);
    });
});
