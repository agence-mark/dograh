/**
 * [.mark] Correctifs d'écran, points 3 et 4 : la liste des Agents. Icône devant le nom, ligne grise sous le nom, plus de colonne
 * « Appels 7 j », les spécialisés rangés sous leur principal et repliables, dossiers dans le menu « Déplacer » avec leur icône
 * et leurs sous-dossiers décalés. (Hors du fournisseur de langue, l'écran parle anglais.)
 */
import { cleanup, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import type { FolderResponse, LienDeGroupe } from "@/client/types.gen";

import { lignesAvecSpecialises } from "./lignes-agents";

vi.mock("sonner", () => ({ toast: { success: vi.fn(), error: vi.fn() } }));
vi.mock("next/navigation", () => ({ useRouter: () => ({ refresh: vi.fn(), push: vi.fn(), replace: vi.fn(), back: vi.fn() }) }));
vi.mock("@/hooks/useOrganizationTimezone", () => ({ useOrganizationTimezone: () => "Europe/Paris" }));
vi.mock("@/lib/auth", () => {
    const auth = { user: { id: "u" }, loading: false };
    return { useAuth: () => auth };
});
vi.mock("@/client/sdk.gen", async (importOriginal) => {
    return (await import("../sdk-factice")).sdkFactice(await importOriginal(), {
        lireLesEtiquettesApiV1EtiquettesGet: () => Promise.resolve({ data: { etiquettes: [], par_agent: {} }, error: undefined }),
    });
});

const { ListeAgents } = await import("./ListeAgents");

const agent = (id: number, name: string, folder_id: number | null = null) => ({
    id,
    name,
    status: "active",
    created_at: "2026-10-16T08:00:00Z",
    total_runs: 0,
    folder_id,
    appels_7j: 4,
});
const dossiers: FolderResponse[] = [
    { id: 1, name: "Clients", created_at: "2026-10-16T08:00:00Z", parent_id: null },
    { id: 2, name: "Durand", created_at: "2026-10-16T08:00:00Z", parent_id: 1 },
];
// Le spécialisé (id 1) est listé AVANT son principal (id 2) : le rangement sous le principal ne dépend pas de l'ordre de la liste.
const actifs = [agent(10, "Seul"), agent(11, "Entretien"), agent(12, "Accueil"), agent(13, "Réclamations")];
const liens = [
    { id: 12, role: "principal", agent_principal_id: null, agents_specialises: [13, 11], cerveau_propre: false },
    { id: 11, role: "specialise", agent_principal_id: 12, agents_specialises: [], cerveau_propre: true },
    { id: 13, role: "specialise", agent_principal_id: 12, agents_specialises: [], cerveau_propre: false },
] as unknown as LienDeGroupe[];

const monter = () => render(<ListeAgents actifs={actifs as never} archives={[]} dossiers={dossiers} liens={liens} dossierOuvertId={null} />);
const ordre = () => [...document.querySelectorAll("tr[data-agent]")].map((l) => l.getAttribute("data-agent"));

afterEach(cleanup);

describe("lignesAvecSpecialises", () => {
    it("range chaque spécialisé sous son principal, dans l'ordre du principal ; un orphelin reste à part", () => {
        const roles = new Map([
            [12, { role: "principal" as const, principalId: null, specialises: [13, 11] }],
            [11, { role: "specialise" as const, principalId: 12, specialises: [] }],
            [13, { role: "specialise" as const, principalId: 12, specialises: [] }],
            [14, { role: "specialise" as const, principalId: 99, specialises: [] }],
        ]);
        const lignes = lignesAvecSpecialises([{ id: 11 }, { id: 14 }, { id: 12 }, { id: 13 }], roles);
        expect(lignes.map((l) => [l.agent.id, l.enfants.map((e) => e.id)])).toEqual([
            [14, []],
            [12, [13, 11]],
        ]);
    });
});

describe("la liste des Agents : groupes (point 3)", () => {
    it("les spécialisés suivent leur principal, avec la ligne grise et sans colonne « Calls 7 d »", () => {
        monter();
        expect(ordre()).toEqual(["10", "12", "13", "11"]);
        expect(screen.queryByText("Calls 7 d")).toBeNull();
        const principal = document.querySelector('tr[data-agent="12"]') as HTMLElement;
        expect(principal.querySelector('[data-sous-ligne-groupe="principal"]')?.textContent).toBe("2 specialised agents");
        expect(principal.querySelector('[data-icone-agent="principal"]')).not.toBeNull();
        const specialise = document.querySelector('tr[data-agent="11"]') as HTMLElement;
        expect(specialise.querySelector('[data-sous-ligne-groupe="specialise"]')?.textContent).toContain("Specialised agent of Accueil");
        expect(specialise.querySelector('[data-icone-agent="specialise"]')).not.toBeNull();
        expect(specialise.querySelector("[data-badge-groupe='cerveau-propre']")).not.toBeNull(); // visible au survol seulement (CSS)
        expect(document.querySelector('tr[data-agent="10"] [data-icone-agent="simple"]')).not.toBeNull();
    });

    it("un principal sans spécialisé dit « no specialist », jamais « 0 »", () => {
        const sans = [{ id: 20, role: "principal", agent_principal_id: null, agents_specialises: [], cerveau_propre: false }] as unknown as LienDeGroupe[];
        render(<ListeAgents actifs={[agent(20, "Accueil seul")] as never} archives={[]} dossiers={dossiers} liens={sans} dossierOuvertId={null} />);
        expect(document.querySelector('tr[data-agent="20"] [data-sous-ligne-groupe="principal"]')?.textContent).toBe("no specialist");
    });

    it("le chevron replie et déplie les spécialisés", () => {
        monter();
        const chevron = screen.getByRole("button", { name: /Collapse the specialised agents of Accueil/ });
        fireEvent.click(chevron);
        expect(ordre()).toEqual(["10", "12"]);
        fireEvent.click(screen.getByRole("button", { name: /Expand the specialised agents of Accueil/ }));
        expect(ordre()).toEqual(["10", "12", "13", "11"]);
    });
});

describe("le menu « ⋯ » d'un agent (point 4)", () => {
    it("« Ouvrir » et « Déplacer » ont une icône ; chaque dossier a la sienne, le sous-dossier est décalé", async () => {
        monter();
        const ligne = document.querySelector('tr[data-agent="10"]') as HTMLElement;
        const declencheur = within(ligne).getByRole("button", { name: /Agent actions/ });
        fireEvent.pointerDown(declencheur, { button: 0, ctrlKey: false });
        const menu = await screen.findByRole("menu");
        expect(within(menu).getByText("Open").closest("a")?.querySelector("svg")).not.toBeNull();
        const deplacer = within(menu).getByText("Move to a folder").closest("[role=menuitem]") as HTMLElement;
        expect(deplacer.querySelector("svg")).not.toBeNull();
        fireEvent.keyDown(deplacer, { key: "ArrowRight" });
        await waitFor(() => expect(document.querySelectorAll("[data-dossier-menu]")).toHaveLength(2));
        const [parent, enfant] = [...document.querySelectorAll<HTMLElement>("[data-dossier-menu]")];
        const item = (el: HTMLElement) => el;
        expect(item(parent).querySelector("svg")).not.toBeNull();
        expect(item(enfant).querySelector("svg")).not.toBeNull();
        expect(parseInt(item(enfant).style.paddingLeft)).toBeGreaterThan(parseInt(item(parent).style.paddingLeft));
    });
});
