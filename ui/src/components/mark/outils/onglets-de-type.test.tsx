/**
 * [.mark] N2 : les réglages propres à chaque type d'outil vivent dans la fenêtre de l'outil (l'ancienne page d'un outil est retirée).
 * Portés depuis les tests de l'ancienne page (transfert d'appel, transfert vers un agent) et complétés : fin d'appel, corps et valeurs
 * fixes d'une requête, serveur MCP. Chaque enregistrement envoie la définition complète, rien d'autre n'est perdu.
 */
import { cleanup, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { FournisseurLangue } from "../langue/langue";
import { PageOutils } from "./PageOutils";
import { validerConfig } from "./OngletsDeType";

const base = { icon: null, icon_color: null, status: "active", created_at: "2026-11-01T10:00:00Z", updated_at: null, description: "" };
const TRANSFERT = {
    ...base, id: 1, tool_uuid: "u-tc", name: "Passer au comptoir", category: "transfer_call",
    definition: {
        schema_version: 1, type: "transfer_call",
        config: { destination_source: "context_mapping", destination: "", messageType: "none", timeout: 30, context_mapping: { rules: [{ context_path: "department", routes: [{ context_value: "support", destination: "PJSIP/support" }] }] } },
    },
};
const STATIQUE = { ...TRANSFERT, id: 2, tool_uuid: "u-st", name: "Vers l'accueil", definition: { schema_version: 1, type: "transfer_call", config: { destination_source: "static", destination: "+33100000000", messageType: "none", timeout: 30 } } };
const VERS_AGENT = { ...base, id: 3, tool_uuid: "u-ta", name: "Vers la facturation", category: "transfer_agent", definition: { schema_version: 1, type: "transfer_agent", config: { workflow_id: 43, message: "Un instant.", play_greeting: true } } };
const FIN = { ...base, id: 4, tool_uuid: "u-fin", name: "Raccrocher", category: "end_call", definition: { schema_version: 1, type: "end_call", config: { messageType: "none", endCallReason: false } } };
const HTTP = { ...base, id: 5, tool_uuid: "u-http", name: "Reserver", category: "http_api", definition: { schema_version: 1, type: "http_api", config: { method: "POST", url: "https://agenda.example.test/rdv", essais: 1, customMessage: "Je regarde" } } };
const MCP = { ...base, id: 6, tool_uuid: "u-mcp", name: "Serveur client", category: "mcp", definition: { schema_version: 1, type: "mcp", config: { url: "https://mcp.example.test", tools_filter: ["a"] } } };

const m = vi.hoisted(() => ({ liste: vi.fn(), maj: vi.fn() }));
vi.mock("@/client/sdk.gen", async (importOriginal) =>
    (await import("../sdk-factice")).sdkFactice(await importOriginal(), {
        listToolsApiV1ToolsGet: m.liste,
        statistiquesDesOutilsApiV1ToolsStatistiquesGet: () => Promise.resolve({ data: {} }),
        updateToolApiV1ToolsToolUuidPut: m.maj,
        getWorkflowsSummaryApiV1WorkflowSummaryGet: () => Promise.resolve({ data: [{ id: 42, name: "Accueil" }, { id: 43, name: "Facturation" }] }),
        listRecordingsApiV1WorkflowRecordingsGet: () => Promise.resolve({ data: { recordings: [] } }),
        getCatalogueApiV1ConnecteursCatalogueGet: () => Promise.resolve({ data: [] }),
        getConnexionsApiV1ConnecteursConnexionsGet: () => Promise.resolve({ data: { nango_configure: false, connexions: [] } }),
        listCredentialsApiV1CredentialsGet: () => Promise.resolve({ data: [] }),
        statistiquesDUnOutilApiV1ToolsToolUuidStatistiquesGet: () =>
            Promise.resolve({ data: { executions: 0, reussies: 0, echecs: 0, reussite: null, duree_mediane_ms: null, jours: 30, page: 0, par_page: 25, total_executions: 0, dernieres_executions: [], agents: [] } }),
    }),
);
vi.mock("sonner", () => ({ toast: { success: vi.fn(), error: vi.fn() } }));
vi.mock("@/lib/auth", () => ({ useAuth: () => ({ user: { id: 1 }, loading: false }) }));
vi.mock("next/navigation", () => ({ useRouter: () => ({ push: vi.fn() }) }));
Element.prototype.scrollIntoView = vi.fn();
Element.prototype.hasPointerCapture = vi.fn(() => false);

afterEach(() => {
    cleanup();
    vi.clearAllMocks();
});

const ouvrir = async (outil: { name: string }, nomOnglet: RegExp) => {
    m.liste.mockResolvedValue({ data: [outil] });
    render(<FournisseurLangue><PageOutils /></FournisseurLangue>);
    fireEvent.click(await screen.findByText(outil.name));
    await screen.findByRole("dialog");
    fireEvent.click(screen.getByRole("tab", { name: nomOnglet }));
};
const enregistrer = async (outil: { tool_uuid: string }) => {
    m.maj.mockResolvedValue({ data: outil });
    fireEvent.click(screen.getByRole("button", { name: "Enregistrer" }));
    await waitFor(() => expect(m.maj).toHaveBeenCalled());
    return m.maj.mock.calls[0][0].body.definition.config;
};
const champ = (nom: string) => (screen.getByLabelText(nom) as HTMLInputElement).value;

describe("[.mark] transfert d'appel dans la fenêtre de l'outil", () => {
    it("offre l'onglet Destination et plus d'éditeur à part", async () => {
        await ouvrir(TRANSFERT, /destination/i);
        expect(screen.queryByText(/éditeur complet/i)).toBeNull();
        expect(screen.getByText(/aiguillage selon le contexte/i)).toBeTruthy();
    });

    it("l'état de l'appel après un transfert réussi est borné et facultatif", async () => {
        await ouvrir(STATIQUE, /destination/i);
        const saisie = screen.getByLabelText("État de l'appel après un transfert réussi") as HTMLInputElement;
        expect(saisie.value).toBe("");
        expect(saisie.maxLength).toBe(64);
    });

    it("garde la ligne qui a le focus quand une ligne plus haut est retirée, ajoute une règle et reclasse", async () => {
        await ouvrir(TRANSFERT, /destination/i);
        fireEvent.click(screen.getAllByRole("button", { name: "Ajouter une ligne" })[0]);
        const ajoutee = screen.getByLabelText("Règle 1 destination 2");
        ajoutee.focus();
        fireEvent.click(screen.getAllByRole("button", { name: "Retirer" })[0]);
        expect(document.activeElement).toBe(screen.getByLabelText("Règle 1 destination 1"));
        fireEvent.click(screen.getByRole("button", { name: /ajouter une règle d'aiguillage/i }));
        expect(champ("Champ du contexte 2")).toBe("");
        fireEvent.change(screen.getByLabelText("Champ du contexte 2"), { target: { value: "state" } });
        expect(screen.getByLabelText("Monter la règle 1")).toHaveProperty("disabled", true);
        fireEvent.click(screen.getByLabelText("Monter la règle 2"));
        expect(champ("Champ du contexte 1")).toBe("state");
        expect(champ("Champ du contexte 2")).toBe("department");
    });

    it("enregistre la définition complète : destination, délai, état après transfert", async () => {
        await ouvrir(STATIQUE, /destination/i);
        fireEvent.change(screen.getByLabelText("Destination du transfert"), { target: { value: "+33199999999" } });
        fireEvent.change(screen.getByLabelText("Durée de sonnerie"), { target: { value: "45" } });
        fireEvent.change(screen.getByLabelText("État de l'appel après un transfert réussi"), { target: { value: "transfere" } });
        const config = await enregistrer(STATIQUE);
        expect(config).toMatchObject({ destination_source: "static", destination: "+33199999999", timeout: 45, call_disposition: "transfere", messageType: "none" });
    });

    it("refuse un transfert sans destination, avec la phrase de l'écran", async () => {
        await ouvrir(STATIQUE, /destination/i);
        fireEvent.change(screen.getByLabelText("Destination du transfert"), { target: { value: "" } });
        fireEvent.click(screen.getByRole("button", { name: "Enregistrer" }));
        expect(await screen.findByText("Saisissez une destination de transfert.")).toBeTruthy();
        expect(m.maj).not.toHaveBeenCalled();
    });

    it("passer au résolveur écrit la requête (adresse, délai, en-tête, valeur fixe) et retire la destination fixe", async () => {
        await ouvrir(STATIQUE, /destination/i);
        fireEvent.click(screen.getByRole("button", { name: "Cherché par une requête" }));
        fireEvent.change(screen.getByLabelText("Adresse du résolveur"), { target: { value: "https://annuaire.example.test/qui" } });
        fireEvent.click(screen.getByRole("button", { name: "Ajouter un en-tête" }));
        fireEvent.change(screen.getByLabelText("Nom de l'en-tête"), { target: { value: "X-Site" } });
        fireEvent.change(screen.getByLabelText("Valeur de l'en-tête"), { target: { value: "1" } });
        fireEvent.click(screen.getByRole("button", { name: "Ajouter une valeur fixe" }));
        fireEvent.change(screen.getByLabelText("Nom de la valeur fixe"), { target: { value: "client" } });
        fireEvent.change(screen.getByLabelText("Valeur fixe"), { target: { value: "{{initial_context.client}}" } });
        const config = await enregistrer(STATIQUE);
        expect(config.destination_source).toBe("dynamic");
        expect(config.destination).toBe("");
        expect(config.resolver).toMatchObject({ type: "http", url: "https://annuaire.example.test/qui", headers: { "X-Site": "1" }, preset_parameters: [{ name: "client", value_template: "{{initial_context.client}}" }] });
    });
});

describe("[.mark] transfert vers un agent dans la fenêtre de l'outil", () => {
    it("montre l'agent déjà réglé, propose ceux de l'organisation et enregistre le message et l'accueil", async () => {
        await ouvrir(VERS_AGENT, /destination/i);
        await waitFor(() => expect(screen.getByLabelText("Transférer à l'agent")).toBeTruthy());
        expect(await screen.findByText("Facturation")).toBeTruthy();
        fireEvent.change(screen.getByLabelText("Message de passage"), { target: { value: "Un instant, svp." } });
        fireEvent.click(screen.getByLabelText("Dire l'accueil de l'agent reçu"));
        const config = await enregistrer(VERS_AGENT);
        expect(config).toMatchObject({ workflow_id: 43, message: "Un instant, svp.", play_greeting: false });
    });

    it("refuse sans agent choisi", async () => {
        const sans = { ...VERS_AGENT, definition: { ...VERS_AGENT.definition, config: { message: "x" } } };
        await ouvrir(sans, /destination/i);
        fireEvent.click(screen.getByRole("button", { name: "Enregistrer" }));
        // rien n'a changé : le bouton dort tant que rien n'est modifié
        fireEvent.change(screen.getByLabelText("Message de passage"), { target: { value: "y" } });
        fireEvent.click(screen.getByRole("button", { name: "Enregistrer" }));
        expect(await screen.findByText("Choisissez l'agent vers lequel transférer.")).toBeTruthy();
    });
});

describe("[.mark] fin d'appel dans la fenêtre de l'outil", () => {
    it("une phrase écrite et la raison de fin demandée au modèle (avec sa description par défaut)", async () => {
        await ouvrir(FIN, /fin d'appel/i);
        fireEvent.click(screen.getByRole("button", { name: "Une phrase" }));
        fireEvent.change(screen.getByLabelText("Phrase dite"), { target: { value: "Bonne journée !" } });
        fireEvent.click(screen.getByLabelText("Demander une raison au modèle"));
        const config = await enregistrer(FIN);
        expect(config).toMatchObject({ messageType: "custom", customMessage: "Bonne journée !", endCallReason: true });
        expect(String(config.endCallReasonDescription)).toContain("reason for ending the call");
    });

    it("« Rien » efface la phrase écrite", async () => {
        const avec = { ...FIN, definition: { ...FIN.definition, config: { messageType: "custom", customMessage: "Au revoir", endCallReason: false } } };
        await ouvrir(avec, /fin d'appel/i);
        fireEvent.click(screen.getByRole("button", { name: "Rien" }));
        const config = await enregistrer(avec);
        expect(config.messageType).toBe("none");
        expect(config.customMessage).toBeUndefined();
    });
});

describe("[.mark] requête HTTP : corps et valeurs fixes dans l'onglet Paramètres", () => {
    it("règle le format du corps, un modèle JSON et une valeur fixe, sans perdre le reste", async () => {
        await ouvrir(HTTP, /paramètres/i);
        fireEvent.click(screen.getByRole("button", { name: "form" }));
        fireEvent.click(screen.getByLabelText("Utiliser un modèle de corps"));
        fireEvent.change(screen.getByLabelText("Modèle du corps"), { target: { value: '{"nom": "{{nom}}"}' } });
        fireEvent.click(screen.getByRole("button", { name: "Ajouter une valeur fixe" }));
        fireEvent.change(screen.getByLabelText("Nom de la valeur fixe"), { target: { value: "site" } });
        fireEvent.change(screen.getByLabelText("Valeur fixe"), { target: { value: "{{initial_context.site}}" } });
        const config = await enregistrer(HTTP);
        expect(config).toMatchObject({ url: "https://agenda.example.test/rdv", essais: 1, customMessage: "Je regarde", body_format: "form", body_template: { nom: "{{nom}}" } });
        expect(config.preset_parameters).toEqual([{ name: "site", type: "string", value_template: "{{initial_context.site}}", required: true }]);
    });

    it("un GET n'a pas de corps : seules les valeurs fixes sont proposées", async () => {
        const get = { ...HTTP, definition: { ...HTTP.definition, config: { method: "GET", url: "https://x.example.test" } } };
        await ouvrir(get, /paramètres/i);
        expect(screen.queryByLabelText("Utiliser un modèle de corps")).toBeNull();
        expect(screen.getByRole("button", { name: "Ajouter une valeur fixe" })).toBeTruthy();
    });
});

describe("[.mark] serveur MCP dans la fenêtre de l'outil", () => {
    it("règle l'adresse et les outils gardés ; refuse une adresse sans http", async () => {
        await ouvrir(MCP, /serveur/i);
        fireEvent.change(screen.getByLabelText("Adresse du serveur MCP"), { target: { value: "ftp://x" } });
        fireEvent.click(screen.getByRole("button", { name: "Enregistrer" }));
        expect(await screen.findByText(/doit commencer par http/)).toBeTruthy();
        fireEvent.change(screen.getByLabelText("Adresse du serveur MCP"), { target: { value: "https://mcp2.example.test" } });
        fireEvent.change(screen.getByLabelText("Outils gardés"), { target: { value: "a, b" } });
        fireEvent.blur(screen.getByLabelText("Outils gardés"));
        const config = await enregistrer(MCP);
        expect(config).toMatchObject({ url: "https://mcp2.example.test", tools_filter: ["a", "b"] });
    });
});

describe("validerConfig", () => {
    const t = (x: { en: string; fr: string }) => x.fr;
    it("laisse passer une configuration en ordre et refuse un résolveur sans adresse ou une règle incomplète", () => {
        expect(validerConfig("end_call", {}, t)).toBeNull();
        expect(validerConfig("transfer_call", { destination_source: "dynamic", resolver: { url: "" } }, t)).toMatch(/résolveur/);
        expect(validerConfig("transfer_call", { destination_source: "context_mapping", context_mapping: { rules: [{ context_path: "", routes: [] }] } }, t)).toMatch(/règle 1/);
        expect(within(document.body).queryByText("x")).toBeNull();
    });
});

describe("[.mark] anciens en-têtes et sources des champs requis", () => {
    it("les anciens en-têtes simples d'une requête restent modifiables dans l'onglet Requête", async () => {
        const ancien = { ...HTTP, definition: { ...HTTP.definition, config: { ...HTTP.definition.config, headers: { "X-Ancien": "1" } } } };
        await ouvrir(ancien, /requête/i);
        fireEvent.change(screen.getByLabelText("Valeur de l'en-tête simple"), { target: { value: "2" } });
        const config = await enregistrer(ancien);
        expect(config.headers).toEqual({ "X-Ancien": "2" });
    });
});
