/**
 * [.mark] U3 sexies (E73 à E75), l'écran Intégrations, rendu :
 *
 *   - Logiciels : le catalogue en cartes (initiales sans fichier de logo), l'état branché ou non ; la fenêtre d'un
 *     logiciel (comptes branchés, nouveau lien, débrancher) ; « Créer un outil » sur une action ;
 *   - Serveurs MCP : « Tester la connexion » découvre les outils, chacun reçoit son réglage (un désactivé est écrit
 *     dans `reglages_outils`) et le transport SSE s'enregistre ;
 *   - Identifiants : « utilisé par », remplacement d'une valeur par un champ d'écriture seule, jamais réaffichée.
 */
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { FournisseurLangue } from "../langue/langue";
import { PageIntegrations } from "./PageIntegrations";

const CATALOGUE = [
    {
        nom: "agenda_essai",
        libelle: "Agenda d'essai",
        integration: "agenda-essai",
        etat: "a_essayer",
        actions: [
            { nom: "trouver", description: "Find slots.", ecrit: false, anticipable_permis: true, parametres: [], reglages_par_defaut: { nombre: 3 } },
            { nom: "poser", description: "Book.", ecrit: true, anticipable_permis: false, parametres: [], reglages_par_defaut: {} },
        ],
    },
    { nom: "crm_essai", libelle: "CRM d'essai", integration: "crm-essai", etat: "a_essayer", actions: [] },
    { nom: "immo_essai", libelle: "Immo d'essai", integration: "immo-essai", etat: "a_activer", editeur: "Éditeur d'essai", actions: [] },
];
const CONNEXIONS = {
    nango_configure: true,
    connexions: [{ integration: "agenda-essai", connecteur: "agenda_essai", connection_id: "compte-1", erreurs: 0, utilise_par: [{ tool_uuid: "t1", nom: "Poser un rendez-vous" }] }],
};
const SERVEUR = {
    id: 9,
    tool_uuid: "u-mcp",
    name: "Mon serveur",
    description: null,
    category: "mcp",
    icon: null,
    icon_color: null,
    status: "active",
    created_at: "2026-11-01T10:00:00Z",
    updated_at: null,
    definition: { schema_version: 1, type: "mcp", config: { transport: "streamable_http", url: "https://mcp.example.test/mcp", timeout_secs: 30, sse_read_timeout_secs: 300, tools_filter: [], reglages_outils: {}, discovered_tools: [] } },
};
const IDENTIFIANT = { uuid: "cred-1", name: "Clé agenda", description: null, credential_type: "api_key", created_at: "2026-11-01T10:00:00Z", updated_at: null };

const m = vi.hoisted(() => ({
    creerOutil: vi.fn(),
    debrancher: vi.fn(),
    lien: vi.fn(),
    tester: vi.fn(),
    maj: vi.fn(),
    remplacer: vi.fn(),
    creerServeur: vi.fn(),
}));
vi.mock("@/client/sdk.gen", async (importOriginal) =>
    (await import("../sdk-factice")).sdkFactice(await importOriginal(), {
        getCatalogueApiV1ConnecteursCatalogueGet: () => Promise.resolve({ data: CATALOGUE }),
        getConnexionsApiV1ConnecteursConnexionsGet: () => Promise.resolve({ data: CONNEXIONS }),
        createToolApiV1ToolsPost: m.creerOutil,
        deleteConnexionApiV1ConnecteursConnexionsIntegrationDelete: m.debrancher,
        postLienApiV1ConnecteursLienPost: m.lien,
        listToolsApiV1ToolsGet: () => Promise.resolve({ data: [SERVEUR] }),
        testerLaConnexionMcpApiV1ToolsMcpTesterPost: m.tester,
        updateToolApiV1ToolsToolUuidPut: m.maj,
        listCredentialsApiV1CredentialsGet: () => Promise.resolve({ data: [IDENTIFIANT] }),
        utilisationDesIdentifiantsApiV1CredentialsUtilisationGet: () => Promise.resolve({ data: { "cred-1": [{ tool_uuid: "t1", nom: "Lire agenda", categorie: "http_api" }] } }),
        remplacerLaValeurApiV1CredentialsCredentialUuidValeurPut: m.remplacer,
    }),
);
vi.mock("next/navigation", () => ({ useRouter: () => ({ push: vi.fn() }) }));
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

describe("[.mark] Intégrations › Logiciels", () => {
    it("montre le catalogue en cartes, branché ou non, et filtre", async () => {
        monter();
        const carte = (await screen.findByText("Agenda d'essai")).closest("button")!;
        expect(carte.textContent).toContain("Branché");
        expect(screen.getByText("CRM d'essai").closest("button")!.textContent).toContain("À essayer");
        expect(screen.getByText("Immo d'essai").closest("button")!.textContent).toContain("À activer");
        fireEvent.change(screen.getByPlaceholderText("Rechercher un logiciel"), { target: { value: "crm" } });
        expect(screen.queryByText("Agenda d'essai")).toBeNull();
        fireEvent.change(screen.getByPlaceholderText("Rechercher un logiciel"), { target: { value: "zzz" } });
        expect(await screen.findByText(/aucun résultat/i)).toBeTruthy();
    });

    it("dit l'état du logiciel : À essayer avec son explication, À activer avec l'éditeur et sans lien de connexion", async () => {
        monter();
        fireEvent.click(await screen.findByText("CRM d'essai"));
        expect(await screen.findByText("État")).toBeTruthy();
        expect(screen.getByText("crm-essai · À essayer")).toBeTruthy();
        fireEvent.keyDown(document.activeElement ?? document.body, { key: "Escape" });
        cleanup();
        monter();
        fireEvent.click(await screen.findByText("Immo d'essai"));
        expect(await screen.findByText("Éditeur d'essai")).toBeTruthy();
        expect(screen.getByText("API sur contrat")).toBeTruthy();
        expect(screen.getByText("immo-essai · À activer")).toBeTruthy();
        expect(screen.queryByRole("button", { name: /lien d'autorisation/i })).toBeNull();
    });

    it("ouvre un logiciel : comptes branchés, nouveau lien, débrancher", async () => {
        m.lien.mockResolvedValue({ data: { lien: "https://nango.example.test/connect/abc" } });
        m.debrancher.mockResolvedValue({ data: { ok: true } });
        monter();
        fireEvent.click(await screen.findByText("Agenda d'essai"));
        expect(await screen.findByText("compte-1")).toBeTruthy();
        fireEvent.click(screen.getByRole("button", { name: /nouveau lien d'autorisation/i }));
        expect(((await screen.findByLabelText("Lien d'autorisation")) as HTMLInputElement).value).toBe("https://nango.example.test/connect/abc");
        expect(m.lien).toHaveBeenCalledWith({ body: { connecteurs: ["agenda_essai"] } }); // l'organisation n'est jamais envoyée d'ici
        fireEvent.click(screen.getByRole("button", { name: "Débrancher" }));
        await waitFor(() => expect(m.debrancher).toHaveBeenCalledWith({ path: { integration: "agenda-essai" } }));
    });

    it("crée un outil sur une action, avec les réglages par défaut de l'action", async () => {
        m.creerOutil.mockResolvedValue({ data: {} });
        monter();
        fireEvent.click(await screen.findByText("Agenda d'essai"));
        fireEvent.click(await screen.findByRole("tab", { name: "Actions" }));
        fireEvent.click(screen.getAllByRole("button", { name: "Créer un outil" })[0]);
        await waitFor(() => expect(m.creerOutil).toHaveBeenCalled());
        const corps = m.creerOutil.mock.calls[0][0].body;
        expect(corps.category).toBe("integration");
        expect(corps.definition.config).toMatchObject({ connecteur: "agenda_essai", action: "trouver", reglages: { nombre: 3 } });
    });
});

describe("[.mark] Intégrations › Serveurs MCP", () => {
    it("teste la connexion, règle chaque outil et enregistre le transport SSE", async () => {
        m.tester.mockResolvedValue({ data: { ok: true, outils: [{ name: "chercher", description: "Cherche" }, { name: "effacer", description: "Efface" }], erreur: null } });
        m.maj.mockResolvedValue({ data: SERVEUR });
        monter("mcp");
        fireEvent.click(await screen.findByText("Mon serveur"));
        await screen.findByRole("dialog");
        fireEvent.click(screen.getByRole("button", { name: "SSE" }));
        fireEvent.click(screen.getByRole("button", { name: /tester la connexion/i }));
        await screen.findByText(/2 outil\(s\) trouvé\(s\)/);
        expect(m.tester.mock.calls[0][0].body).toMatchObject({ url: "https://mcp.example.test/mcp", transport: "sse" });
        fireEvent.click(screen.getByRole("tab", { name: "Outils" }));
        expect(await screen.findByText("chercher")).toBeTruthy();
        const reglage = screen.getAllByRole("combobox")[1]; // « effacer »
        fireEvent.pointerDown(reglage, { button: 0, ctrlKey: false });
        fireEvent.click(reglage);
        fireEvent.click(await screen.findByRole("option", { name: "Désactivé" }));
        fireEvent.click(screen.getByRole("button", { name: "Enregistrer" }));
        await waitFor(() => expect(m.maj).toHaveBeenCalled());
        const config = m.maj.mock.calls[0][0].body.definition.config;
        expect(config.transport).toBe("sse");
        expect(config.reglages_outils).toEqual({ effacer: "desactive" });
        expect(config.discovered_tools).toHaveLength(2);
    });

    it("dit l'erreur quand le serveur ne répond pas", async () => {
        m.tester.mockResolvedValue({ data: { ok: false, outils: [], erreur: "The server did not answer, or exposes no tool." } });
        monter("mcp");
        fireEvent.click(await screen.findByText("Mon serveur"));
        await screen.findByRole("dialog");
        fireEvent.click(screen.getByRole("button", { name: /tester la connexion/i }));
        expect(await screen.findByText(/did not answer/)).toBeTruthy();
    });
});

describe("[.mark] Intégrations › Identifiants", () => {
    it("dit qui utilise l'identifiant et remplace sa valeur sans jamais l'afficher", async () => {
        m.remplacer.mockResolvedValue({ data: { uuid: "cred-1", remplacee: true } });
        monter("identifiants");
        const ligne = (await screen.findByText("Clé agenda")).closest("tr")!;
        expect(ligne.textContent).toContain("Lire agenda"); // « utilisé par »
        expect(ligne.textContent).toContain("Clé d'API");
        fireEvent.click(ligne);
        const champ = (await screen.findByLabelText("Nouvelle valeur")) as HTMLInputElement;
        expect(champ.type).toBe("password");
        expect(champ.value).toBe(""); // la valeur enregistrée n'est jamais relue
        fireEvent.change(champ, { target: { value: "nouvelle-valeur-secrete" } });
        fireEvent.click(screen.getByRole("button", { name: "Remplacer" }));
        await waitFor(() => expect(m.remplacer).toHaveBeenCalledWith({ path: { credential_uuid: "cred-1" }, body: { valeur: "nouvelle-valeur-secrete" } }));
        await waitFor(() => expect((screen.getByLabelText("Nouvelle valeur") as HTMLInputElement).value).toBe(""));
        expect(document.body.textContent).not.toContain("nouvelle-valeur-secrete");
    });

    it("n'offre pas de suppression d'un identifiant encore utilisé", async () => {
        monter("identifiants");
        fireEvent.click((await screen.findByText("Clé agenda")).closest("tr")!);
        await screen.findByLabelText("Nouvelle valeur");
        expect(screen.getByRole("button", { name: "Supprimer" })).toHaveProperty("disabled", true);
    });
});
