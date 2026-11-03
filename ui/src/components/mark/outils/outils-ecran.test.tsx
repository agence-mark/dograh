/**
 * [.mark] U3 sexies (E73, E74), l'écran des Outils, rendu :
 *
 *   - le tableau : type, branché sur, accès, exécutions et réussite lus du serveur ; onglets Actifs / Brouillons /
 *     Archivés ; filtre par type ; état vide ;
 *   - la fenêtre d'un outil HTTP : ses sept onglets ; l'enregistrement envoie la définition COMPLÈTE (rien du reste
 *     de la configuration n'est perdu) avec le comportement, l'emplacement d'un paramètre, la réponse et les
 *     réponses simulées ;
 *   - un en-tête secret : la valeur saisie est rangée dans un identifiant, la définition n'en garde que la référence
 *     et rien ne la réaffiche ;
 *   - l'essai : un outil qui écrit n'est jamais essayé en direct, il l'est en réponse simulée ; le premier essai se
 *     valide après un essai réussi seulement.
 */
import { cleanup, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { FournisseurLangue } from "../langue/langue";
import { PageOutils } from "./PageOutils";

const HTTP = {
    id: 1,
    tool_uuid: "u-http",
    name: "Reserver",
    description: "Réserve un rendez-vous.",
    category: "http_api",
    icon: null,
    icon_color: null,
    status: "active",
    created_at: "2026-11-01T10:00:00Z",
    updated_at: null,
    definition: {
        schema_version: 1,
        type: "http_api",
        config: { method: "POST", url: "https://agenda.example.test/rdv/{{id}}", timeout_ms: 5000, body_format: "json", essais: 1, customMessage: "Je regarde", parameters: [{ name: "id", type: "string", description: "Rendez-vous", required: true }] },
    },
};
const LECTURE = { ...HTTP, id: 2, tool_uuid: "u-get", name: "Chercher", description: "Cherche.", definition: { schema_version: 1, type: "http_api", config: { method: "GET", url: "https://agenda.example.test/rdv" } } };
const BROUILLON = { ...HTTP, id: 3, tool_uuid: "u-draft", name: "Brouillon", status: "draft", category: "calculator", definition: { schema_version: 1, type: "calculator" } };

const m = vi.hoisted(() => ({
    liste: vi.fn(),
    maj: vi.fn(),
    essai: vi.fn(),
    valider: vi.fn(),
    creerIdentifiant: vi.fn(),
    lire: vi.fn(),
}));
vi.mock("@/client/sdk.gen", async (importOriginal) =>
    (await import("../sdk-factice")).sdkFactice(await importOriginal(), {
        listToolsApiV1ToolsGet: m.liste,
        statistiquesDesOutilsApiV1ToolsStatistiquesGet: () =>
            Promise.resolve({
                data: {
                    "u-http": { executions: 12, reussies: 9, echecs: 3, reussite: 75, duree_mediane_ms: 420, nb_agents: 2, jours: 30 },
                    "u-get": { executions: 0, reussies: 0, echecs: 0, reussite: null, duree_mediane_ms: null, nb_agents: 0, jours: 30 },
                },
            }),
        updateToolApiV1ToolsToolUuidPut: m.maj,
        essayerUnOutilApiV1ToolsToolUuidEssaiPost: m.essai,
        validerLePremierEssaiApiV1ToolsToolUuidPremierEssaiPost: m.valider,
        createCredentialApiV1CredentialsPost: m.creerIdentifiant,
        getToolApiV1ToolsToolUuidGet: m.lire,
        getCatalogueApiV1ConnecteursCatalogueGet: () => Promise.resolve({ data: [] }),
        getConnexionsApiV1ConnecteursConnexionsGet: () => Promise.resolve({ data: { nango_configure: false, connexions: [] } }),
        statistiquesDUnOutilApiV1ToolsToolUuidStatistiquesGet: () =>
            Promise.resolve({ data: { executions: 0, reussies: 0, echecs: 0, reussite: null, duree_mediane_ms: null, jours: 30, page: 0, par_page: 25, total_executions: 0, dernieres_executions: [], agents: [] } }),
        listCredentialsApiV1CredentialsGet: () => Promise.resolve({ data: [] }),
    }),
);
vi.mock("sonner", () => ({ toast: { success: vi.fn(), error: vi.fn() } }));
vi.mock("@/lib/auth", () => ({ useAuth: () => ({ user: { id: 1 }, loading: false }) }));
vi.mock("next/navigation", () => ({ useRouter: () => ({ push: vi.fn() }) }));

// jsdom ne connaît pas ces gestes du `Select` (Radix).
Element.prototype.scrollIntoView = vi.fn();
Element.prototype.hasPointerCapture = vi.fn(() => false);

afterEach(() => {
    cleanup();
    vi.clearAllMocks();
});

const monter = () =>
    render(
        <FournisseurLangue>
            <PageOutils />
        </FournisseurLangue>,
    );

const ouvrirReserver = async () => {
    m.liste.mockResolvedValue({ data: [HTTP, LECTURE, BROUILLON] });
    monter();
    fireEvent.click(await screen.findByText("Reserver"));
    return screen.findByRole("dialog");
};
const onglet = (nom: RegExp) => fireEvent.click(screen.getByRole("tab", { name: nom }));

describe("[.mark] le tableau des outils", () => {
    it("lit les chiffres du serveur et classe par état", async () => {
        m.liste.mockResolvedValue({ data: [HTTP, LECTURE, BROUILLON] });
        monter();
        const ligne = (await screen.findByText("Reserver")).closest("tr")!;
        expect(within(ligne).getByText("Requête HTTP")).toBeTruthy();
        expect(within(ligne).getByText("Écrit")).toBeTruthy();
        expect(within(ligne).getByText("12")).toBeTruthy();
        expect(within(ligne).getByText("75 %")).toBeTruthy();
        const get = screen.getByText("Chercher").closest("tr")!;
        expect(within(get).getByText("Lit")).toBeTruthy(); // un GET lit
        expect(within(get).getAllByText("–").length).toBeGreaterThan(0); // aucun appel : pas de chiffre inventé
        expect(screen.queryByText("Brouillon")).toBeNull();
        fireEvent.click(screen.getByRole("tab", { name: /brouillons/i }));
        expect(await screen.findByText("Brouillon")).toBeTruthy();
        expect(screen.queryByText("Reserver")).toBeNull();
    });

    it("V2 : la date de modification se lit en français, jamais en 2026-11-01", async () => {
        m.liste.mockResolvedValue({ data: [HTTP] });
        monter();
        const ligne = (await screen.findByText("Reserver")).closest("tr")!;
        expect(within(ligne).getByText(/1 nov\.? 2026/)).toBeTruthy();
        expect(within(ligne).queryByText("2026-11-01")).toBeNull();
    });

    it("dit « Aucun outil » quand l'organisation n'en a pas", async () => {
        m.liste.mockResolvedValue({ data: [] });
        monter();
        expect(await screen.findByText("Aucun outil")).toBeTruthy();
    });

    it("J (E102) : une recherche sans résultat dit « Aucun résultat pour », même sans aucun outil, et s'efface", async () => {
        m.liste.mockResolvedValue({ data: [] });
        monter();
        await screen.findByText("Aucun outil");
        fireEvent.change(screen.getByPlaceholderText(/Rechercher/), { target: { value: "zzzz" } });
        expect(await screen.findByText(/Aucun résultat pour/)).toBeTruthy();
        expect(screen.queryByText("Aucun outil")).toBeNull();
        fireEvent.click(screen.getByRole("button", { name: "Effacer les filtres" }));
        expect(await screen.findByText("Aucun outil")).toBeTruthy();
    });
});

describe("[.mark] la fenêtre d'un outil HTTP", () => {
    it("offre les sept onglets du type", async () => {
        const fenetre = await ouvrirReserver();
        for (const nom of ["Général", "Requête", "Paramètres", "Réponse", "Comportement", "Essai", "Activité"]) {
            expect(within(fenetre).getByRole("tab", { name: nom })).toBeTruthy();
        }
    });

    it("enregistre la définition complète avec le comportement, l'emplacement, la réponse et les réponses simulées", async () => {
        m.maj.mockResolvedValue({ data: HTTP });
        await ouvrirReserver();
        // Comportement : la phrase avant en « Auto », le repli.
        onglet(/comportement/i);
        fireEvent.click(screen.getByRole("button", { name: "Auto" }));
        fireEvent.change(screen.getByRole("textbox", { name: /phrase de repli/i }), { target: { value: "Je note votre demande" } });
        // Paramètres : l'emplacement et les valeurs permises.
        onglet(/paramètres/i);
        fireEvent.change(screen.getByRole("textbox", { name: /valeurs permises/i }), { target: { value: "a, b" } });
        // Réponse : chemins gardés.
        onglet(/réponse/i);
        fireEvent.change(screen.getByRole("textbox", { name: /chemins gardés/i }), { target: { value: "rdv.date\nrdv.id" } });
        fireEvent.click(screen.getByRole("button", { name: /ajouter une copie/i }));
        fireEvent.change(screen.getByRole("textbox", { name: "Chemin" }), { target: { value: "rdv.id" } });
        fireEvent.change(screen.getByRole("textbox", { name: "Clé" }), { target: { value: "rdv_id" } });
        fireEvent.click(screen.getByRole("button", { name: /ajouter une réponse/i }));
        fireEvent.click(screen.getByRole("button", { name: "Enregistrer" }));
        await waitFor(() => expect(m.maj).toHaveBeenCalled());
        const corps = m.maj.mock.calls[0][0].body;
        expect(m.maj.mock.calls[0][0].path).toEqual({ tool_uuid: "u-http" });
        const config = corps.definition.config;
        // Rien du reste n'est perdu : l'adresse, les essais, le corps, le message d'avant.
        expect(config).toMatchObject({ method: "POST", url: "https://agenda.example.test/rdv/{{id}}", essais: 1, body_format: "json", customMessage: "Je regarde" });
        // Et les ajouts y sont.
        expect(config.phrase_avant_mode).toBe("auto");
        expect(config.phrase_repli).toBe("Je note votre demande");
        expect(config.parameters[0].valeurs_permises).toEqual(["a", "b"]);
        expect(config.chemins_gardes).toEqual(["rdv.date", "rdv.id"]);
        expect(config.copies_dans_la_fiche).toEqual([{ chemin: "rdv.id", cle: "rdv_id" }]);
        expect(config.reponses_simulees).toHaveLength(1);
    });

    it("propose « en arrière-plan » à un outil qui lit seulement", async () => {
        m.liste.mockResolvedValue({ data: [HTTP, LECTURE] });
        monter();
        fireEvent.click(await screen.findByText("Chercher"));
        await screen.findByRole("dialog");
        onglet(/comportement/i);
        const execution = screen.getAllByRole("combobox").find((c) => /Immédiate/.test(c.textContent ?? ""))!;
        fireEvent.pointerDown(execution, { button: 0, ctrlKey: false });
        fireEvent.click(execution);
        expect(await screen.findByRole("option", { name: "En arrière-plan" })).toBeTruthy();
    });

    it("range un secret dans un identifiant : la définition n'en garde que la référence, rien ne le réaffiche", async () => {
        m.maj.mockResolvedValue({ data: HTTP });
        m.liste.mockResolvedValue({ data: [{ ...HTTP, definition: { ...HTTP.definition, config: { ...HTTP.definition.config, en_tetes_ext: [{ nom: "X-Cle", sorte: "secret" }] } } }] });
        m.creerIdentifiant.mockResolvedValue({ data: { uuid: "cred-1", name: "x", credential_type: "custom_header", description: null, created_at: "2026-11-01T10:00:00Z", updated_at: null } });
        monter();
        fireEvent.click(await screen.findByText("Reserver"));
        await screen.findByRole("dialog");
        onglet(/requête/i);
        const champ = screen.getByLabelText("Valeur du secret") as HTMLInputElement;
        expect(champ.type).toBe("password");
        fireEvent.change(champ, { target: { value: "valeur-ultra-secrete" } });
        fireEvent.blur(champ);
        await waitFor(() => expect(m.creerIdentifiant).toHaveBeenCalled());
        expect(m.creerIdentifiant.mock.calls[0][0].body.credential_data).toEqual({ header_name: "X-Cle", header_value: "valeur-ultra-secrete" });
        await screen.findByText(/rangé \(masqué\)/i);
        expect(document.body.innerHTML).not.toContain("valeur-ultra-secrete");
        fireEvent.click(screen.getByRole("button", { name: "Enregistrer" }));
        await waitFor(() => expect(m.maj).toHaveBeenCalled());
        const entetes = m.maj.mock.calls[0][0].body.definition.config.en_tetes_ext;
        expect(entetes).toEqual([expect.objectContaining({ nom: "X-Cle", sorte: "secret", identifiant_uuid: "cred-1" })]);
        expect(JSON.stringify(m.maj.mock.calls[0][0])).not.toContain("valeur-ultra-secrete");
    });
});

describe("[.mark] l'essai", () => {
    it("n'essaie jamais en direct un outil qui écrit : réponse simulée, puis premier essai validé par une personne", async () => {
        m.essai.mockResolvedValue({ data: { reussi: true, mode: "simule", ecrit: true, duree_ms: 3, message: "The service answered.", donnees: { rdv: { date: "jeudi" } }, statut_http: 200, copies: { rdv_id: 1 }, simulee: true } });
        m.valider.mockResolvedValue({ data: { valide_par: "x", valide_le: "2026-11-03T08:00:00Z", mode: "simule" } });
        m.lire.mockResolvedValue({ data: HTTP });
        await ouvrirReserver();
        onglet(/essai/i);
        expect(screen.getByRole("button", { name: /valider le premier essai/i })).toHaveProperty("disabled", true); // pas d'essai réussi encore
        fireEvent.click(screen.getByRole("button", { name: "Essayer" }));
        await screen.findByText("Essai réussi");
        expect(m.essai.mock.calls[0][0].body.mode).toBe("simule"); // jamais « direct » pour un POST
        expect(screen.getByText(/rdv_id/)).toBeTruthy();
        await waitFor(() => expect(screen.getByRole("button", { name: /valider le premier essai/i })).toHaveProperty("disabled", false));
        fireEvent.click(screen.getByRole("button", { name: /valider le premier essai/i }));
        await waitFor(() => expect(m.valider).toHaveBeenCalledWith({ path: { tool_uuid: "u-http" } }));
    });

    it("essaie directement un outil qui lit", async () => {
        m.liste.mockResolvedValue({ data: [LECTURE] });
        m.essai.mockResolvedValue({ data: { reussi: true, mode: "direct", ecrit: false, duree_ms: 5, message: "The service answered.", donnees: {}, copies: {}, simulee: false } });
        monter();
        fireEvent.click(await screen.findByText("Chercher"));
        await screen.findByRole("dialog");
        onglet(/essai/i);
        fireEvent.click(screen.getByRole("button", { name: "Essayer" }));
        await waitFor(() => expect(m.essai).toHaveBeenCalled());
        expect(m.essai.mock.calls[0][0].body.mode).toBe("direct");
    });
});
