/**
 * [.mark] U9 (lot H2) : l'accueil d'un client.
 *
 * Questions de ce fichier :
 *
 *     Chaque ligne vient d'une route réelle (agents, base, après-appel, intégrations, téléphonie, clés, À améliorer) ?
 *     Une lecture qui échoue se dit « illisible » au lieu d'inventer un état ? Un client sans agent montre l'état vide « premier » ?
 *     « Ouvrir son portail » est désactivé avec sa raison ? Les liens restent dans l'espace du client ?
 */
import { cleanup, render, screen, waitFor, within } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import AccueilClient from "./AccueilClient";

const m = vi.hoisted(() => ({
    agents: vi.fn(),
    base: vi.fn(),
    apres: vi.fn(),
    connexions: vi.fn(),
    telephonie: vi.fn(),
    cles: vi.fn(),
    tri: vi.fn(),
    chiffres: vi.fn(),
}));
vi.mock("next/navigation", () => ({ useParams: () => ({ org: "7" }), useRouter: () => ({ push: vi.fn() }) }));
vi.mock("next/link", () => ({ default: ({ children, href, ...r }: { children: React.ReactNode; href: string }) => <a href={href} {...r}>{children}</a> }));
vi.mock("@/lib/auth", () => ({ useAuth: () => ({ user: { id: "u" }, loading: false }) }));
vi.mock("@/components/mark/studio/nom-espace", () => ({ useNomEspace: () => "Nuances de Feu" }));
vi.mock("@/client/sdk.gen", () => ({
    getWorkflowsSummaryApiV1WorkflowSummaryGet: m.agents,
    getBaseClientApiV1OrganizationsBaseClientGet: m.base,
    getApresAppelApiV1OrganizationsApresAppelGet: m.apres,
    getConnexionsApiV1ConnecteursConnexionsGet: m.connexions,
    listTelephonyConfigurationsApiV1OrganizationsTelephonyConfigsGet: m.telephonie,
    listerLesClesApiV1ClesGet: m.cles,
    lireLaFileDeTriApiV1TriGet: m.tri,
    chiffresDUnClientApiV1RelationClientsOrganizationIdChiffresGet: m.chiffres,
}));

beforeEach(() => {
    m.agents.mockResolvedValue({ data: [{ id: 3, name: "Accueil" }, { id: 4, name: "Devis" }] });
    m.base.mockResolvedValue({ data: { nom_base: "client_nuances", joignable: true } });
    m.apres.mockResolvedValue({ data: { base_rattachee: true } });
    m.connexions.mockResolvedValue({ data: { nango_configure: true, connexions: [{}, {}] } });
    m.telephonie.mockResolvedValue({ data: { configurations: [] } });
    m.cles.mockResolvedValue({ data: [{}, {}, {}, {}] });
    m.tri.mockResolvedValue({ data: { lignes: [{}, {}] } });
    m.chiffres.mockResolvedValue({ data: { appels_7j: 12, note_juge: 4.3, agents_publies: 1 } });
});
afterEach(() => {
    cleanup();
    Object.values(m).forEach((f) => f.mockReset());
});

const ligne = (id: string) => document.querySelector(`[data-branchement="${id}"]`) as HTMLElement;

describe("l'accueil d'un client", () => {
    it("montre ses agents (liens vers l'agent), ses branchements lus sur les vraies routes, et ce qui attend", async () => {
        render(<AccueilClient />);
        expect(await screen.findByText("Accueil")).toBeTruthy();
        expect(screen.getByText("Accueil").closest("a")?.getAttribute("href")).toBe("/agents/3");
        await waitFor(() => expect(ligne("cles")).toBeTruthy());
        expect(within(ligne("base")).getByText(/client_nuances · attached|client_nuances · rattachée/)).toBeTruthy();
        expect(within(ligne("integrations")).getByText("2 connection(s)")).toBeTruthy();
        expect(within(ligne("telephonie")).getByText("none")).toBeTruthy();
        expect(within(ligne("cles")).getByText("4 key(s)")).toBeTruthy();
        expect(within(ligne("cles")).getByText("Keys").closest("a")?.getAttribute("href")).toBe("/clients/7/modeles");
        expect(screen.getByText("2 point(s) waiting")).toBeTruthy();
        expect(screen.getByText("Nuances de Feu")).toBeTruthy();
    });

    it("« Ouvrir son portail » est grisé avec sa raison", async () => {
        render(<AccueilClient />);
        const bouton = (await screen.findByRole("button", { name: /Open its portal/ })) as HTMLButtonElement;
        expect(bouton.disabled).toBe(true);
        expect(bouton.getAttribute("title")).toBe("The portal does not exist yet.");
    });

    it("une lecture qui échoue se dit « illisible », sans inventer d'état", async () => {
        m.base.mockResolvedValue({ error: { detail: "boom" } });
        m.cles.mockResolvedValue({ error: { detail: "boom" } });
        render(<AccueilClient />);
        await waitFor(() => expect(ligne("base")).toBeTruthy());
        expect(within(ligne("base")).getByText("unreadable")).toBeTruthy();
        expect(within(ligne("cles")).getByText("unreadable")).toBeTruthy();
        expect(within(ligne("integrations")).getByText("2 connection(s)")).toBeTruthy();
        expect(screen.queryByText(/boom/)).toBeNull();
    });

    it("un client neuf : aucun agent (état vide), rien à améliorer (état « fait »)", async () => {
        m.agents.mockResolvedValue({ data: [] });
        m.tri.mockResolvedValue({ data: { lignes: [] } });
        m.base.mockResolvedValue({ data: { nom_base: null } });
        render(<AccueilClient />);
        expect(await screen.findByText("No agent")).toBeTruthy();
        expect(await screen.findByText("Nothing to improve")).toBeTruthy();
        await waitFor(() => expect(ligne("base")).toBeTruthy());
        expect(within(ligne("base")).getByText("not attached")).toBeTruthy();
    });

    it("O-1 : la bande de chiffres d'un client en service dit ses appels des 7 jours, sa note du juge et ce qui reste à améliorer", async () => {
        m.tri.mockResolvedValue({ data: { lignes: [{ gravite: 3 }, { gravite: 1 }] } });
        render(<AccueilClient />);
        const bande = await screen.findByTestId("bande-du-client");
        expect(m.chiffres).toHaveBeenCalledWith({ path: { organization_id: 7 } });
        await waitFor(() => expect(bande.textContent).toContain("12"));
        expect(bande.textContent).toContain("Calls in 7 days");
        expect(bande.textContent).toContain("4.3");
        expect(bande.textContent).toContain("Judge score");
        expect(bande.textContent).toContain("of which serious : 1");
    });

    it("O-1 : sans appel noté, un tiret (jamais un chiffre inventé) ; un client sans agent publié n'a pas de bande ; une lecture en échec se dit illisible", async () => {
        m.chiffres.mockResolvedValue({ data: { appels_7j: 0, note_juge: null, agents_publies: 1 } });
        render(<AccueilClient />);
        const bande = await screen.findByTestId("bande-du-client");
        await waitFor(() => expect(bande.textContent).toContain("no scored call yet"));
        expect(bande.textContent).toContain("–");
        cleanup();
        m.chiffres.mockResolvedValue({ data: { appels_7j: 0, note_juge: null, agents_publies: 0 } });
        render(<AccueilClient />);
        await screen.findByText("Accueil");
        expect(screen.queryByTestId("bande-du-client")).toBeNull();
        cleanup();
        m.chiffres.mockResolvedValue({ error: { detail: "x" } });
        render(<AccueilClient />);
        expect((await screen.findByTestId("bande-du-client")).textContent).toContain("unreadable");
    });
});
