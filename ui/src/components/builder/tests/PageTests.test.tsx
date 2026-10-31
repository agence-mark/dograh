/**
 * [.mark] builder-agent-vocal (lot 6): the « Tests and corrections » page and its pieces.
 *
 * Questions of this file:
 *
 *     Are the tests listed by folder with their last run? Does the publication banner say what blocks? Does a replay show the
 *     reason under the agent's reply at fault, and the diagnosis with « nothing changes without your agreement »? Is the judge's
 *     opinion apart and noted? Does the form send the criteria the code understands (and the call's run and reply for a test
 *     from a call)? Does the call page's button list the caller's replies? Does the history offer the way back? Does the
 *     « To triage » line assign, set the origin and show where it leads? Does a recipe list its agents and prepare drafts?
 */
import { cleanup, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { AgentsDeLaRecette } from "./AgentsDeLaRecette";
import { BoutonCreerUnTest, repliquesDeLaPersonne } from "./BoutonCreerUnTest";
import { fautesDeLaReplique } from "./DetailDunTest";
import { critereDeLaLigne, NouveauTest } from "./NouveauTest";
import { PageTests, parDossier } from "./PageTests";
import type { ResumeDeTest } from "./types";

const m = vi.hoisted(() => ({
    liste: vi.fn(),
    publication: vi.fn(),
    corrections: vi.fn(),
    test: vi.fn(),
    rejouer: vi.fn(),
    exporter: vi.fn(),
    changer: vi.fn(),
    supprimer: vi.fn(),
    retour: vi.fn(),
    creer: vi.fn(),
    note: vi.fn(),
    agents: vi.fn(),
    preparer: vi.fn(),
}));

vi.mock("@/client", () => ({
    lireLesTestsApiV1BuilderTestsWorkflowIdGet: (o: unknown) => m.liste(o),
    etatDeLaPublicationApiV1BuilderTestsWorkflowIdPublicationGet: (o: unknown) => m.publication(o),
    historiqueDesCorrectionsApiV1BuilderTestsWorkflowIdCorrectionsGet: (o: unknown) => m.corrections(o),
    lireUnTestApiV1BuilderTestsWorkflowIdSlugGet: (o: unknown) => m.test(o),
    rejouerLaSuiteApiV1BuilderTestsWorkflowIdRejouerPost: (o: unknown) => m.rejouer(o),
    exporterLesTestsApiV1BuilderTestsWorkflowIdExportGet: (o: unknown) => m.exporter(o),
    changerUnTestApiV1BuilderTestsWorkflowIdSlugPatch: (o: unknown) => m.changer(o),
    supprimerUnTestApiV1BuilderTestsWorkflowIdSlugDelete: (o: unknown) => m.supprimer(o),
    retourArriereApiV1BuilderTestsWorkflowIdCorrectionsCorrectionIdRetourPost: (o: unknown) => m.retour(o),
    creerUnTestApiV1BuilderTestsWorkflowIdPost: (o: unknown) => m.creer(o),
    noterLeJugeApiV1BuilderTestsWorkflowIdJugeNotesPost: (o: unknown) => m.note(o),
    agentsDUneRecetteApiV1BuilderTestsRecetteFamilleSlugAgentsGet: (o: unknown) => m.agents(o),
    preparerLesMisesAJourApiV1BuilderTestsRecetteFamilleSlugPreparerPost: (o: unknown) => m.preparer(o),
}));

const TESTS: ResumeDeTest[] = [
    { slug: "numero-dit", nom: "Numéro dit", obligatoire: true, dossier: "Sécurité", origine: "client", genre: "replique", criteres: 1, derniere: { le: "2026-10-31T10:00:00+00:00", version: 2, statut: "echec", reussis: 2, total: 3 } },
    { slug: "libre", nom: "Appelant pressé", obligatoire: false, dossier: "", origine: "fiche", genre: "conversation", criteres: 2, derniere: null },
];

const DETAIL = {
    test: { slug: "numero-dit", nom: "Numéro dit", obligatoire: true, dossier: "Sécurité", origine: "client", criteres: [{ type: "texte_absent", texte: "outil_interne" }], replique: "Bonjour" },
    resultats: [
        {
            le: "2026-10-31T10:00:00+00:00",
            version: 2,
            statut: "echec",
            reussis: 2,
            total: 3,
            essais: [
                { numero: 1, reussi: true, criteres: [], lignes: [["moi", "Bonjour"], ["agent", "Bien sûr."]] },
                {
                    numero: 2,
                    reussi: false,
                    criteres: [{ critere: { type: "texte_absent", texte: "outil_interne" }, reussi: false, detail: "x", rang: 1, raison: "This reply says « outil_interne », which it must not." }],
                    lignes: [["agent", "Bonjour."], ["moi", "Un renseignement"], ["agent", "Je lance outil_interne."]],
                },
            ],
            juge: { bloquant: false, avis: [{ question: "Le ton est-il naturel ?", ok: false, serre: true, passes: 3, raison: "froid" }] },
        },
    ],
};

const SUITE = {
    ok: false,
    total: 1,
    refus: true,
    echecs: [
        {
            test: "numero-dit", nom: "Numéro dit", obligatoire: true, essai: 2, critere: { type: "texte_absent", texte: "outil_interne" },
            raison: "This reply says « outil_interne », which it must not.", rang: 1, replique: "Je lance outil_interne.",
            diagnostic: { cause: "agent", raison: "The test ran and its criterion makes sense: the agent answered otherwise.", accord_requis: true },
        },
    ],
};

beforeEach(() => {
    m.liste.mockResolvedValue({ data: { tests: TESTS } });
    m.publication.mockResolvedValue({
        data: {
            brouillon: true, version: 2, suivi: true, bloque: true,
            controle: { ok: false, bloquants: [{ code: "exemple_de_valeur", gravite: "bloquant", message: "The prompt gives a phone number as an example", etape: "Accueil", extrait: "06 12" }], avertissements: [{ code: "fait_en_dur", gravite: "avertissement", message: "A fact is written in the prompt", etape: null, extrait: null }] },
            tests_obligatoires: [{ slug: "numero-dit", nom: "Numéro dit", raison: "failed (2/3)" }],
        },
    });
    m.corrections.mockResolvedValue({ data: { corrections: [{ id: "c2", le: "2026-10-31T10:00:00+00:00", version: 2, vert: false, resume: "changed: Accueil", restaure_de: null, retour_possible: true }, { id: "c1", le: "2026-10-30T10:00:00+00:00", version: 1, vert: true, resume: "First tested version.", restaure_de: null, retour_possible: false }] } });
    m.test.mockResolvedValue({ data: DETAIL });
    m.rejouer.mockResolvedValue({ data: SUITE });
    m.changer.mockResolvedValue({ data: {} });
    m.supprimer.mockResolvedValue({ data: { ok: true } });
    m.retour.mockResolvedValue({ data: { ok: true, message: "Restored as a draft. Replay the whole suite before calling it verified." } });
    m.creer.mockResolvedValue({ data: { ok: true, test: { slug: "nouveau" } } });
    m.note.mockResolvedValue({ data: { ok: true } });
    m.exporter.mockResolvedValue({ data: { format: "tests-agent-mark", tests: [] } });
});
afterEach(() => {
    cleanup();
    vi.clearAllMocks();
});

describe("la page Tests et corrections", () => {
    it("liste les tests par dossier avec leur dernière exécution", async () => {
        render(<PageTests workflowId={42} />);
        await screen.findByText("Numéro dit");
        expect(m.liste).toHaveBeenCalledWith({ path: { workflow_id: 42 } });
        const dossiers = screen.getAllByTestId("dossier-de-tests");
        expect(dossiers).toHaveLength(2);
        expect(within(dossiers[0]).getByText("Sécurité")).toBeTruthy();
        expect(within(dossiers[0]).getByText("2/3")).toBeTruthy();
        expect(screen.getByText(/never replayed/i)).toBeTruthy();
        expect(parDossier(TESTS).map(([d]) => d)).toEqual(["Sécurité", ""]);
    });

    it("dit ce qui bloque la publication : le contrôle du prompt et les tests obligatoires", async () => {
        render(<PageTests workflowId={42} />);
        const bandeau = await screen.findByTestId("bandeau-publication");
        expect(bandeau.textContent).toContain("Publication blocked");
        expect(bandeau.textContent).toContain("phone number as an example");
        expect(bandeau.textContent).toContain("failed (2/3)");
        expect(bandeau.textContent).toContain("A fact is written in the prompt"); // l'avertissement est dit, sans bloquer
    });

    it("rejoue toute la suite et montre la raison, la réplique fautive et le diagnostic sans rien changer", async () => {
        render(<PageTests workflowId={42} />);
        await screen.findByText("Numéro dit");
        fireEvent.click(screen.getByRole("button", { name: /Replay the whole suite/ }));
        const echec = await screen.findByTestId("echec-de-la-suite");
        expect(m.rejouer).toHaveBeenCalledWith({ path: { workflow_id: 42 }, body: { repetitions: 3 } });
        expect(echec.textContent).toContain("Je lance outil_interne.");
        expect(echec.textContent).toContain("which it must not");
        expect(screen.getByTestId("diagnostic").textContent).toContain("The agent");
        expect(screen.getByTestId("diagnostic").textContent).toContain("Nothing is changed without your agreement");
        expect(screen.getByTestId("resultat-de-la-suite").textContent).toContain("Refused: a required test fails");
        await waitFor(() => expect(m.liste.mock.calls.length).toBeGreaterThan(1)); // la liste est relue après le rejeu
    });

    it("montre le détail : la raison est écrite sous la réplique fautive, pas ailleurs", async () => {
        render(<PageTests workflowId={42} />);
        fireEvent.click(await screen.findByText("Numéro dit"));
        await screen.findByTestId("detail-du-test");
        fireEvent.click(screen.getByRole("button", { name: /Attempt 2/ }));
        const conversation = await screen.findByTestId("conversation-du-test");
        const fautives = conversation.querySelectorAll("[data-faute]");
        expect(fautives).toHaveLength(1);
        expect(fautives[0].textContent).toContain("Je lance outil_interne.");
        expect(within(fautives[0] as HTMLElement).getByTestId("raison-de-l-echec").textContent).toContain("which it must not");
        expect(fautesDeLaReplique(DETAIL.resultats[0].essais[1].criteres as never, 0)).toHaveLength(0);
        expect(fautesDeLaReplique(DETAIL.resultats[0].essais[1].criteres as never, 1)).toHaveLength(1);
    });

    it("garde l'avis du juge à part, et le noter appelle la calibration", async () => {
        render(<PageTests workflowId={42} />);
        fireEvent.click(await screen.findByText("Numéro dit"));
        const juge = await screen.findByTestId("avis-du-juge");
        expect(juge.textContent).toContain("blocks nothing");
        expect(juge.textContent).toContain("3 passes, close call");
        fireEvent.click(within(juge).getByRole("button", { name: /I agree/ }));
        await waitFor(() => expect(m.note).toHaveBeenCalledWith({ path: { workflow_id: 42 }, body: { identifiant: "numero-dit:2026-10-31T10:00:00+00:00:0", ok: true } }));
    });

    it("rend un test obligatoire ou non, et le supprime", async () => {
        render(<PageTests workflowId={42} />);
        fireEvent.click(await screen.findByText("Numéro dit"));
        const detail = await screen.findByTestId("detail-du-test");
        fireEvent.click(within(detail).getByRole("checkbox", { name: "Required" }));
        await waitFor(() => expect(m.changer).toHaveBeenCalledWith({ path: { workflow_id: 42, slug: "numero-dit" }, body: { obligatoire: false } }));
        fireEvent.click(within(detail).getByRole("button", { name: "Delete" }));
        await waitFor(() => expect(m.supprimer).toHaveBeenCalledWith({ path: { workflow_id: 42, slug: "numero-dit" } }));
    });

    it("offre le retour arrière seulement quand l'instantané est gardé, et dit de rejouer la suite", async () => {
        render(<PageTests workflowId={42} />);
        const historique = await screen.findByTestId("historique-des-corrections");
        const boutons = within(historique).getAllByRole("button", { name: /Go back to this version/ });
        expect((boutons[1] as HTMLButtonElement).disabled).toBe(true);
        fireEvent.click(boutons[0]);
        await waitFor(() => expect(m.retour).toHaveBeenCalledWith({ path: { workflow_id: 42, correction_id: "c2" } }));
        await screen.findByText(/Replay the whole suite before calling it verified/);
    });

    it("exporte un fichier pour le labo", async () => {
        const creer = vi.fn(() => "blob:test");
        Object.assign(URL, { createObjectURL: creer, revokeObjectURL: vi.fn() });
        const clic = vi.spyOn(HTMLAnchorElement.prototype, "click").mockImplementation(() => undefined);
        render(<PageTests workflowId={42} />);
        await screen.findByText("Numéro dit");
        fireEvent.click(screen.getByRole("button", { name: /Export for the lab/ }));
        await waitFor(() => expect(clic).toHaveBeenCalled());
        expect(m.exporter).toHaveBeenCalledWith({ path: { workflow_id: 42 } });
        clic.mockRestore();
    });

    it("dit comment créer un premier test quand il n'y en a pas, et grise le rejeu", async () => {
        m.liste.mockResolvedValue({ data: { tests: [] } });
        render(<PageTests workflowId={42} />);
        expect((await screen.findByTestId("aucun-test")).textContent).toContain("from a reply of a call");
        expect((screen.getByRole("button", { name: /Replay the whole suite/ }) as HTMLButtonElement).disabled).toBe(true);
    });

    it("montre l'erreur du serveur telle qu'elle vient", async () => {
        m.liste.mockResolvedValue({ error: { detail: "Workflow not found" } });
        render(<PageTests workflowId={42} />);
        expect((await screen.findByRole("alert")).textContent).toBe("Workflow not found");
    });
});

describe("le formulaire d'un nouveau test", () => {
    it("envoie les critères tels que le code les comprend", async () => {
        const onCree = vi.fn();
        render(<NouveauTest workflowId={42} onCree={onCree} />);
        fireEvent.change(screen.getByLabelText("Test name"), { target: { value: "Mon test" } });
        fireEvent.change(screen.getByLabelText("Reply"), { target: { value: "Bonjour" } });
        fireEvent.change(screen.getByLabelText("Text"), { target: { value: "outil_interne" } });
        fireEvent.click(screen.getByRole("button", { name: "Add a criterion" }));
        const selects = screen.getAllByLabelText("Criterion");
        fireEvent.change(selects[1], { target: { value: "outil" } });
        fireEvent.change(screen.getByLabelText("Tool name"), { target: { value: "noter" } });
        fireEvent.click(screen.getByLabelText("Must NOT be called"));
        fireEvent.click(screen.getByLabelText("Required"));
        fireEvent.click(screen.getByRole("button", { name: "Create the test" }));
        await waitFor(() => expect(m.creer).toHaveBeenCalled());
        expect(m.creer.mock.calls[0][0]).toEqual({
            path: { workflow_id: 42 },
            body: {
                nom: "Mon test",
                replique: "Bonjour",
                criteres: [{ type: "texte_absent", texte: "outil_interne" }, { type: "outil", nom: "noter", appele: false }],
                obligatoire: true,
                dossier: "",
                origine: "manuel",
            },
        });
        await waitFor(() => expect(onCree).toHaveBeenCalledWith("nouveau"));
    });

    it("envoie le run et le rang d'un test tiré d'un appel, et rien de la conversation", async () => {
        render(<NouveauTest workflowId={42} source={{ runId: 7, rang: 2, extrait: "mon numéro" }} onCree={() => undefined} />);
        expect(screen.getByTestId("source-du-test").textContent).toContain("7");
        fireEvent.change(screen.getByLabelText("Test name"), { target: { value: "Depuis l'appel" } });
        fireEvent.change(screen.getByLabelText("Text"), { target: { value: "06" } });
        fireEvent.click(screen.getByRole("button", { name: "Create the test" }));
        await waitFor(() => expect(m.creer).toHaveBeenCalled());
        const corps = m.creer.mock.calls[0][0].body;
        expect(corps).toMatchObject({ run_id: 7, rang: 2, origine: "client" });
        expect(corps.replique).toBeUndefined();
    });

    it("garde fermé le bouton tant que le nom et la réplique manquent, et montre un refus du serveur", async () => {
        m.creer.mockResolvedValue({ error: { detail: "The test still holds data that looks real: nothing was kept." } });
        render(<NouveauTest workflowId={42} onCree={() => undefined} />);
        const bouton = screen.getByRole("button", { name: "Create the test" }) as HTMLButtonElement;
        expect(bouton.disabled).toBe(true);
        fireEvent.change(screen.getByLabelText("Test name"), { target: { value: "x" } });
        fireEvent.change(screen.getByLabelText("Reply"), { target: { value: "bonjour" } });
        expect(bouton.disabled).toBe(false);
        fireEvent.click(bouton);
        expect((await screen.findByRole("alert")).textContent).toContain("looks real");
    });

    it("traduit une ligne de critère en critère du serveur", () => {
        expect(critereDeLaLigne({ type: "mecanique_dite", valeurs: { noms: "a, b ,," } })).toEqual({ type: "mecanique_dite", noms: ["a", "b"] });
        expect(critereDeLaLigne({ type: "merci_en_tete", valeurs: { max: "2" } })).toEqual({ type: "merci_en_tete", max: 2 });
        expect(critereDeLaLigne({ type: "appel_clos_par_l_agent", valeurs: {} })).toEqual({ type: "appel_clos_par_l_agent" });
    });
});

describe("le bouton de la page d'un appel", () => {
    const EVENEMENTS = [
        { type: "rtf-bot-text", payload: { text: "Bonjour" } },
        { type: "rtf-user-transcription", payload: { final: true, text: "Je voudrais un devis" } },
        { type: "rtf-user-transcription", payload: { final: false, text: "mon num" } },
        { type: "rtf-user-transcription", payload: { final: true, text: "Mon numéro est le zéro six" } },
    ];

    it("liste les répliques finales de la personne et crée depuis celle qui est choisie", async () => {
        expect(repliquesDeLaPersonne(EVENEMENTS)).toEqual(["Je voudrais un devis", "Mon numéro est le zéro six"]);
        render(<BoutonCreerUnTest workflowId={42} runId={9} evenements={EVENEMENTS} />);
        fireEvent.click(screen.getByRole("button", { name: /Create a test from a reply/ }));
        fireEvent.change(screen.getByLabelText("Reply"), { target: { value: "2" } });
        fireEvent.change(screen.getByLabelText("Test name"), { target: { value: "Numéro" } });
        fireEvent.change(screen.getByLabelText("Text"), { target: { value: "06" } });
        fireEvent.click(screen.getByRole("button", { name: "Create the test" }));
        await waitFor(() => expect(m.creer.mock.calls[0][0].body).toMatchObject({ run_id: 9, rang: 2 }));
        expect((await screen.findByTestId("test-cree")).textContent).toContain("Test created");
    });

    it("s'ouvre sur la réplique demandée par la page À trier et ne s'affiche pas sans réplique", () => {
        render(<BoutonCreerUnTest workflowId={42} runId={9} evenements={EVENEMENTS} rangInitial={2} />);
        expect(screen.getByTestId("source-du-test").textContent).toContain("2");
        cleanup();
        const { container } = render(<BoutonCreerUnTest workflowId={42} runId={9} evenements={[]} />);
        expect(container.innerHTML).toBe("");
    });
});

describe("les agents d'une recette (B30)", () => {
    beforeEach(() => {
        m.agents.mockResolvedValue({ data: { version: 2, agents: [{ organisation: 7, agent: 42, version: 1, a_jour: false }, { organisation: 7, agent: 43, version: 2, a_jour: true }] } });
        m.preparer.mockResolvedValue({
            data: {
                agents: [
                    { agent: 42, etat: "brouillon_prepare", message: "A draft holds the new version. Nothing is published.", suite: { ok: true, total: 3, echecs: 0, disponible: true } },
                    { agent: 44, etat: "proposition", message: "The rule « outil_tarde » was changed in this agent." },
                ],
            },
        });
    });

    it("liste les agents avec la version utilisée et prépare des brouillons sans rien publier", async () => {
        render(<AgentsDeLaRecette famille="phrases-du-code" slug="attente-outil" />);
        const bloc = await screen.findByTestId("agents-de-la-recette");
        expect(bloc.textContent).toContain("#42");
        expect(bloc.textContent).toContain("v1 → v2");
        fireEvent.click(within(bloc).getByRole("button", { name: /Prepare the updates/ }));
        const lignes = await screen.findByTestId("mises-a-jour-preparees");
        expect(m.preparer).toHaveBeenCalledWith({ path: { famille: "phrases-du-code", slug: "attente-outil" }, body: { rejouer_la_suite: true } });
        expect(lignes.textContent).toContain("draft prepared");
        expect(lignes.textContent).toContain("suite green");
        expect(lignes.textContent).toContain("proposal (customized, nothing overwritten)");
    });

    it("ne propose rien quand tous les agents sont à jour", async () => {
        m.agents.mockResolvedValue({ data: { version: 2, agents: [{ organisation: 7, agent: 43, version: 2, a_jour: true }] } });
        render(<AgentsDeLaRecette famille="phrases-du-code" slug="attente-outil" />);
        await screen.findByTestId("agents-de-la-recette");
        expect(screen.queryByRole("button", { name: /Prepare the updates/ })).toBeNull();
    });
});
