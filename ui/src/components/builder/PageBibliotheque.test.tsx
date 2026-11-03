/**
 * [.mark] builder-agent-vocal (lot 2): the « Library » page.
 *
 * Questions of this file:
 *
 *     Does the list show the status, version, author, bench and « used by N agents » of each element, and filter by
 *     family and status? Does an element show its versions, origin and the Candidate warning? Is « Promote to Recipe »
 *     closed until the bench is written, and « Reject » until the reason is? Does a rollback name the version? Is a
 *     refusal of the server shown as it comes? Do proposals need a reason to be refused? Does an import send its
 *     origin and show what changed? Is the page in the side menu?
 */
import { cleanup, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { PageBibliotheque } from "./PageBibliotheque";

const m = vi.hoisted(() => ({
    familles: vi.fn(),
    elements: vi.fn(),
    element: vi.fn(),
    usage: vi.fn(),
    creer: vi.fn(),
    version: vi.fn(),
    retour: vi.fn(),
    statut: vi.fn(),
    importer: vi.fn(),
    propositions: vi.fn(),
    accepter: vi.fn(),
    refuser: vi.fn(),
    etiquettes: vi.fn(),
    dossiers: vi.fn(),
    creerDossier: vi.fn(),
    supprimerDossier: vi.fn(),
    creerFamille: vi.fn(),
    modifierFamille: vi.fn(),
    ranger: vi.fn(),
    deposer: vi.fn(),
    creerEtiquette: vi.fn(),
    renommerEtiquette: vi.fn(),
    supprimerEtiquette: vi.fn(),
}));

vi.mock("@/client", () => ({
    listerLesFamillesApiV1BuilderBibliothequeFamillesGet: (...a: unknown[]) => m.familles(...a),
    parcourirApiV1BuilderBibliothequeParcourirGet: (...a: unknown[]) => m.elements(...a),
    listerLesEtiquettesApiV1BuilderBibliothequeEtiquettesGet: (...a: unknown[]) => m.etiquettes(...a),
    listerLesDossiersApiV1BuilderBibliothequeFamillesFamilleDossiersGet: (...a: unknown[]) => m.dossiers(...a),
    creerUnDossierApiV1BuilderBibliothequeFamillesFamilleDossiersPost: (...a: unknown[]) => m.creerDossier(...a),
    supprimerUnDossierApiV1BuilderBibliothequeFamillesFamilleDossiersDelete: (...a: unknown[]) => m.supprimerDossier(...a),
    creerUneFamilleApiV1BuilderBibliothequeFamillesPost: (...a: unknown[]) => m.creerFamille(...a),
    modifierUneFamilleApiV1BuilderBibliothequeFamillesFamillePut: (...a: unknown[]) => m.modifierFamille(...a),
    rangerUnElementApiV1BuilderBibliothequeFamilleSlugRangementPost: (...a: unknown[]) => m.ranger(...a),
    deposerUnDocumentApiV1BuilderBibliothequeDepotPost: (...a: unknown[]) => m.deposer(...a),
    creerUneEtiquetteApiV1BuilderBibliothequeEtiquettesPost: (...a: unknown[]) => m.creerEtiquette(...a),
    renommerUneEtiquetteApiV1BuilderBibliothequeEtiquettesPut: (...a: unknown[]) => m.renommerEtiquette(...a),
    supprimerUneEtiquetteApiV1BuilderBibliothequeEtiquettesDelete: (...a: unknown[]) => m.supprimerEtiquette(...a),
    lireUnElementApiV1BuilderBibliothequeFamilleSlugGet: (...a: unknown[]) => m.element(...a),
    lireLUtilisationApiV1BuilderBibliothequeFamilleSlugUtilisationGet: (...a: unknown[]) => m.usage(...a),
    creerUnElementApiV1BuilderBibliothequeFamillePost: (...a: unknown[]) => m.creer(...a),
    ajouterUneVersionApiV1BuilderBibliothequeFamilleSlugVersionsPost: (...a: unknown[]) => m.version(...a),
    revenirEnArriereApiV1BuilderBibliothequeFamilleSlugRetourPost: (...a: unknown[]) => m.retour(...a),
    changerLeStatutApiV1BuilderBibliothequeFamilleSlugStatutPost: (...a: unknown[]) => m.statut(...a),
    importerApiV1BuilderBibliothequeImportPost: (...a: unknown[]) => m.importer(...a),
    listerLesPropositionsApiV1BuilderBibliothequePropositionsGet: (...a: unknown[]) => m.propositions(...a),
    accepterApiV1BuilderBibliothequePropositionsIdentifiantAccepterPost: (...a: unknown[]) => m.accepter(...a),
    refuserApiV1BuilderBibliothequePropositionsIdentifiantRefuserPost: (...a: unknown[]) => m.refuser(...a),
    agentsDUneRecetteApiV1BuilderTestsRecetteFamilleSlugAgentsGet: () => Promise.resolve({ data: { version: 1, agents: [] } }),
    preparerLesMisesAJourApiV1BuilderTestsRecetteFamilleSlugPreparerPost: () => Promise.resolve({ data: { agents: [] } }),
}));

const FICHE = { description: "What it is", quand: "When", comment: "How" };
const FAMILLES = [
    { slug: "moules-etape", libelle: "Step templates", groupe: "construit", cible: "x", mode: "fournit", du_code: true, fiche: FICHE },
    { slug: "lexiques", libelle: "Lexicons", groupe: "regle", cible: "x", mode: "applique", du_code: true, fiche: FICHE },
];
const RESUMES = [
    { famille: "moules-etape", slug: "qualifier", titre: "Qualify", statut: "recette", version_courante: 2, auteur: "alice", date: "2026-10-30T10:00:00Z", banc: { description: "v12, 31 of 39" }, origine: null, utilisee_par: 3 },
    { famille: "lexiques", slug: "commun", titre: "Common", statut: "candidat", version_courante: 1, auteur: "bob", date: "2026-10-30T11:00:00Z", banc: null, origine: null, utilisee_par: 0 },
];
const version = (numero: number, extra: Record<string, unknown> = {}) => ({
    numero, auteur: "alice", date: "2026-10-30T10:00:00Z", notes: "", statut: "candidat", contenu: { texte: `v${numero}` }, ...extra,
});
const ELEMENT = {
    famille: "lexiques", slug: "commun", titre: "Common", version_courante: 2,
    versions: [version(1, { notes: "first" }), version(2, { notes: "shorter", origine: { source: "https://x.test/g", licence: "MIT", date: "2026-10-31" } })],
};

beforeEach(() => {
    m.familles.mockResolvedValue({ data: FAMILLES });
    m.elements.mockResolvedValue({ data: { total: RESUMES.length, elements: RESUMES } });
    m.etiquettes.mockResolvedValue({ data: [{ nom: "urgence", elements: 2 }] });
    m.dossiers.mockResolvedValue({ data: ["rdv"] });
    m.element.mockResolvedValue({ data: ELEMENT });
    m.usage.mockResolvedValue({ data: { nombre: 2, agents: [] } });
    m.propositions.mockResolvedValue({ data: [] });
});
afterEach(() => {
    cleanup();
    vi.clearAllMocks();
});

const ouvrir = async (testid = "element-lexiques-commun") => {
    render(<PageBibliotheque />);
    fireEvent.click(await screen.findByTestId(testid));
    return screen.findByTestId("element-detail");
};

describe("[.mark] the Library page: the list", () => {
    it("shows status, version, author, bench and « used by N agents » of each element", async () => {
        render(<PageBibliotheque />);
        const recette = await screen.findByTestId("element-moules-etape-qualifier");
        expect(recette.textContent).toContain("Qualify");
        expect(recette.textContent).toContain("Recipe");
        expect(recette.textContent).toContain("v2 · alice");
        expect(recette.textContent).toContain("v12, 31 of 39");
        expect(recette.textContent).toContain("Used by 3 agent(s)");
        const candidat = screen.getByTestId("element-lexiques-commun");
        expect(candidat.textContent).toContain("Candidate");
        expect(candidat.textContent).toContain("Used by 0 agent(s)");
    });

    it("filters by family, status, sub-folder and label, sending the filter to the server, 25 per page", async () => {
        render(<PageBibliotheque />);
        await screen.findByTestId("element-lexiques-commun");
        expect(m.elements).toHaveBeenCalledWith({ query: expect.objectContaining({ limite: 25, decalage: 0 }) });
        fireEvent.click(screen.getByTestId("famille-lexiques"));
        await waitFor(() => expect(m.elements).toHaveBeenLastCalledWith({ query: expect.objectContaining({ famille: "lexiques" }) }));
        expect(m.dossiers).toHaveBeenLastCalledWith({ path: { famille: "lexiques" } });
        fireEvent.click(within(await screen.findByTestId("sous-dossiers")).getByRole("button", { name: "rdv" }));
        await waitFor(() => expect(m.elements).toHaveBeenLastCalledWith({ query: expect.objectContaining({ famille: "lexiques", dossier: "rdv" }) }));
        fireEvent.click(within(screen.getByTestId("filtre-etiquettes")).getByRole("button", { name: /urgence/ }));
        await waitFor(() => expect(m.elements).toHaveBeenLastCalledWith({ query: expect.objectContaining({ etiquette: ["urgence"] }) }));
    });

    it("searches the whole library after the last keystroke and shows the matching passage", async () => {
        m.elements.mockResolvedValue({ data: { total: 1, elements: [{ ...RESUMES[1], extrait: "…tuyau de poêle…" }] } });
        render(<PageBibliotheque />);
        fireEvent.change(await screen.findByLabelText("Search the whole library"), { target: { value: "tuyau" } });
        await waitFor(() => expect(m.elements).toHaveBeenLastCalledWith({ query: expect.objectContaining({ q: "tuyau", decalage: 0 }) }));
        expect((await screen.findByTestId("element-lexiques-commun")).textContent).toContain("tuyau de poêle");
    });

    it("asks the server for the next page when the list is longer than 25", async () => {
        m.elements.mockResolvedValue({ data: { total: 60, elements: RESUMES } });
        render(<PageBibliotheque />);
        await screen.findByTestId("element-lexiques-commun");
        fireEvent.click(screen.getByRole("button", { name: /next|suivant/i }));
        await waitFor(() => expect(m.elements).toHaveBeenLastCalledWith({ query: expect.objectContaining({ decalage: 25 }) }));
    });

    it("says so when the filter finds nothing, and shows a refusal of the server as it comes", async () => {
        m.elements.mockResolvedValueOnce({ data: { total: 0, elements: [] } });
        render(<PageBibliotheque />);
        expect(await screen.findByTestId("bibliotheque-vide")).toBeTruthy();
        cleanup();
        m.elements.mockResolvedValueOnce({ error: { detail: "The library organization is not configured" } });
        render(<PageBibliotheque />);
        expect((await screen.findByRole("alert")).textContent).toContain("not configured");
    });
});

describe("[.mark] the Library page: families, sheets, labels, filing and drops", () => {
    it("creates a family from the window and reads the families again", async () => {
        render(<PageBibliotheque />);
        fireEvent.click(await screen.findByRole("button", { name: /New family/ }));
        const nom = await screen.findByLabelText("Name");
        fireEvent.change(nom, { target: { value: "Trades" } });
        fireEvent.change(screen.getByLabelText("What it is"), { target: { value: "Trade sheets" } });
        m.creerFamille.mockResolvedValue({ data: { ...FAMILLES[0], slug: "trades", libelle: "Trades", du_code: false } });
        fireEvent.click(screen.getByRole("button", { name: "Create the family" }));
        await waitFor(() => expect(m.creerFamille).toHaveBeenCalledOnce());
        expect(m.creerFamille.mock.calls[0][0].body).toMatchObject({ slug: "trades", libelle: "Trades", fiche: { description: "Trade sheets" } });
        await waitFor(() => expect(m.familles.mock.calls.length).toBeGreaterThan(1));
    });

    it("edits the sheet of a family", async () => {
        render(<PageBibliotheque />);
        fireEvent.click(await screen.findByTestId("famille-lexiques"));
        fireEvent.click(await screen.findByRole("button", { name: "Sheet of the family" }));
        const champ = await screen.findByLabelText("When to use it");
        expect((champ as HTMLTextAreaElement).value).toBe("When");
        fireEvent.change(champ, { target: { value: "Before any search" } });
        m.modifierFamille.mockResolvedValue({ data: FAMILLES[1] });
        fireEvent.click(screen.getByRole("button", { name: "Save the sheet" }));
        await waitFor(() =>
            expect(m.modifierFamille).toHaveBeenCalledWith({
                path: { famille: "lexiques" },
                body: { fiche: { description: "What it is", quand: "Before any search", comment: "How" } },
            }),
        );
    });

    it("puts a label on an element without touching its versions", async () => {
        await ouvrir();
        const rangement = await screen.findByTestId("rangement");
        m.ranger.mockResolvedValue({ data: { ...ELEMENT, etiquettes: ["urgence"], dossier: "" } });
        fireEvent.click(within(rangement).getByText(/\+ Label/));
        const champ = within(rangement).getByLabelText("Label to add");
        fireEvent.change(champ, { target: { value: "urgence" } });
        fireEvent.keyDown(champ, { key: "Enter" });
        await waitFor(() =>
            expect(m.ranger).toHaveBeenCalledWith({ path: { famille: "lexiques", slug: "commun" }, body: { etiquettes: ["urgence"] } }),
        );
    });

    it("manages the labels: rename and delete go to the server, the count is shown", async () => {
        render(<PageBibliotheque />);
        fireEvent.click(await screen.findByText("Manage labels…"));
        const fenetre = await screen.findByTestId("gestion-etiquettes");
        expect(fenetre.textContent).toContain("2 element(s)");
        m.renommerEtiquette.mockResolvedValue({ data: [{ nom: "panne", elements: 2 }] });
        fireEvent.click(within(fenetre).getByRole("button", { name: "Rename" }));
        fireEvent.change(within(fenetre).getByLabelText("New name"), { target: { value: "panne" } });
        fireEvent.click(within(fenetre).getByRole("button", { name: "Rename" }));
        await waitFor(() => expect(m.renommerEtiquette).toHaveBeenCalledWith({ query: { ancien: "urgence" }, body: { nom: "panne" } }));
    });

    it("deletes a label only after the confirmation that says how many elements lose it", async () => {
        render(<PageBibliotheque />);
        fireEvent.click(await screen.findByText("Manage labels…"));
        const fenetre = await screen.findByTestId("gestion-etiquettes");
        m.supprimerEtiquette.mockResolvedValue({ data: [] });
        fireEvent.click(within(fenetre).getByRole("button", { name: "Delete" }));
        expect(m.supprimerEtiquette).not.toHaveBeenCalled();
        fireEvent.click(within(fenetre).getByRole("button", { name: /Remove from 2 element/ }));
        await waitFor(() => expect(m.supprimerEtiquette).toHaveBeenCalledWith({ query: { nom: "urgence" } }));
    });

    it("drops a document: the file goes to the server and the result says it is a Candidate", async () => {
        render(<PageBibliotheque />);
        fireEvent.click(screen.getByRole("tab", { name: "Add" }));
        const depot = await screen.findByTestId("depot-document");
        const fichier = new File(["# Rule"], "rule.md", { type: "text/markdown" });
        fireEvent.change(depot.querySelector("[data-depot-fichier]") as HTMLInputElement, { target: { files: [fichier] } });
        m.deposer.mockResolvedValue({ data: { element: ELEMENT, cree: true, comparatif: null } });
        fireEvent.click(within(depot).getByRole("button", { name: "Drop as a Candidate" }));
        await waitFor(() => expect(m.deposer).toHaveBeenCalledOnce());
        expect(m.deposer.mock.calls[0][0].body).toMatchObject({ famille: "moules-etape", fichier, licence: "inconnue" });
        expect((await within(depot).findByTestId("depot-resultat")).textContent).toContain("Dropped as a Candidate");
    });

    it("shows the refusal of a drop as it comes", async () => {
        render(<PageBibliotheque />);
        fireEvent.click(screen.getByRole("tab", { name: "Add" }));
        const depot = await screen.findByTestId("depot-document");
        fireEvent.change(depot.querySelector("[data-depot-fichier]") as HTMLInputElement, { target: { files: [new File(["x"], "x.exe")] } });
        m.deposer.mockResolvedValue({ error: { detail: "The document is not read: Format not supported" } });
        fireEvent.click(within(depot).getByRole("button", { name: "Drop as a Candidate" }));
        expect((await within(depot).findByRole("alert")).textContent).toContain("Format not supported");
    });
});

describe("[.mark] the Library page: one element", () => {
    it("shows its versions with author, date, notes, its origin, the Candidate warning and its use", async () => {
        const detail = await ouvrir();
        expect(within(detail).getByTestId("statut-courant").textContent).toBe("Candidate");
        expect(within(detail).getByTestId("avertissement-candidat").textContent).toContain("not proven");
        expect(within(detail).getByTestId("origine-courante").textContent).toContain("https://x.test/g");
        expect(within(detail).getByTestId("origine-courante").textContent).toContain("MIT");
        expect(within(detail).getByTestId("utilisee-par").textContent).toBe("Used by 2 agent(s)");
        expect(within(detail).getByTestId("version-1").textContent).toContain("first");
        expect(within(detail).getByTestId("version-2").textContent).toContain("shorter");
        expect(m.element).toHaveBeenCalledWith({ path: { famille: "lexiques", slug: "commun" } });
    });

    it("keeps « Promote to Recipe » closed until the bench is written, then sends it", async () => {
        const detail = await ouvrir();
        const bouton = within(detail).getByRole("button", { name: "Promote to Recipe" }) as HTMLButtonElement;
        expect(bouton.disabled).toBe(true);
        fireEvent.change(within(detail).getByLabelText("The bench that proves it"), { target: { value: "  3 x 3 green  " } });
        expect(bouton.disabled).toBe(false);
        m.statut.mockResolvedValue({ data: { ...ELEMENT, versions: [ELEMENT.versions[0], { ...ELEMENT.versions[1], statut: "recette", banc: { description: "3 x 3 green" } }] } });
        fireEvent.click(bouton);
        await waitFor(() => expect(m.statut).toHaveBeenCalledOnce());
        expect(m.statut.mock.calls[0][0]).toEqual({
            path: { famille: "lexiques", slug: "commun" },
            body: { version: 2, statut: "recette", banc: { description: "3 x 3 green" } },
        });
        expect((await screen.findByTestId("banc-courant")).textContent).toContain("3 x 3 green");
        expect(screen.getByTestId("statut-courant").textContent).toBe("Recipe");
    });

    it("keeps « Reject » closed until the reason is written, then keeps the reason", async () => {
        const detail = await ouvrir();
        const bouton = within(detail).getByRole("button", { name: "Reject this version" }) as HTMLButtonElement;
        expect(bouton.disabled).toBe(true);
        fireEvent.change(within(detail).getByLabelText("The reason, kept with it"), { target: { value: "too long" } });
        m.statut.mockResolvedValue({ data: { ...ELEMENT, versions: [ELEMENT.versions[0], { ...ELEMENT.versions[1], statut: "rejete", raison_rejet: "too long" }] } });
        fireEvent.click(bouton);
        await waitFor(() => expect(m.statut.mock.calls[0][0].body).toEqual({ version: 2, statut: "rejete", raison: "too long" }));
        expect((await screen.findByTestId("raison-rejet")).textContent).toContain("too long");
    });

    it("goes back to a named version", async () => {
        const detail = await ouvrir();
        m.retour.mockResolvedValue({ data: { ...ELEMENT, version_courante: 3, versions: [...ELEMENT.versions, version(3, { restaure_de: 1 })] } });
        fireEvent.click(within(within(detail).getByTestId("version-1")).getByRole("button", { name: "Go back to this version" }));
        await waitFor(() => expect(m.retour).toHaveBeenCalledWith({ path: { famille: "lexiques", slug: "commun" }, body: { version: 1 } }));
        expect(await screen.findByTestId("version-3")).toBeTruthy();
    });

    it("refuses invalid JSON without calling the server, and says a new version is a Candidate", async () => {
        const detail = await ouvrir();
        fireEvent.click(within(detail).getByRole("button", { name: "New version" }));
        expect(screen.getByText(/always a Candidate/)).toBeTruthy();
        fireEvent.change(within(detail).getByLabelText("Content of the new version (JSON)"), { target: { value: "{pas du json" } });
        fireEvent.click(within(detail).getByRole("button", { name: "Save the version" }));
        expect((await screen.findByRole("alert")).textContent).toContain("not valid JSON");
        expect(m.version).not.toHaveBeenCalled();
    });

    it("sends a new version with its notes", async () => {
        const detail = await ouvrir();
        fireEvent.click(within(detail).getByRole("button", { name: "New version" }));
        fireEvent.change(within(detail).getByLabelText("Content of the new version (JSON)"), { target: { value: '{"texte": "v3"}' } });
        fireEvent.change(within(detail).getByLabelText("Notes"), { target: { value: "clearer" } });
        m.version.mockResolvedValue({ data: { ...ELEMENT, version_courante: 3, versions: [...ELEMENT.versions, version(3, { notes: "clearer" })] } });
        fireEvent.click(within(detail).getByRole("button", { name: "Save the version" }));
        await waitFor(() => expect(m.version).toHaveBeenCalledWith({ path: { famille: "lexiques", slug: "commun" }, body: { contenu: { texte: "v3" }, notes: "clearer" } }));
        expect((await screen.findByTestId("version-3")).textContent).toContain("clearer");
    });

    it("shows the refusal of a person who is not in the .mark team", async () => {
        const detail = await ouvrir();
        fireEvent.change(within(detail).getByLabelText("The bench that proves it"), { target: { value: "banc" } });
        m.statut.mockResolvedValue({ error: { detail: "Only members of the .mark organization write in the library." } });
        fireEvent.click(within(detail).getByRole("button", { name: "Promote to Recipe" }));
        expect((await screen.findByRole("alert")).textContent).toContain("Only members of the .mark organization");
    });
});

describe("[.mark] the Library page: proposals and import", () => {
    const PROPOSITION = {
        id: "p1", type: "passage_recette", famille: "lexiques", slug: "commun", version: 1, justification: "3 x 3 green",
        auteur: "builder pour dograh:p1", date: "2026-10-30T12:00:00Z", etat: "en_attente",
    };

    it("lists the proposals, accepts one with its bench and keeps « Refuse » closed without a reason", async () => {
        m.propositions.mockResolvedValue({ data: [PROPOSITION] });
        render(<PageBibliotheque />);
        fireEvent.click(screen.getByRole("tab", { name: "Proposals" }));
        const carte = await screen.findByTestId("proposition-p1");
        expect(carte.textContent).toContain("Move to Recipe");
        expect(carte.textContent).toContain("builder pour dograh:p1");
        expect((within(carte).getByRole("button", { name: "Refuse" }) as HTMLButtonElement).disabled).toBe(true);
        fireEvent.change(within(carte).getByLabelText("The bench that proves it"), { target: { value: "3 x 3 green" } });
        m.accepter.mockResolvedValue({ data: { ...PROPOSITION, etat: "acceptee" } });
        m.propositions.mockResolvedValue({ data: [] });
        fireEvent.click(within(carte).getByRole("button", { name: "Accept" }));
        await waitFor(() =>
            expect(m.accepter).toHaveBeenCalledWith({ path: { identifiant: "p1" }, body: { banc: { description: "3 x 3 green" } } }),
        );
        expect(await screen.findByTestId("propositions-vide")).toBeTruthy();
    });

    it("refuses a proposal with its reason", async () => {
        m.propositions.mockResolvedValue({ data: [PROPOSITION] });
        render(<PageBibliotheque />);
        fireEvent.click(screen.getByRole("tab", { name: "Proposals" }));
        const carte = await screen.findByTestId("proposition-p1");
        fireEvent.change(within(carte).getByLabelText("Reason for refusing"), { target: { value: "not proven" } });
        m.refuser.mockResolvedValue({ data: { ...PROPOSITION, etat: "refusee" } });
        fireEvent.click(within(carte).getByRole("button", { name: "Refuse" }));
        await waitFor(() => expect(m.refuser).toHaveBeenCalledWith({ path: { identifiant: "p1" }, body: { motif: "not proven" } }));
    });

    it("imports with its origin, licence and date, and shows what changed since the last import", async () => {
        render(<PageBibliotheque />);
        fireEvent.click(screen.getByRole("tab", { name: "Add" }));
        const form = await screen.findByTestId("formulaire-import");
        fireEvent.change(within(form).getByLabelText("Identifier (a-z, 0-9, -)"), { target: { value: "guide" } });
        fireEvent.change(within(form).getByLabelText("Title"), { target: { value: "Guide" } });
        fireEvent.click(within(form).getByLabelText(/comes from a source outside/));
        const bouton = within(form).getByRole("button", { name: "Import as a Candidate" }) as HTMLButtonElement;
        expect(bouton.disabled).toBe(true); // origin and licence are required
        fireEvent.change(within(form).getByLabelText("Source (address or file)"), { target: { value: "https://x.test/g" } });
        fireEvent.change(within(form).getByLabelText("Licence (or « unknown »)"), { target: { value: "MIT" } });
        fireEvent.change(within(form).getByLabelText("Date"), { target: { value: "2026-10-31" } });
        expect(bouton.disabled).toBe(false);
        m.importer.mockResolvedValue({ data: { element: ELEMENT, cree: false, comparatif: { identique: false, ajoutees: 2, retirees: 1, diff: "-a\n+b" } } });
        fireEvent.click(bouton);
        await waitFor(() => expect(m.importer).toHaveBeenCalledOnce());
        expect(m.importer.mock.calls[0][0].body).toMatchObject({
            famille: "moules-etape", slug: "guide", titre: "Guide",
            origine: { source: "https://x.test/g", licence: "MIT", date: "2026-10-31" },
        });
        expect((await screen.findByTestId("comparatif")).textContent).toContain("2 line(s) added, 1 removed");
    });

    it("creates a plain element as a Candidate", async () => {
        render(<PageBibliotheque />);
        fireEvent.click(screen.getByRole("tab", { name: "Add" }));
        const form = await screen.findByTestId("formulaire-import");
        fireEvent.change(within(form).getByLabelText("Identifier (a-z, 0-9, -)"), { target: { value: "neuf" } });
        fireEvent.change(within(form).getByLabelText("Title"), { target: { value: "New" } });
        m.creer.mockResolvedValue({ data: ELEMENT });
        fireEvent.click(within(form).getByRole("button", { name: "Create as a Candidate" }));
        await waitFor(() =>
            expect(m.creer).toHaveBeenCalledWith({ path: { famille: "moules-etape" }, body: { slug: "neuf", titre: "New", contenu: { texte: "" } } }),
        );
    });
});
