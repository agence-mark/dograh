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
import { ECHECS } from "@/components/mark/notifications/phrases-echec";
import { lireNotifications } from "@/components/mark/notifications/magasin";
import { phraseAttendue } from "@/components/mark/notifications/texte-attendu";
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
    champs: vi.fn(),
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
    champsDUneFamilleApiV1BuilderBibliothequeFamillesFamilleChampsGet: (...a: unknown[]) => m.champs(...a),
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
    m.champs.mockResolvedValue({ data: [] });
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

// Radix ouvre un menu au clavier : Entrée sur son déclencheur.
const ouvrirLeMenu = async (nom: RegExp) => {
    const declencheur = await screen.findByRole("button", { name: nom });
    fireEvent.keyDown(declencheur, { key: "Enter" });
};
const fenetreNouvelElement = async () => {
    fireEvent.click(await screen.findByRole("button", { name: /New element/ }));
    return screen.findByTestId("nouvel-element");
};

describe("[.mark] the Library page: the list", () => {
    it("shows status, version, author, bench and « used by N agents » of each element", async () => {
        render(<PageBibliotheque />);
        const recette = await screen.findByTestId("element-moules-etape-qualifier");
        expect(recette.textContent).toContain("Qualify");
        expect(recette.textContent).toContain("Recipe");
        expect(recette.textContent).toContain("v2");
        expect(recette.textContent).toContain("v12, 31 of 39");
        expect(within(recette).getByTestId("nb-agents").textContent).toBe("3");
        const candidat = screen.getByTestId("element-lexiques-commun");
        expect(candidat.textContent).toContain("Candidate");
        expect(within(candidat).getByTestId("nb-agents").textContent).toBe("–");
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
        await ouvrirLeMenu(/Labels/);
        fireEvent.click(await screen.findByRole("menuitemcheckbox", { name: /urgence/ }));
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
        {
            const affiche = (await screen.findByRole("alert")).textContent ?? "";
            expect(affiche).toMatch(phraseAttendue(ECHECS.bibliothequeParcourir));
            expect(affiche).not.toContain("not configured");
        }
    });
});

describe("[.mark] the Library page: families, sheets, labels, filing and drops", () => {
    it("creates a family from the window and reads the families again", async () => {
        render(<PageBibliotheque />);
        fireEvent.click(await screen.findByRole("button", { name: /New family/ }));
        const nom = await screen.findByLabelText("Name");
        fireEvent.change(nom, { target: { value: "Trades" } });
        fireEvent.change(screen.getByLabelText("Description"), { target: { value: "Trade sheets" } });
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
        await ouvrirLeMenu(/Labels/);
        fireEvent.click(await screen.findByText("Manage labels…"));
        const fenetre = await screen.findByTestId("gestion-etiquettes");
        expect(within(fenetre).getByTestId("nb-urgence").textContent).toBe("2");
        m.renommerEtiquette.mockResolvedValue({ data: [{ nom: "panne", elements: 2 }] });
        fireEvent.click(within(fenetre).getByRole("button", { name: "Rename urgence" }));
        const champ = within(fenetre).getByLabelText("New name");
        fireEvent.change(champ, { target: { value: "panne" } });
        fireEvent.keyDown(champ, { key: "Enter" });
        await waitFor(() => expect(m.renommerEtiquette).toHaveBeenCalledWith({ query: { ancien: "urgence" }, body: { nom: "panne" } }));
    });

    it("deletes a label only after the confirmation that says how many elements lose it", async () => {
        render(<PageBibliotheque />);
        await ouvrirLeMenu(/Labels/);
        fireEvent.click(await screen.findByText("Manage labels…"));
        const fenetre = await screen.findByTestId("gestion-etiquettes");
        m.supprimerEtiquette.mockResolvedValue({ data: [] });
        fireEvent.click(within(fenetre).getByRole("button", { name: "Delete urgence" }));
        expect(m.supprimerEtiquette).not.toHaveBeenCalled();
        expect(fenetre.textContent).toContain("Removed from 2 element(s)");
        fireEvent.click(within(fenetre).getByRole("button", { name: "Delete" }));
        await waitFor(() => expect(m.supprimerEtiquette).toHaveBeenCalledWith({ query: { nom: "urgence" } }));
    });

    it("creates a label from the « Labels » menu", async () => {
        render(<PageBibliotheque />);
        await ouvrirLeMenu(/Labels/);
        m.creerEtiquette.mockResolvedValue({ data: [] });
        const champ = await screen.findByLabelText("New label");
        fireEvent.change(champ, { target: { value: "banc" } });
        fireEvent.keyDown(champ, { key: "Enter" });
        await waitFor(() => expect(m.creerEtiquette).toHaveBeenCalledWith({ body: { nom: "banc" } }));
    });

    it("drops a document: the file goes to the server and the result says it is a Candidate", async () => {
        render(<PageBibliotheque />);
        await fenetreNouvelElement();
        fireEvent.click(screen.getByRole("button", { name: "Drop a file" }));
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
        await fenetreNouvelElement();
        fireEvent.click(screen.getByRole("button", { name: "Drop a file" }));
        const depot = await screen.findByTestId("depot-document");
        fireEvent.change(depot.querySelector("[data-depot-fichier]") as HTMLInputElement, { target: { files: [new File(["x"], "x.exe")] } });
        m.deposer.mockResolvedValue({ error: { detail: "The document is not read: Format not supported" } });
        fireEvent.click(within(depot).getByRole("button", { name: "Drop as a Candidate" }));
        // Clôture D2 : un échec d'écriture passe par une notification (phrase écrite, jamais le texte du serveur).
        await waitFor(() => expect(lireNotifications().some((n) => n.sorte === "echec" && n.texte.fr === ECHECS.bibliothequeDeposerDocument.fr)).toBe(true));
        expect(lireNotifications().map((n) => n.texte.fr + n.texte.en).join(" ")).not.toContain("Format not supported");
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
        fireEvent.click(within(detail).getByRole("button", { name: "Promote to Recipe" }));
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
        fireEvent.click(within(detail).getByRole("button", { name: "Reject" }));
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
        fireEvent.click(within(detail).getByRole("button", { name: "Promote to Recipe" }));
        fireEvent.change(within(detail).getByLabelText("The bench that proves it"), { target: { value: "banc" } });
        m.statut.mockResolvedValue({ error: { detail: "Only members of the .mark organization write in the library." } });
        fireEvent.click(within(detail).getByRole("button", { name: "Promote to Recipe" }));
        await waitFor(() => expect(lireNotifications().some((n) => n.sorte === "echec" && n.texte.fr === ECHECS.bibliothequeChanger.fr)).toBe(true));
        expect(lireNotifications().map((n) => n.texte.fr + n.texte.en).join(" ")).not.toContain("Only members of the .mark organization");
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
        fireEvent.click(await screen.findByRole("button", { name: /Proposals/ }));
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
        const vide = await screen.findByTestId("propositions-vide");
        // V2b : l'état vide est celui du design (coche, titre), jamais un paragraphe encadré dans la fenêtre.
        expect(vide.querySelector("[class*=border]")).toBeNull();
    });

    it("refuses a proposal with its reason", async () => {
        m.propositions.mockResolvedValue({ data: [PROPOSITION] });
        render(<PageBibliotheque />);
        fireEvent.click(await screen.findByRole("button", { name: /Proposals/ }));
        const carte = await screen.findByTestId("proposition-p1");
        fireEvent.change(within(carte).getByLabelText("Reason for refusing"), { target: { value: "not proven" } });
        m.refuser.mockResolvedValue({ data: { ...PROPOSITION, etat: "refusee" } });
        fireEvent.click(within(carte).getByRole("button", { name: "Refuse" }));
        await waitFor(() => expect(m.refuser).toHaveBeenCalledWith({ path: { identifiant: "p1" }, body: { motif: "not proven" } }));
    });

    it("imports with its origin, licence and date, and shows what changed since the last import", async () => {
        render(<PageBibliotheque />);
        const form = await fenetreNouvelElement();
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
        const form = await fenetreNouvelElement();
        fireEvent.change(within(form).getByLabelText("Title"), { target: { value: "New" } });
        m.creer.mockResolvedValue({ data: ELEMENT });
        fireEvent.click(within(form).getByRole("button", { name: "Create as a Candidate" }));
        await waitFor(() =>
            expect(m.creer).toHaveBeenCalledWith({ path: { famille: "moules-etape" }, body: { slug: "new", titre: "New", contenu: { texte: "" }, notes: "" } }),
        );
    });
});

describe("[.mark] K5: the « New element » window and the frame of the maquette", () => {
    it("files the new element in its sub-folder with its labels, after creating it (never a new version)", async () => {
        render(<PageBibliotheque />);
        const form = await fenetreNouvelElement();
        fireEvent.change(within(form).getByLabelText("Title"), { target: { value: "Rdv fait accompli" } });
        fireEvent.change(within(form).getByLabelText("Content"), { target: { value: "Two slots." } });
        fireEvent.change(within(form).getByLabelText("Version notes"), { target: { value: "first" } });
        fireEvent.click(within(form).getByText(/\+ Label/));
        const champ = within(form).getByLabelText("Label to add");
        fireEvent.change(champ, { target: { value: "urgence" } });
        fireEvent.keyDown(champ, { key: "Enter" });
        m.creer.mockResolvedValue({ data: ELEMENT });
        m.ranger.mockResolvedValue({ data: ELEMENT });
        fireEvent.click(within(form).getByRole("button", { name: "Create as a Candidate" }));
        await waitFor(() =>
            expect(m.creer).toHaveBeenCalledWith({
                path: { famille: "moules-etape" },
                body: { slug: "rdv-fait-accompli", titre: "Rdv fait accompli", contenu: { texte: "Two slots." }, notes: "first" },
            }),
        );
        await waitFor(() =>
            expect(m.ranger).toHaveBeenCalledWith({ path: { famille: "moules-etape", slug: "rdv-fait-accompli" }, body: { etiquettes: ["urgence"] } }),
        );
    });

    it("refuses a JSON that is not an object for a family read by a mechanism, without calling the server", async () => {
        m.familles.mockResolvedValue({ data: [{ ...FAMILLES[0], slug: "lexiques", libelle: "Lexicons" }] });
        render(<PageBibliotheque />);
        const form = await fenetreNouvelElement();
        fireEvent.change(within(form).getByLabelText("Title"), { target: { value: "Terms" } });
        fireEvent.change(within(form).getByLabelText("Content (JSON)"), { target: { value: "[1]" } });
        fireEvent.click(within(form).getByRole("button", { name: "Create as a Candidate" }));
        expect((await within(form).findByRole("alert")).textContent).toContain("not a valid JSON object");
        expect(m.creer).not.toHaveBeenCalled();
    });

    it("shows the number of proposals waiting on the « Proposals » button, and the first family is chosen at the start", async () => {
        m.propositions.mockResolvedValue({ data: [{ id: "p1", etat: "en_attente" }, { id: "p2", etat: "acceptee" }] });
        render(<PageBibliotheque />);
        const bouton = await screen.findByRole("button", { name: /Proposals/ });
        await waitFor(() => expect(bouton.textContent).toContain("1"));
        await waitFor(() => expect(m.elements).toHaveBeenLastCalledWith({ query: expect.objectContaining({ famille: "moules-etape" }) }));
    });
});

describe("[.mark] lot 14 (SE-21): Library, I-1, I-3, I-5", () => {
    it("I-5: each family shows its number of elements, read with the list of families", async () => {
        m.familles.mockResolvedValue({ data: [{ ...FAMILLES[0], nombre: 3 }, { ...FAMILLES[1], nombre: 0 }] });
        render(<PageBibliotheque />);
        expect((await screen.findByTestId("nombre-moules-etape")).textContent).toBe("3");
        expect(screen.getByTestId("nombre-lexiques").textContent).toBe("0");
    });

    it("I-1: the status pills add up and are sent to the server as a list; a second click on a pill takes it off", async () => {
        render(<PageBibliotheque />);
        await screen.findByTestId("element-lexiques-commun");
        fireEvent.click(screen.getByRole("button", { name: "Candidate" }));
        fireEvent.click(screen.getByRole("button", { name: "Rejected" }));
        await waitFor(() => expect(m.elements).toHaveBeenLastCalledWith({ query: expect.objectContaining({ statut: ["candidat", "rejete"] }) }));
        fireEvent.click(screen.getByRole("button", { name: "Candidate" }));
        await waitFor(() => expect(m.elements).toHaveBeenLastCalledWith({ query: expect.objectContaining({ statut: ["rejete"] }) }));
        fireEvent.click(screen.getByRole("button", { name: "Rejected" }));
        await waitFor(() => expect(m.elements).toHaveBeenLastCalledWith({ query: expect.objectContaining({ statut: undefined }) }));
    });

    it("I-3: a family read by a mechanism shows a form of its fields (no JSON by hand) and sends the content built from them", async () => {
        m.familles.mockResolvedValue({ data: [{ ...FAMILLES[0], slug: "scenarios-test", libelle: "Test scenarios" }] });
        m.champs.mockResolvedValue({
            data: [
                { nom: "but", sorte: "long", obligatoire: true, choix: [] },
                { nom: "tours_max", sorte: "nombre", obligatoire: false, choix: [] },
                { nom: "questions_juge", sorte: "liste", obligatoire: false, choix: [] },
                { nom: "criteres", sorte: "objet", obligatoire: false, choix: [] },
            ],
        });
        m.creer.mockResolvedValue({ data: { famille: "scenarios-test", slug: "panne" } });
        render(<PageBibliotheque />);
        const form = await fenetreNouvelElement();
        const champs = await within(form).findByTestId("champs-de-la-famille");
        expect(within(form).queryByLabelText("Content (JSON)")).toBeNull();
        fireEvent.change(within(form).getByLabelText("Title"), { target: { value: "Panne" } });
        fireEvent.change(within(champs).getByLabelText("but"), { target: { value: "Booking" } });
        fireEvent.change(within(champs).getByLabelText("tours max"), { target: { value: "8" } });
        fireEvent.change(within(champs).getByLabelText("questions juge"), { target: { value: "Q1\n\nQ2" } });
        fireEvent.change(within(champs).getByLabelText("criteres"), { target: { value: "[{" } });
        fireEvent.click(within(form).getByRole("button", { name: "Create as a Candidate" }));
        expect((await within(champs).findByRole("alert")).textContent).toContain("Not valid JSON");
        expect(m.creer).not.toHaveBeenCalled();
        fireEvent.change(within(champs).getByLabelText("criteres"), { target: { value: '[{"type":"x"}]' } });
        fireEvent.click(within(form).getByRole("button", { name: "Create as a Candidate" }));
        await waitFor(() => expect(m.creer).toHaveBeenCalled());
        expect(m.creer.mock.calls[0][0].body.contenu).toEqual({ but: "Booking", tours_max: 8, questions_juge: ["Q1", "Q2"], criteres: [{ type: "x" }] });
    });
});
