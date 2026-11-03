/**
 * [.mark] La page d'un agent (U3) : les onglets, le menu du membre du groupe, l'onglet Versions, la barre du canevas.
 *
 * Questions de ce fichier :
 *
 *     Chaque adresse retombe-t-elle sur le bon onglet ? Le menu du groupe n'apparaît-il que pour un membre d'un groupe,
 *     et mène-t-il au même onglet chez l'autre membre ? L'onglet Versions ouvre-t-il la version en cours modifiable et
 *     les autres en lecture seule, compare-t-il, et pagine-t-il côté serveur ? « Prompt général » ouvre-t-il la
 *     fenêtre du nœud global ?
 */
import { cleanup, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import type { WorkflowVersionResponse } from "@/client/types.gen";

import { BarreCanevas } from "./BarreCanevas";
import { membresDuGroupe } from "./membres-groupe";
import { MenuMembre } from "./MenuMembre";
import { adresseOnglet, ongletDeAdresse,ONGLETS_AGENT } from "./onglets-agent";
import { useOuvertureNoeud } from "./ouverture-noeud";
import { adresseDeLaVersion, PageVersions } from "./PageVersions";

const m = vi.hoisted(() => ({ versions: vi.fn(), groupe: vi.fn() }));
vi.mock("next/navigation", () => ({ useRouter: () => ({ push: vi.fn() }) }));
vi.mock("next/link", () => ({ default: ({ children, href, ...r }: { children: React.ReactNode; href: string }) => <a href={href} {...r}>{children}</a> }));
vi.mock("sonner", () => ({ toast: Object.assign(vi.fn(), { error: vi.fn(), success: vi.fn() }) }));
vi.mock("@/components/flow/renderer", () => ({
    useNodeSpecs: () => ({ specs: [{ name: "agentNode", display_name: "Agent Step", category: "call_node", properties: [] }] }),
}));
vi.mock("@/lib/auth", () => ({ useAuth: () => ({ user: { id: "u" }, loading: false }) }));
vi.mock("@/hooks/useOrganizationTimezone", () => ({ useOrganizationTimezone: () => "UTC" }));
vi.mock("@/client/sdk.gen", () => ({
    getWorkflowVersionsApiV1WorkflowWorkflowIdVersionsGet: m.versions,
    lireUnGroupeApiV1WorkflowWorkflowIdGroupeGet: m.groupe,
}));
vi.mock("@/app/workflow/[workflowId]/components/WorkflowVersionDiffDialog", () => ({
    WorkflowVersionDiffDialog: ({ previousVersion, selectedVersion }: { previousVersion: WorkflowVersionResponse; selectedVersion: WorkflowVersionResponse }) => (
        <div data-testid="diff">{`v${previousVersion.version_number}->v${selectedVersion.version_number}`}</div>
    ),
}));

afterEach(cleanup);

const v = (n: number, status: string): WorkflowVersionResponse => ({
    id: 100 + n,
    version_number: n,
    status,
    created_at: "2026-01-01T00:00:00Z",
    workflow_json: { nodes: [], edges: [] },
});

describe("les onglets", () => {
    it("sont cinq, dans l'ordre du plan, sans « Autour de l'appel »", () => {
        expect(ONGLETS_AGENT.map((o) => o.id)).toEqual(["parcours", "reglages", "tests", "appels", "versions"]);
    });

    it("chaque adresse retombe sur son onglet, toute autre suite sur le Parcours", () => {
        for (const o of ONGLETS_AGENT) expect(ongletDeAdresse(adresseOnglet(7, o.id))).toBe(o.id);
        expect(ongletDeAdresse("/agents/7")).toBe("parcours");
        expect(ongletDeAdresse("/agents/7/inconnu")).toBe("parcours");
        expect(ongletDeAdresse("/labo/agents")).toBe("parcours");
    });
});

describe("le menu du membre du groupe", () => {
    it("range le principal d'abord, puis les spécialisés ; un agent seul n'a pas de membres", () => {
        expect(membresDuGroupe({ principal: { id: 1, name: "Accueil" }, specialises: [{ id: 2, name: "Entretien" }] })).toEqual([
            { id: 1, nom: "Accueil", principal: true },
            { id: 2, nom: "Entretien", principal: false },
        ]);
        expect(membresDuGroupe({ principal: null, specialises: [] })).toEqual([]);
        expect(membresDuGroupe(undefined)).toEqual([]);
    });

    it("n'affiche rien pour un agent seul", async () => {
        m.groupe.mockResolvedValue({ data: { principal: null, specialises: [] } });
        render(<MenuMembre agentId={1} onglet="tests" />);
        await waitFor(() => expect(m.groupe).toHaveBeenCalled());
        expect(document.querySelector("[data-menu-membre]")).toBeNull();
    });

    it("mène au même onglet chez l'autre membre du groupe", async () => {
        m.groupe.mockResolvedValue({ data: { principal: { id: 1, name: "Accueil" }, specialises: [{ id: 2, name: "Entretien" }] } });
        render(<MenuMembre agentId={2} onglet="tests" />);
        const declencheur = await waitFor(() => {
            const d = document.querySelector("[data-menu-membre]");
            if (!d) throw new Error("menu absent");
            return d as HTMLElement;
        });
        expect(declencheur.textContent).toContain("Entretien");
        fireEvent.pointerDown(declencheur, { button: 0, ctrlKey: false });
        fireEvent.click(declencheur);
        const menu = await screen.findByRole("menu");
        expect(within(menu).getByText("Accueil (main)").closest("a")?.getAttribute("href")).toBe("/agents/1/tests");
    });
});

describe("l'onglet Versions", () => {
    beforeEach(() => {
        m.versions.mockReset();
    });

    it("la version en cours (le brouillon) ouvre le Parcours modifiable, les autres une version en lecture seule", () => {
        expect(adresseDeLaVersion(12, v(21, "draft"), true)).toBe("/agents/12");
        expect(adresseDeLaVersion(12, v(20, "published"), false)).toBe("/agents/12?version=20");
    });

    const ouvrirLigne = async (ligne: HTMLElement) => {
        const declencheur = within(ligne).getByRole("button", { name: /Version menu/ });
        fireEvent.pointerDown(declencheur, { button: 0, ctrlKey: false });
        fireEvent.click(declencheur);
        return await screen.findByRole("menu");
    };

    it("liste les versions d'une page, nomme l'état et marque la version en cours", async () => {
        m.versions.mockImplementation(async ({ query }: { query: { status?: string } }) =>
            query.status === "draft" ? { data: [v(21, "draft")] } : { data: [v(21, "draft"), v(20, "published"), v(19, "archived")] },
        );
        render(<PageVersions agentId={12} />);
        await screen.findByText("v21 draft");
        const lignes = document.querySelectorAll("tbody tr");
        expect(lignes).toHaveLength(3);
        expect(lignes[0].textContent).toContain("v21 draft");
        expect(lignes[0].textContent).toContain("current");
        expect(lignes[1].textContent).toContain("v20 published");
        const menu1 = await ouvrirLigne(lignes[1] as HTMLElement);
        expect(within(menu1).getByText("Open").closest("a")?.getAttribute("href")).toBe("/agents/12?version=20");
        fireEvent.keyDown(menu1, { key: "Escape" });
        const menu0 = await ouvrirLigne(lignes[0] as HTMLElement);
        expect(within(menu0).getByText("Open").closest("a")?.getAttribute("href")).toBe("/agents/12");
        // Une page de 25 : une ligne de plus est demandée pour savoir s'il y a une suite, jamais tout l'historique.
        const liste = m.versions.mock.calls.map((c) => c[0].query).find((q: { status?: string }) => !q.status);
        expect(liste).toEqual({ limit: 26, offset: 0 });
    });

    it("sans brouillon, la publiée la plus récente est la version en cours (lien modifiable)", async () => {
        m.versions.mockImplementation(async ({ query }: { query: { status?: string } }) =>
            query.status === "draft" ? { data: [] } : { data: [v(20, "published"), v(19, "archived")] },
        );
        render(<PageVersions agentId={12} />);
        await screen.findByText("v20 published");
        const lignes = document.querySelectorAll("tbody tr");
        const menu0 = await ouvrirLigne(lignes[0] as HTMLElement);
        expect(within(menu0).getByText("Open").closest("a")?.getAttribute("href")).toBe("/agents/12");
        fireEvent.keyDown(menu0, { key: "Escape" });
        const menu1 = await ouvrirLigne(lignes[1] as HTMLElement);
        expect(within(menu1).getByText("Open").closest("a")?.getAttribute("href")).toBe("/agents/12?version=19");
    });

    it("compare une version à la précédente en relisant la paire au bon rang", async () => {
        m.versions.mockImplementation(async ({ query }: { query: { status?: string; limit: number; offset?: number } }) => {
            if (query.status === "draft") return { data: [] };
            if (query.limit === 2) return { data: [v(20, "published"), v(19, "archived")] };
            return { data: [v(20, "published"), v(19, "archived")] };
        });
        render(<PageVersions agentId={12} />);
        await screen.findByText("v20 published");
        const menu = await ouvrirLigne(document.querySelectorAll("tbody tr")[0] as HTMLElement);
        fireEvent.click(within(menu).getByText("Compare with the previous one"));
        expect((await screen.findByTestId("diff")).textContent).toBe("v19->v20");
        expect(m.versions.mock.calls.some((c) => c[0].query.limit === 2 && c[0].query.offset === 0)).toBe(true);
    });

    it("n'invente pas de comparaison pour la plus ancienne version", async () => {
        m.versions.mockImplementation(async ({ query }: { query: { status?: string; limit: number } }) => {
            if (query.status === "draft") return { data: [] };
            return query.limit === 2 ? { data: [v(1, "archived")] } : { data: [v(1, "archived")] };
        });
        render(<PageVersions agentId={12} />);
        await screen.findByText("v1 archived");
        const menu = await ouvrirLigne(document.querySelectorAll("tbody tr")[0] as HTMLElement);
        fireEvent.click(within(menu).getByText("Compare with the previous one"));
        await waitFor(() => expect(m.versions.mock.calls.some((c) => c[0].query.limit === 2)).toBe(true));
        expect(screen.queryByTestId("diff")).toBeNull();
    });
});

describe("la barre du canevas", () => {
    const monter = (surcharge: Partial<React.ComponentProps<typeof BarreCanevas>> = {}) => {
        const actions = {
            onPromptGeneral: vi.fn(),
            onAjouter: vi.fn(),
            onZoomAvant: vi.fn(),
            onZoomArriere: vi.fn(),
            onAjuster: vi.fn(),
            onRanger: vi.fn(),
        };
        render(<BarreCanevas lectureSeule={false} zoom={80} changementDuBuilder={false} noeuds={[]} {...actions} {...surcharge} />);
        return actions;
    };
    const ouvrirNoeud = async () => {
        const noeud = screen.getByRole("button", { name: "Node" });
        fireEvent.pointerDown(noeud, { button: 0, ctrlKey: false });
        fireEvent.click(noeud);
        return await screen.findByRole("menu");
    };

    it("branche chaque bouton sur son geste, et dit le zoom", async () => {
        const a = monter({ bibliothequeHref: "/labo/bibliotheque" });
        fireEvent.click(screen.getByRole("button", { name: "General prompt" }));
        fireEvent.click(screen.getByRole("button", { name: "Zoom in" }));
        fireEvent.click(screen.getByRole("button", { name: "Zoom out" }));
        fireEvent.click(screen.getByRole("button", { name: "Fit the view" }));
        expect(a.onPromptGeneral).toHaveBeenCalledTimes(1);
        expect(a.onZoomAvant).toHaveBeenCalledTimes(1);
        expect(a.onZoomArriere).toHaveBeenCalledTimes(1);
        expect(a.onAjuster).toHaveBeenCalledTimes(1);
        expect(screen.getByText("80 %")).toBeTruthy();
        expect(screen.getByRole("link", { name: "Library" }).getAttribute("href")).toBe("/labo/bibliotheque");
        // Le menu « Nœud » liste les types que le serveur sait poser, et range les nœuds.
        fireEvent.click(within(await ouvrirNoeud()).getByText("Agent Step"));
        expect(a.onAjouter).toHaveBeenCalledWith("agentNode");
        fireEvent.click(within(await ouvrirNoeud()).getByText("Tidy up the nodes"));
        expect(a.onRanger).toHaveBeenCalledTimes(1);
    });

    it("n'a pas de lien « Bibliothèque » hors du Labo, et en lecture seule garde le zoom et « Ajuster »", () => {
        monter({ lectureSeule: true });
        expect(screen.queryByRole("link", { name: "Library" })).toBeNull();
        expect(screen.queryByRole("button", { name: "General prompt" })).toBeNull();
        expect(screen.queryByRole("button", { name: "Node" })).toBeNull();
        expect(screen.getByRole("button", { name: "Zoom in" })).toBeTruthy();
        expect(screen.getByRole("button", { name: "Fit the view" })).toBeTruthy();
    });

    it("une demande d'ouverture d'un nœud change de clé à chaque fois, même pour le même nœud", () => {
        useOuvertureNoeud.getState().demander("n1");
        const premiere = useOuvertureNoeud.getState().demande;
        useOuvertureNoeud.getState().demander("n1");
        const seconde = useOuvertureNoeud.getState().demande;
        expect(premiere?.id).toBe("n1");
        expect(seconde?.cle).toBe((premiere?.cle ?? 0) + 1);
    });
});
