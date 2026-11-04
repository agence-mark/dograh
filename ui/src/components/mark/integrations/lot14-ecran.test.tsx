/**
 * [.mark] Partie 3, lot 14 (SE-19, J-1 à J-3) : Intégrations à la maquette, rendu.
 *
 *   - Logiciels : le tableau des comptes (État, Branché par avec la date, Outils, Dernier usage, Vérifié), les dates relatives ;
 *     la description du logiciel sur sa carte et dans « À propos » ; le logo d'un fichier versé, sinon les initiales ;
 *   - Serveurs MCP : colonnes « État » (Joignable / Injoignable / Jamais essayé) et « Rafraîchi » (date du dernier essai) ;
 *     « Tester la connexion » d'un serveur enregistré envoie son identifiant et relit la liste.
 */
import { cleanup, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { FournisseurLangue } from "../langue/langue";
import { PageIntegrations } from "./PageIntegrations";

const CATALOGUE = [
    {
        nom: "agenda_essai",
        libelle: "Agenda d'essai",
        integration: "agenda-essai",
        etat: "a_essayer",
        categorie: "Agenda",
        description: "Créneaux libres de l'agenda.",
        description_en: "Free slots of the calendar.",
        actions: [],
    },
    { nom: "crm_essai", libelle: "CRM d'essai", integration: "crm-essai", etat: "a_essayer", categorie: "CRM", description: "Contacts du CRM.", description_en: "CRM contacts.", actions: [] },
];
const ilYa = (heures: number) => new Date(Date.now() - heures * 3600_000).toISOString();
const CONNEXIONS = {
    nango_configure: true,
    connexions: [
        { integration: "agenda-essai", connecteur: "agenda_essai", connection_id: "c1", compte: "agenda de test", autorise_par: "Evan", creee_le: "2026-10-07T10:00:00Z", erreurs: 0, utilise_par: [{ tool_uuid: "t1", nom: "Poser" }], dernier_usage_le: ilYa(0.1), mis_a_jour_le: ilYa(0.2) },
        { integration: "crm-essai", connecteur: "crm_essai", connection_id: "c2", compte: "crm de test", autorise_par: "Pierre", creee_le: "2026-10-12T10:00:00Z", erreurs: 0, utilise_par: [] },
    ],
};
const serveur = (uuid: string, nom: string, essai?: { joignable: boolean; le: string }) => ({
    id: 1,
    tool_uuid: uuid,
    name: nom,
    description: null,
    category: "mcp",
    icon: null,
    icon_color: null,
    status: "active",
    created_at: "2026-11-01T10:00:00Z",
    updated_at: null,
    definition: {
        schema_version: 1,
        type: "mcp",
        config: { transport: "streamable_http", url: `https://${uuid}.example.test/mcp`, timeout_secs: 30, sse_read_timeout_secs: 300, tools_filter: [], reglages_outils: {}, discovered_tools: [], ...(essai ? { dernier_test_connexion: essai } : {}) },
    },
});

const m = vi.hoisted(() => ({ tester: vi.fn(), liste: vi.fn(async (..._a: unknown[]) => ({ data: [] as unknown[] })) }));
vi.mock("./logos", () => ({ logoDe: (i: string) => (i === "agenda-essai" ? "/logos/agenda.svg" : null) }));
vi.mock("@/client/sdk.gen", async (importOriginal) =>
    (await import("../sdk-factice")).sdkFactice(await importOriginal(), {
        getCatalogueApiV1ConnecteursCatalogueGet: () => Promise.resolve({ data: CATALOGUE }),
        getConnexionsApiV1ConnecteursConnexionsGet: () => Promise.resolve({ data: CONNEXIONS }),
        getPropositionsApiV1ConnecteursPropositionsGet: () => Promise.resolve({ data: [] }),
        listToolsApiV1ToolsGet: (...a: unknown[]) => m.liste(...a),
        testerLaConnexionMcpApiV1ToolsMcpTesterPost: (...a: unknown[]) => m.tester(...a),
    }),
);
vi.mock("next/navigation", () => ({ useRouter: () => ({ push: vi.fn() }), usePathname: () => "/labo/integrations" }));
vi.mock("sonner", () => ({ toast: { success: vi.fn(), error: vi.fn() } }));
vi.mock("@/lib/auth", () => ({ useAuth: () => ({ user: { id: 1 }, loading: false }) }));

Element.prototype.scrollIntoView = vi.fn();
Element.prototype.hasPointerCapture = vi.fn(() => false);

afterEach(() => {
    cleanup();
    vi.clearAllMocks();
    window.history.replaceState(null, "", "/");
});

const monter = (onglet?: string) => {
    window.history.replaceState(null, "", onglet ? `/?onglet=${onglet}` : "/");
    return render(
        <FournisseurLangue>
            <PageIntegrations />
        </FournisseurLangue>,
    );
};

describe("[.mark] lot 14 : Intégrations › Logiciels (J-1, J-2)", () => {
    it("le tableau des comptes a les colonnes de la maquette et montre le dernier usage et la vérification en dates relatives", async () => {
        monter();
        const ligne = (await screen.findByText("agenda de test")).closest("tr")!;
        const tableau = ligne.closest("table")!;
        expect([...tableau.querySelectorAll("th")].map((h) => h.textContent)).toEqual(["Logiciel", "État", "Branché par", "Outils", "Dernier usage", "Vérifié"]);
        const cellules = [...ligne.querySelectorAll("td")].map((c) => c.textContent);
        expect(cellules[2]).toMatch(/^Evan, /); // « Branché par » porte la date
        expect(cellules[3]).toBe("1");
        expect(cellules[4]).toMatch(/aujourd'hui/); // lu chez Nango, jamais inventé
        const sans = screen.getByText("crm de test").closest("tr")!;
        const celluleSans = [...sans.querySelectorAll("td")].map((c) => c.textContent);
        expect(celluleSans[4]).toBe("–");
        expect(celluleSans[5]).toBe("–");
    });

    it("le logo d'un fichier versé remplace les initiales, sinon les initiales restent", async () => {
        monter();
        const avec = (await screen.findByText("agenda de test")).closest("tr")!;
        expect(avec.querySelector('img[src="/logos/agenda.svg"]')).toBeTruthy();
        const sans = screen.getByText("crm de test").closest("tr")!;
        expect(sans.querySelector("img")).toBeNull();
        expect(sans.textContent).toContain("CD");
    });

    it("la description du logiciel est sur sa carte du catalogue et dans « À propos »", async () => {
        monter();
        fireEvent.click(await screen.findByRole("button", { name: /Catalogue/ }));
        const carte = (await screen.findAllByText("CRM d'essai")).map((x) => x.closest("button")).find(Boolean)!;
        expect(carte.textContent).toContain("Contacts du CRM.");
        fireEvent.click(carte);
        fireEvent.click(await screen.findByRole("tab", { name: /À propos/ }));
        expect((await screen.findByTestId("description-du-logiciel")).textContent).toBe("Contacts du CRM.");
    });
});

describe("[.mark] lot 14 : Intégrations › Serveurs MCP (J-3)", () => {
    it("montre l'état et la date du dernier essai de chaque serveur ; jamais essayé quand rien n'est gardé", async () => {
        m.liste.mockResolvedValue({
            data: [serveur("a", "Stock", { joignable: true, le: ilYa(0.1) }), serveur("b", "Archives", { joignable: false, le: "2025-10-29T09:00:00Z" }), serveur("c", "Neuf")],
        });
        monter("mcp");
        const stock = (await screen.findByText("Stock")).closest("tr")!;
        const tableau = stock.closest("table")!;
        expect([...tableau.querySelectorAll("th")].map((h) => h.textContent)).toEqual(["Serveur", "Connexion", "Outils", "État", "Rafraîchi"]);
        expect(stock.textContent).toContain("Joignable");
        expect(stock.textContent).toMatch(/aujourd'hui/);
        expect(screen.getByText("Archives").closest("tr")!.textContent).toContain("Injoignable");
        const neuf = screen.getByText("Neuf").closest("tr")!;
        expect(neuf.textContent).toContain("Jamais essayé");
        expect([...neuf.querySelectorAll("td")].at(-1)!.textContent).toBe("–");
    });

    it("« Tester la connexion » d'un serveur enregistré envoie son identifiant et relit la liste (état gardé par le serveur)", async () => {
        m.liste.mockResolvedValue({ data: [serveur("a", "Stock")] });
        m.tester.mockResolvedValue({ data: { ok: true, outils: [{ name: "chercher", description: "" }] } });
        monter("mcp");
        fireEvent.click((await screen.findByText("Stock")).closest("tr")!);
        const fenetre = await screen.findByRole("dialog");
        const lectures = m.liste.mock.calls.length;
        fireEvent.click(within(fenetre).getByRole("button", { name: /Tester la connexion/ }));
        await waitFor(() => expect(m.tester).toHaveBeenCalled());
        expect(m.tester.mock.calls[0][0].body.outil_uuid).toBe("a");
        await waitFor(() => expect(m.liste.mock.calls.length).toBeGreaterThan(lectures));
    });

    it("un serveur pas encore enregistré se teste sans identifiant (rien à garder)", async () => {
        m.liste.mockResolvedValue({ data: [] });
        m.tester.mockResolvedValue({ data: { ok: true, outils: [] } });
        monter("mcp");
        fireEvent.click(await screen.findByRole("button", { name: /Ajouter un serveur MCP/ }));
        const fenetre = await screen.findByRole("dialog");
        fireEvent.change(within(fenetre).getByLabelText("Adresse du serveur"), { target: { value: "https://x.example.test/mcp" } });
        fireEvent.click(within(fenetre).getByRole("button", { name: /Tester la connexion/ }));
        await waitFor(() => expect(m.tester).toHaveBeenCalled());
        expect(m.tester.mock.calls[0][0].body.outil_uuid).toBeNull();
    });
});
