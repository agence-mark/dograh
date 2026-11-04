/**
 * [.mark] U3 sexies (E73 à E75), l'écran Intégrations, rendu :
 *
 *   - Logiciels : le catalogue en cartes (initiales sans fichier de logo), l'état branché ou non ; la fenêtre d'un
 *     logiciel (comptes branchés, nouveau lien, débrancher) ; « Créer un outil » sur une action ;
 *   - Serveurs MCP : « Tester la connexion » découvre les outils, chacun reçoit son réglage (un désactivé est écrit
 *     dans `reglages_outils`) et le transport SSE s'enregistre ;
 *   - Identifiants : « utilisé par », remplacement d'une valeur par un champ d'écriture seule, jamais réaffichée.
 */
import { cleanup, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { ChampsCreationIntegration } from "../connecteurs/ConfigOutilIntegration";
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
    propositions: vi.fn(),
    proposer: vi.fn(),
    relancer: vi.fn(),
    lienProposition: vi.fn(),
    retirer: vi.fn(),
}));
const chemin = vi.hoisted(() => ({ valeur: "/labo/integrations" }));
const etat = vi.hoisted(() => ({ connexions: [] as unknown[], nango: true }));
vi.mock("@/client/sdk.gen", async (importOriginal) =>
    (await import("../sdk-factice")).sdkFactice(await importOriginal(), {
        getCatalogueApiV1ConnecteursCatalogueGet: () => Promise.resolve({ data: CATALOGUE }),
        getConnexionsApiV1ConnecteursConnexionsGet: () => Promise.resolve({ data: { ...CONNEXIONS, nango_configure: etat.nango, ...(etat.connexions.length ? { connexions: etat.connexions } : {}) } }),
        getPropositionsApiV1ConnecteursPropositionsGet: (...a: unknown[]) => m.propositions(...a),
        postPropositionApiV1ConnecteursPropositionsPost: (...a: unknown[]) => m.proposer(...a),
        postRelanceApiV1ConnecteursPropositionsIdentifiantRelancerPost: (...a: unknown[]) => m.relancer(...a),
        postLienPropositionApiV1ConnecteursPropositionsIdentifiantLienPost: (...a: unknown[]) => m.lienProposition(...a),
        deletePropositionApiV1ConnecteursPropositionsIdentifiantDelete: (...a: unknown[]) => m.retirer(...a),
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
vi.mock("next/navigation", () => ({ useRouter: () => ({ push: vi.fn() }), usePathname: () => chemin.valeur }));
vi.mock("sonner", () => ({ toast: { success: vi.fn(), error: vi.fn() } }));
vi.mock("@/lib/auth", () => ({ useAuth: () => ({ user: { id: 1 }, loading: false }) }));

Element.prototype.scrollIntoView = vi.fn();
Element.prototype.hasPointerCapture = vi.fn(() => false);

afterEach(() => {
    cleanup();
    vi.clearAllMocks();
    chemin.valeur = "/labo/integrations";
    etat.connexions = [];
    etat.nango = true;
    m.propositions.mockResolvedValue({ data: [] });
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

const ouvrirLeCatalogue = async () => {
    monter();
    fireEvent.click(await screen.findByRole("button", { name: /Catalogue/ }));
    return screen.findByLabelText("Rechercher un logiciel");
};

describe("[.mark] Intégrations : l'action de l'onglet actif est dans la rangée du titre (K7)", () => {
    const titre = () => screen.getByRole("heading", { name: /Intégrations|Integrations/ }).closest("div")!.parentElement as HTMLElement;

    it("Logiciels : « Catalogue » ; Serveurs MCP : « Ajouter un serveur MCP » ; Identifiants : « Nouvel identifiant » ; jamais deux à la fois", async () => {
        monter();
        await screen.findByText("compte-1");
        expect(within(titre()).getByRole("button", { name: /Catalogue/ })).toBeTruthy();
        fireEvent.click(screen.getByRole("tab", { name: /Serveurs MCP|MCP servers/ }));
        await waitFor(() => expect(within(titre()).getByRole("button", { name: /Ajouter un serveur MCP|Add an MCP server/ })).toBeTruthy());
        expect(within(titre()).queryByRole("button", { name: /Catalogue/ })).toBeNull();
        fireEvent.click(screen.getByRole("tab", { name: /Identifiants|Credentials/ }));
        await waitFor(() => expect(within(titre()).getByRole("button", { name: /Nouvel identifiant|New credential/ })).toBeTruthy());
        expect(within(titre()).queryByRole("button", { name: /Ajouter un serveur MCP|Add an MCP server/ })).toBeNull();
    });

    it("le bouton de la rangée du titre ouvre bien la fenêtre de son onglet", async () => {
        monter("mcp");
        fireEvent.click(await within(titre()).findByRole("button", { name: /Ajouter un serveur MCP|Add an MCP server/ }));
        expect(await screen.findByText(/Nouveau serveur MCP|New MCP server/)).toBeTruthy();
    });

    it("V2b : la fenêtre d'un nouveau serveur ajoute le serveur, teste dans son pied, sans note dans le corps", async () => {
        monter("mcp");
        fireEvent.click(await within(titre()).findByRole("button", { name: /Ajouter un serveur MCP|Add an MCP server/ }));
        const fenetre = await screen.findByRole("dialog");
        expect(within(fenetre).getByRole("tab", { name: /Configurer|Configure/ })).toBeTruthy();
        expect(within(fenetre).getByRole("button", { name: /Ajouter le serveur|Add the server/ })).toBeTruthy();
        expect(within(fenetre).getByRole("button", { name: /Tester la connexion|Test the connection/ })).toBeTruthy();
        expect(fenetre.textContent).not.toMatch(/No credentials found|Aucun identifiant\./);
    });
});

describe("[.mark] V2b : un logiciel sans Nango", () => {
    it("grise « Brancher un compte de test » sans écrire la raison dans le corps de la fenêtre", async () => {
        etat.nango = false;
        await ouvrirLeCatalogue();
        fireEvent.click(await screen.findByText("CRM d'essai"));
        const bouton = await screen.findByRole("button", { name: /Brancher un compte de test|Connect a test account/ });
        expect((bouton as HTMLButtonElement).disabled).toBe(true);
        expect(document.body.textContent).not.toMatch(/Pas de Nango|No Nango/);
    });
});

describe("[.mark] Intégrations › Logiciels", () => {
    it("montre le tableau des comptes branchés (au Labo : nos comptes de test), et le catalogue derrière « Catalogue »", async () => {
        monter();
        const ligne = (await screen.findByText("compte-1")).closest("tr")!;
        expect(ligne.textContent).toContain("Agenda d'essai");
        expect(ligne.textContent).toContain("Connecté");
        expect(screen.getByText("Nos comptes de test")).toBeTruthy();
        expect(screen.queryByText("CRM d'essai")).toBeNull(); // le catalogue n'est pas sur la page
    });

    it("le catalogue montre les cartes, branché ou non, et filtre", async () => {
        const recherche = await ouvrirLeCatalogue();
        const carte = (await screen.findAllByText("Agenda d'essai")).map((x) => x.closest("button")).find(Boolean)!;
        expect(carte.textContent).toContain("Branché");
        expect(screen.getByText("CRM d'essai").closest("button")!.textContent).toContain("À essayer");
        expect(screen.getByText("Immo d'essai").closest("button")!.textContent).toContain("À activer");
        fireEvent.change(recherche, { target: { value: "crm" } });
        expect(screen.queryByText("Immo d'essai")).toBeNull();
        fireEvent.change(recherche, { target: { value: "zzz" } });
        expect(await screen.findByText(/aucun résultat/i)).toBeTruthy();
    });

    it("dit l'état du logiciel : À essayer avec son explication, À activer avec l'éditeur et sans lien de connexion", async () => {
        await ouvrirLeCatalogue();
        fireEvent.click(await screen.findByText("CRM d'essai"));
        expect((await screen.findAllByText("État")).length).toBeGreaterThan(0);
        expect(screen.getByText("crm-essai · À essayer")).toBeTruthy();
        cleanup();
        await ouvrirLeCatalogue();
        fireEvent.click(await screen.findByText("Immo d'essai"));
        expect(await screen.findByText("Éditeur d'essai")).toBeTruthy();
        expect(screen.getByText("API sur contrat")).toBeTruthy();
        expect(screen.getByText("immo-essai · À activer")).toBeTruthy();
        expect(screen.queryByRole("button", { name: /brancher/i })).toBeNull();
    });

    it("ouvre un logiciel depuis son compte : tester, et débrancher après confirmation", async () => {
        m.debrancher.mockResolvedValue({ data: { ok: true } });
        monter();
        fireEvent.click((await screen.findByText("compte-1")).closest("tr")!);
        const dialogue = await screen.findByRole("dialog");
        expect(dialogue.textContent).toContain("Branché par");
        fireEvent.click(screen.getByRole("button", { name: "Débrancher" }));
        expect(m.debrancher).not.toHaveBeenCalled(); // un geste sur un compte réel demande confirmation
        fireEvent.click(screen.getByRole("button", { name: "Confirmer" }));
        await waitFor(() => expect(m.debrancher).toHaveBeenCalledWith({ path: { integration: "agenda-essai" }, query: undefined }));
    });

    it("au Labo, « Brancher un compte de test » ouvre l'autorisation avec le nom du compte", async () => {
        m.lien.mockResolvedValue({ data: { lien: "https://nango.example.test/connect/abc" } });
        const ouvre = vi.spyOn(window, "open").mockReturnValue(null);
        monter();
        fireEvent.click((await screen.findByText("compte-1")).closest("tr")!);
        fireEvent.click(await screen.findByRole("button", { name: /Brancher un compte de test/ }));
        fireEvent.change(await screen.findByLabelText("Nom du compte"), { target: { value: "agenda 2" } });
        fireEvent.click(screen.getByRole("button", { name: "Autoriser maintenant" }));
        await waitFor(() => expect(m.lien).toHaveBeenCalledWith({ body: { connecteurs: ["agenda_essai"], compte: "agenda 2" } })); // l'organisation n'est jamais envoyée d'ici
        expect(ouvre).toHaveBeenCalledWith("https://nango.example.test/connect/abc", "_blank", "noopener");
    });

    it("crée un outil sur une action, avec les réglages par défaut de l'action", async () => {
        m.creerOutil.mockResolvedValue({ data: {} });
        monter();
        fireEvent.click((await screen.findByText("compte-1")).closest("tr")!);
        fireEvent.click(await screen.findByRole("tab", { name: "Actions" }));
        fireEvent.click(screen.getAllByRole("button", { name: "Créer un outil" })[0]);
        await waitFor(() => expect(m.creerOutil).toHaveBeenCalled());
        const corps = m.creerOutil.mock.calls[0][0].body;
        expect(corps.category).toBe("integration");
        expect(corps.definition.config).toMatchObject({ connecteur: "agenda_essai", action: "trouver", reglages: { nombre: 3 } });
        expect(corps.definition.config.compte).toBeUndefined(); // un seul compte : l'outil suit le seul compte
    });

    it("avec deux comptes du même logiciel, l'outil créé garde le compte choisi", async () => {
        m.creerOutil.mockResolvedValue({ data: {} });
        etat.connexions = [
            { integration: "agenda-essai", connecteur: "agenda_essai", connection_id: "c1", compte: "agenda A", erreurs: 0, utilise_par: [] },
            { integration: "agenda-essai", connecteur: "agenda_essai", connection_id: "c2", compte: "agenda B", erreurs: 0, utilise_par: [] },
        ];
        monter();
        fireEvent.click((await screen.findAllByText("agenda A"))[0].closest("tr")!);
        fireEvent.click(await screen.findByRole("tab", { name: "Actions" }));
        fireEvent.click(screen.getAllByRole("button", { name: "Créer un outil" })[0]);
        await waitFor(() => expect(m.creerOutil).toHaveBeenCalled());
        expect(m.creerOutil.mock.calls[0][0].body.definition.config.compte).toBe("agenda A");
    });
});

describe("[.mark] Intégrations › Logiciels chez un client : les propositions", () => {
    const PROPOSITION = { identifiant: "p1", connecteur: "agenda_essai", compte: "agenda des techniciens", message: "", etat: "a_autoriser", propose_par: "evan@mark.test", propose_le: "2026-11-03T10:00:00Z", relances: 0 };
    const chez = () => {
        chemin.valeur = "/clients/2/integrations";
        m.propositions.mockResolvedValue({ data: [PROPOSITION] });
    };

    it("montre une proposition « À autoriser » comme une ligne du tableau, puis la relance, copie son lien et la retire après confirmation", async () => {
        chez();
        m.relancer.mockResolvedValue({ data: PROPOSITION });
        m.lienProposition.mockResolvedValue({ data: { lien: "https://nango.example.test/connect/p1" } });
        m.retirer.mockResolvedValue({ data: {} });
        monter();
        const ligne = (await screen.findByText("agenda des techniciens")).closest("tr")!;
        expect(ligne.textContent).toContain("À autoriser");
        expect(ligne.textContent).toContain("proposé par evan@mark.test");
        expect(screen.getByText("Comptes du client")).toBeTruthy();
        fireEvent.click(ligne);
        fireEvent.click(await screen.findByRole("button", { name: "Relancer" }));
        await waitFor(() => expect(m.relancer).toHaveBeenCalledWith({ path: { identifiant: "p1" } }));
        fireEvent.click(screen.getByRole("button", { name: "Copier le lien" }));
        await waitFor(() => expect(m.lienProposition).toHaveBeenCalledWith({ path: { identifiant: "p1" } }));
        fireEvent.click(screen.getByRole("button", { name: "Retirer" }));
        expect(m.retirer).not.toHaveBeenCalled();
        fireEvent.click(screen.getByRole("button", { name: "Confirmer" }));
        await waitFor(() => expect(m.retirer).toHaveBeenCalledWith({ path: { identifiant: "p1" } }));
    });

    it("« Proposer au client » envoie le nom du compte et le message ; « Copier un lien à la place » ne crée aucune proposition", async () => {
        chez();
        m.propositions.mockResolvedValue({ data: [] });
        m.proposer.mockResolvedValue({ data: PROPOSITION });
        m.lien.mockResolvedValue({ data: { lien: "https://nango.example.test/connect/z" } });
        monter();
        fireEvent.click(await screen.findByRole("button", { name: /Catalogue/ }));
        fireEvent.click((await screen.findAllByText("Agenda d'essai")).map((x) => x.closest("button")).find(Boolean)!);
        fireEvent.click(await screen.findByRole("button", { name: /Proposer au client/ }));
        fireEvent.change(await screen.findByLabelText("Nom du compte"), { target: { value: "agenda des techniciens" } });
        fireEvent.click(screen.getByRole("button", { name: /Copier un lien à la place/ }));
        await waitFor(() => expect(m.lien).toHaveBeenCalledWith({ body: { connecteurs: ["agenda_essai"], compte: "agenda des techniciens" } }));
        expect(m.proposer).not.toHaveBeenCalled();
        fireEvent.click(screen.getAllByRole("button", { name: "Proposer au client" }).at(-1)!);
        await waitFor(() => expect(m.proposer).toHaveBeenCalled());
        expect(m.proposer.mock.calls[0][0].body).toMatchObject({ connecteur: "agenda_essai", compte: "agenda des techniciens" });
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

describe("[.mark] « Nouvel outil » d'un logiciel : le compte branché", () => {
    const DEUX = [
        { integration: "agenda-essai", connecteur: "agenda_essai", connection_id: "c1", compte: "agenda A", erreurs: 0, utilise_par: [] },
        { integration: "agenda-essai", connecteur: "agenda_essai", connection_id: "c2", compte: "agenda B", erreurs: 0, utilise_par: [] },
    ];

    it("avec deux comptes, l'outil prend le premier d'emblée puis celui qu'on choisit ; avec un seul, rien n'est demandé ni écrit", async () => {
        etat.connexions = DEUX;
        const changements: Array<Record<string, unknown> | null> = [];
        render(
            <FournisseurLangue>
                <ChampsCreationIntegration avecCompte onChange={(v) => changements.push(v as Record<string, unknown> | null)} />
            </FournisseurLangue>,
        );
        const choix = await screen.findByTestId("choix-du-compte");
        await waitFor(() => expect(changements.at(-1)).toMatchObject({ connecteur: "agenda_essai", compte: "agenda A" }));
        fireEvent.pointerDown(within(choix).getByRole("combobox"), { button: 0, ctrlKey: false });
        fireEvent.click(within(choix).getByRole("combobox"));
        fireEvent.click(await screen.findByRole("option", { name: "agenda B" }));
        await waitFor(() => expect(changements.at(-1)).toMatchObject({ compte: "agenda B" }));
        cleanup();
        etat.connexions = [DEUX[0]];
        const seul: Array<Record<string, unknown> | null> = [];
        render(
            <FournisseurLangue>
                <ChampsCreationIntegration avecCompte onChange={(v) => seul.push(v as Record<string, unknown> | null)} />
            </FournisseurLangue>,
        );
        await waitFor(() => expect(seul.length).toBeGreaterThan(0));
        expect(screen.queryByTestId("choix-du-compte")).toBeNull();
        expect(seul.every((v) => !v || v.compte === undefined)).toBe(true);
    });
});
