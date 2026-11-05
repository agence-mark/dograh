/**
 * [.mark] Partie 3, sous-lot 9 : la fenêtre « Nouveau client » (E14). Elle lit l'état sur le serveur et demande l'étape suivante.
 *
 * | Test | Ce qu'il prouve |
 * |---|---|
 * | démarrer | nom requis (erreur sous le champ), identifiant proposé, l'organisation créée, les étapes listées |
 * | en-tête | chaque requête d'une installation porte l'organisation du client |
 * | erreur | l'étape fautive en rouge avec sa phrase, le bouton devient « Reprendre » |
 * | dépense | l'étape 8 demande une confirmation, montant affiché ; rien n'est lancé avant |
 * | clé | la fiche du portail est montrée une fois, à copier |
 * | agent | l'étape 6 ouvre la fenêtre de création unique pour ce client, l'agent créé est retenu |
 * | reprendre | une installation interrompue se relit (liste « en cours », ou désignée) |
 * | fermer | des saisies non enregistrées : on prévient |
 */
import { cleanup, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import type { EtapeVue, InstallationVue } from "@/client/types.gen";

const TITRES: Array<[string, string]> = [
    ["Le client et son organisation", "The client and its organization"],
    ["La base du client", "The client database"],
    ["Établissements et horaires", "Establishments and opening hours"],
    ["Équipe et sujets", "Team and subjects"],
    ["Logiciels proposés", "Proposed software"],
    ["L'agent, depuis une recette", "The agent, from a recipe"],
    ["Clé d'API et fiche du portail", "API key and portal record"],
    ["Appels simulés", "Simulated calls"],
    ["Récapitulatif", "Summary"],
];

function vue(etats: Partial<Record<number, EtapeVue["etat"]>>, extra: Partial<InstallationVue> = {}, erreur?: number): InstallationVue {
    const etapes: EtapeVue[] = TITRES.map(([fr, en], i) => ({
        numero: i + 1,
        cle: `e${i + 1}`,
        titre: { fr, en },
        passable: [2, 3, 4, 5, 7, 8].includes(i + 1),
        depense: i + 1 === 8,
        etat: etats[i + 1] ?? (i === 0 ? "faite" : "a_faire"),
        resultat: {},
        erreur: erreur === i + 1 ? { fr: "Cette base existe déjà.", en: "This database already exists." } : null,
        code_erreur: erreur === i + 1 ? "base_prise" : null,
    }));
    const prochaine = etapes.find((e) => e.etat !== "faite" && e.etat !== "passee")?.numero ?? null;
    return { id: 1, organization_id: 77, nom: "Plomberie Garnier", etat: "ouverte", cree_le: "2026-11-05T08:00:00Z", etapes, prochaine, ...extra };
}

const m = vi.hoisted(() => ({
    demarrer: vi.fn(),
    executer: vi.fn(),
    passer: vi.fn(),
    courante: vi.fn(),
    ouvertes: vi.fn(),
    groupe: vi.fn(),
}));

vi.mock("sonner", () => ({ toast: { success: vi.fn(), error: vi.fn() } }));
vi.mock("next/navigation", () => ({ useRouter: () => ({ refresh: vi.fn(), push: vi.fn(), replace: vi.fn(), back: vi.fn() }) }));
vi.mock("@/components/mark/studio/liste-deroulante", async () => await import("@/components/mark/studio/liste-deroulante-natif-test"));
vi.mock("@/client/sdk.gen", async (importOriginal) => {
    return (await import("../sdk-factice")).sdkFactice(await importOriginal(), {
        demarrerUneInstallationApiV1InstallationsClientPost: (o: unknown) => m.demarrer(o),
        executerUneEtapeApiV1InstallationsClientCouranteEtapesNumeroPost: (o: unknown) => m.executer(o),
        passerUneEtapeApiV1InstallationsClientCouranteEtapesNumeroPasserPost: (o: unknown) => m.passer(o),
        installationCouranteApiV1InstallationsClientCouranteGet: (o: unknown) => m.courante(o),
        installationsOuvertesApiV1InstallationsClientOuvertesGet: (o: unknown) => m.ouvertes(o),
        listerLesRecettesApiV1BuilderRecettesGet: () => Promise.resolve({ data: { defaut: null, recettes: [] }, error: undefined }),
        creerUnGroupeApiV1WorkflowGroupePost: (o: unknown) => m.groupe(o),
        getCatalogueApiV1ConnecteursCatalogueGet: () =>
            Promise.resolve({ data: [{ nom: "google_calendar", libelle: "Google Agenda", integration: "g", actions: [] }], error: undefined }),
    });
});

const { FenetreNouveauClient, identifiantPropose } = await import("./FenetreNouveauClient");

type Appel = { body?: { donnees?: Record<string, unknown>; confirmer?: boolean; nom?: string; identifiant?: string }; headers?: Record<string, string>; path?: { numero: number } };
const appel = (f: { mock: { calls: unknown[][] } }, i = 0) => f.mock.calls[i][0] as Appel;

beforeEach(() => {
    m.ouvertes.mockResolvedValue({ data: [], error: undefined });
});
afterEach(() => {
    cleanup();
    vi.clearAllMocks();
});

async function demarree(etats: Partial<Record<number, EtapeVue["etat"]>> = {}, extra: Partial<InstallationVue> = {}) {
    m.courante.mockResolvedValue({ data: vue(etats, extra), error: undefined });
    const onOuvert = vi.fn();
    render(<FenetreNouveauClient ouvert onOuvert={onOuvert} organisationAReprendre={77} />);
    await screen.findByText(/Plomberie Garnier/);
    return onOuvert;
}

describe("Nouveau client : démarrer", () => {
    it("propose l'identifiant d'après le nom", () => {
        expect(identifiantPropose("Plomberie Garnier & Fils")).toBe("client-plomberie-garnier-fils");
        expect(identifiantPropose("Électricité")).toBe("client-electricite");
    });

    it("exige le nom (erreur sous le champ), crée le client, puis liste ses neuf étapes", async () => {
        m.demarrer.mockResolvedValue({ data: vue({}), error: undefined });
        render(<FenetreNouveauClient ouvert onOuvert={vi.fn()} />);
        fireEvent.click(screen.getByRole("button", { name: "Create the client" }));
        expect(await screen.findByText("Give the company name.")).toBeTruthy();
        expect(m.demarrer).not.toHaveBeenCalled();
        fireEvent.change(screen.getByLabelText("Company name"), { target: { value: "Plomberie Garnier" } });
        expect((screen.getByLabelText("Identifier") as HTMLInputElement).value).toBe("client-plomberie-garnier");
        fireEvent.click(screen.getByRole("button", { name: "Create the client" }));
        await waitFor(() => expect(m.demarrer).toHaveBeenCalledTimes(1));
        expect(appel(m.demarrer).body).toEqual({ nom: "Plomberie Garnier", identifiant: "client-plomberie-garnier" });
        const liste = await screen.findByText("The client database");
        expect(liste.closest("[data-section='etapes']")?.querySelectorAll("li")).toHaveLength(9);
        expect(screen.getByText(/Step 2 of 9/)).toBeTruthy();
    });

    it("un identifiant pris : la phrase du serveur sous le champ", async () => {
        m.demarrer.mockResolvedValue({ data: undefined, error: { detail: { code: "nom_pris", fr: "Un client porte déjà cet identifiant.", en: "A client already uses this identifier." } } });
        render(<FenetreNouveauClient ouvert onOuvert={vi.fn()} />);
        fireEvent.change(screen.getByLabelText("Company name"), { target: { value: "Garnier" } });
        fireEvent.click(screen.getByRole("button", { name: "Create the client" }));
        expect(await screen.findByText("A client already uses this identifier.")).toBeTruthy();
    });
});

describe("Nouveau client : les étapes", () => {
    it("chaque requête porte l'organisation du client ; l'étape 2 part avec sa base", async () => {
        await demarree();
        expect(appel(m.courante).headers).toEqual({ "X-Mark-Organisation": "77" });
        m.executer.mockResolvedValue({ data: { installation: vue({ 2: "faite" }), sautee: false, echec: null, montre: null }, error: undefined });
        fireEvent.change(screen.getByLabelText("Database name"), { target: { value: "client_garnier" } });
        fireEvent.click(screen.getByRole("button", { name: "Set up the database" }));
        await waitFor(() => expect(m.executer).toHaveBeenCalledTimes(1));
        const a = appel(m.executer);
        expect(a.headers).toEqual({ "X-Mark-Organisation": "77" });
        expect(a.path).toEqual({ numero: 2 });
        expect(a.body).toEqual({ donnees: { mode: "creer", nom_base: "client_garnier" }, confirmer: false });
        expect(await screen.findByText("Establishment name")).toBeTruthy();
    });

    it("une étape en erreur : sa phrase en rouge, le bouton devient « Reprendre »", async () => {
        m.courante.mockResolvedValue({ data: vue({ 2: "erreur" }, {}, 2), error: undefined });
        render(<FenetreNouveauClient ouvert onOuvert={vi.fn()} organisationAReprendre={77} />);
        const phrase = await screen.findByText("This database already exists.");
        expect(phrase.getAttribute("role")).toBe("alert");
        expect(screen.getByRole("button", { name: "Resume" })).toBeTruthy();
    });

    it("passer une étape passable", async () => {
        await demarree();
        m.passer.mockResolvedValue({ data: vue({ 2: "passee" }), error: undefined });
        fireEvent.click(screen.getByRole("button", { name: "Skip this step" }));
        await waitFor(() => expect(appel(m.passer).path).toEqual({ numero: 2 }));
        expect(await screen.findByText("· skipped")).toBeTruthy();
    });

    it("l'étape 8 dépense : confirmation avec le montant, rien n'est lancé avant", async () => {
        await demarree({ 2: "passee", 3: "passee", 4: "passee", 5: "passee", 6: "faite", 7: "passee" }, { estimation: { scenarios: 3, montant: null, plafond: 2, devise: "EUR" } });
        expect(screen.getByText(/3 scenario\(s\)/).textContent).toMatch(/amount unknown until the first call, at most the cap/);
        fireEvent.click(screen.getByRole("button", { name: "Run the simulated calls" }));
        const boite = await screen.findByRole("alertdialog", { name: "Confirm the spending" });
        expect(m.executer).not.toHaveBeenCalled();
        m.executer.mockResolvedValue({ data: { installation: vue({ 2: "passee", 3: "passee", 4: "passee", 5: "passee", 6: "faite", 7: "passee", 8: "faite" }), sautee: false, echec: null, montre: null }, error: undefined });
        fireEvent.click(within(boite).getByRole("button", { name: "Confirm the spending" }));
        await waitFor(() => expect(m.executer).toHaveBeenCalledTimes(1));
        expect(appel(m.executer).body).toEqual({ donnees: {}, confirmer: true });
    });

    it("l'étape 7 montre la fiche du portail une seule fois, à copier", async () => {
        await demarree({ 2: "passee", 3: "passee", 4: "passee", 5: "passee", 6: "faite" });
        const fiche = { format: "client-portail-mark", version: 1, organisation_id: 77, nom: "Plomberie Garnier", cle_api: { valeur: "cle-{{J}}", prefixe: "dgr_" }, base: null };
        m.executer.mockResolvedValue({ data: { installation: vue({ 2: "passee", 3: "passee", 4: "passee", 5: "passee", 6: "faite", 7: "faite" }), sautee: false, echec: null, montre: { fiche_portail: fiche } }, error: undefined });
        fireEvent.click(screen.getByRole("button", { name: "Create the client's key" }));
        const bloc = await screen.findByText("Shown only once. Copy it before closing.");
        expect(bloc.closest("[data-section='fiche-portail']")?.textContent).toContain("client-portail-mark");
        expect(screen.getByRole("button", { name: "Copy the portal record" })).toBeTruthy();
    });

    it("l'étape 6 ouvre la fenêtre de création unique pour ce client et retient l'agent créé", async () => {
        await demarree({ 2: "passee", 3: "passee", 4: "passee", 5: "passee" });
        m.groupe.mockResolvedValue({ data: { workflow_id: 40, folder_id: 2 }, error: undefined });
        m.executer.mockResolvedValue({ data: { installation: vue({ 2: "passee", 3: "passee", 4: "passee", 5: "passee", 6: "faite" }), sautee: false, echec: null, montre: null }, error: undefined });
        fireEvent.click(screen.getByRole("button", { name: "Create the agent" }));
        const fenetre = await screen.findByRole("dialog");
        expect(fenetre.getAttribute("data-modale")).toBe("creation-d-agent");
        fireEvent.change(within(fenetre).getByLabelText("Name"), { target: { value: "Accueil" } });
        fireEvent.click(within(fenetre).getByRole("button", { name: "Create the draft" }));
        await waitFor(() => expect(m.executer).toHaveBeenCalledTimes(1));
        expect(appel(m.groupe).headers).toEqual({ "X-Mark-Organisation": "77" });
        expect(appel(m.executer).body).toEqual({ donnees: { workflow_id: 40 }, confirmer: false });
    });
});

describe("Nouveau client : reprendre et fermer", () => {
    it("propose de reprendre une installation en cours", async () => {
        m.ouvertes.mockResolvedValue({ data: [{ id: 1, organization_id: 77, nom: "Plomberie Garnier", cree_le: "2026-11-05T08:00:00Z", prochaine: 3, faites: 2, erreur: false }], error: undefined });
        m.courante.mockResolvedValue({ data: vue({ 2: "faite" }), error: undefined });
        render(<FenetreNouveauClient ouvert onOuvert={vi.fn()} />);
        fireEvent.click(await screen.findByRole("button", { name: "Resume" }));
        await waitFor(() => expect(appel(m.courante).headers).toEqual({ "X-Mark-Organisation": "77" }));
        expect(await screen.findByText(/Step 3 of 9/)).toBeTruthy();
    });

    it("des saisies non enregistrées : fermer demande confirmation", async () => {
        const onOuvert = await demarree();
        fireEvent.change(screen.getByLabelText("Database name"), { target: { value: "autre" } });
        // La croix de la fenêtre et le bouton du pied passent par le même geste.
        fireEvent.click(screen.getAllByRole("button", { name: "Close" }).find((b) => b.textContent === "Close") as HTMLElement);
        expect(await screen.findByRole("alertdialog", { name: "Close anyway" })).toBeTruthy();
        expect(onOuvert).not.toHaveBeenCalledWith(false);
        fireEvent.click(screen.getByRole("button", { name: "Close anyway" }));
        expect(onOuvert).toHaveBeenCalledWith(false);
    });
});
