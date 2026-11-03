/**
 * [.mark] U3 (E47): l'onglet Tests de l'agent.
 *
 * Questions de ce fichier :
 *
 *     La liste rend-elle les tests (cases, sorte, obligatoire, dernier résultat, modifié) et les exécutions passées ? « Tout jouer »
 *     rejoue-t-il la sélection, les obligatoires ou toute la suite, avec le nombre d'essais ? La fenêtre d'un test crée les trois
 *     sortes (rien en dur : les listes viennent de l'agent et de la bibliothèque), modifie un test existant par la route de
 *     modification, et ne propose jamais l'ancien critère « merci » ? « Depuis la bibliothèque » dit ce qui manque avant de copier ?
 *     Les fonctions d'avant (bandeau de publication, raison sur la réplique fautive, diagnostic, avis du juge, retour arrière,
 *     export) sont-elles toutes gardées ?
 */
import { cleanup, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { fautesDeLaReplique } from "./DetailDunTest";
import { PageTests, parDossier } from "./PageTests";
import type { ResumeDeTest } from "./types";
import { sorteDuTest } from "./types";

vi.mock("next/navigation", () => ({ useRouter: () => ({ push: vi.fn() }), usePathname: () => "/agents/42/tests" }));

const m = vi.hoisted(() => ({
    liste: vi.fn(),
    publication: vi.fn(),
    corrections: vi.fn(),
    passees: vi.fn(),
    ressources: vi.fn(),
    test: vi.fn(),
    rejouer: vi.fn(),
    exporter: vi.fn(),
    changer: vi.fn(),
    supprimer: vi.fn(),
    retour: vi.fn(),
    creer: vi.fn(),
    note: vi.fn(),
    examiner: vi.fn(),
    copier: vi.fn(),
}));

vi.mock("@/client", () => ({
    lireLesTestsApiV1BuilderTestsWorkflowIdGet: (o: unknown) => m.liste(o),
    etatDeLaPublicationApiV1BuilderTestsWorkflowIdPublicationGet: (o: unknown) => m.publication(o),
    historiqueDesCorrectionsApiV1BuilderTestsWorkflowIdCorrectionsGet: (o: unknown) => m.corrections(o),
    executionsPasseesApiV1BuilderTestsWorkflowIdExecutionsGet: (o: unknown) => m.passees(o),
    ressourcesDeLAgentApiV1BuilderTestsWorkflowIdRessourcesGet: (o: unknown) => m.ressources(o),
    lireUnTestApiV1BuilderTestsWorkflowIdSlugGet: (o: unknown) => m.test(o),
    rejouerLaSuiteApiV1BuilderTestsWorkflowIdRejouerPost: (o: unknown) => m.rejouer(o),
    exporterLesTestsApiV1BuilderTestsWorkflowIdExportGet: (o: unknown) => m.exporter(o),
    changerUnTestApiV1BuilderTestsWorkflowIdSlugPatch: (o: unknown) => m.changer(o),
    supprimerUnTestApiV1BuilderTestsWorkflowIdSlugDelete: (o: unknown) => m.supprimer(o),
    retourArriereApiV1BuilderTestsWorkflowIdCorrectionsCorrectionIdRetourPost: (o: unknown) => m.retour(o),
    creerUnTestApiV1BuilderTestsWorkflowIdPost: (o: unknown) => m.creer(o),
    noterLeJugeApiV1BuilderTestsWorkflowIdJugeNotesPost: (o: unknown) => m.note(o),
    examinerUnScenarioApiV1BuilderBibliothequeScenariosTypesSlugExaminerPost: (o: unknown) => m.examiner(o),
    copierUnScenarioApiV1BuilderBibliothequeScenariosTypesSlugCopierPost: (o: unknown) => m.copier(o),
}));

const TESTS: ResumeDeTest[] = [
    { slug: "numero-dit", nom: "Numéro dit", description: "Le numéro reste muet", modifie_le: "2026-10-31T11:00:00+00:00", obligatoire: true, dossier: "Sécurité", origine: "client", genre: "replique", criteres: 1, derniere: { le: "2026-10-31T10:00:00+00:00", version: 2, statut: "echec", reussis: 2, total: 3 } },
    { slug: "libre", nom: "Appelant pressé", obligatoire: false, dossier: "", origine: "fiche", genre: "conversation", criteres: 2, derniere: null },
];

const DETAIL = {
    test: { slug: "numero-dit", nom: "Numéro dit", obligatoire: true, dossier: "Sécurité", origine: "client", criteres: [{ type: "texte_absent", texte: "outil_interne" }, { type: "merci_en_tete", max: 0 }], replique: "Bonjour", historique: [{ role: "assistant", texte: "Bonjour, je vous écoute." }] },
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

const RESSOURCES = {
    etapes: ["Accueil", "Collecte"],
    outils: ["chercher_un_creneau", "noter"],
    issues: ["rendez_vous", "abandon"],
    champs: ["nom"],
    personnages: [{ slug: "presse", titre: "Appelant pressé" }],
    scenarios_types: [{ slug: "capture-simple", titre: "Capture simple", statut: "candidat" }],
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
    m.passees.mockResolvedValue({ data: { executions: [{ test: "numero-dit", nom: "Numéro dit", obligatoire: true, le: "2026-10-31T10:00:00+00:00", version: 2, statut: "echec", reussis: 2, total: 3 }] } });
    m.ressources.mockResolvedValue({ data: RESSOURCES });
    m.test.mockResolvedValue({ data: DETAIL });
    m.rejouer.mockResolvedValue({ data: SUITE });
    m.changer.mockResolvedValue({ data: {} });
    m.supprimer.mockResolvedValue({ data: { ok: true } });
    m.retour.mockResolvedValue({ data: { ok: true, message: "Restored as a draft. Replay the whole suite before calling it verified." } });
    m.creer.mockResolvedValue({ data: { ok: true, test: { slug: "nouveau" } } });
    m.note.mockResolvedValue({ data: { ok: true } });
    m.exporter.mockResolvedValue({ data: { format: "tests-agent-mark", tests: [] } });
    m.examiner.mockResolvedValue({ data: { titre: "Capture simple", but: "Veut un rendez-vous", personnage_absent: false, absents: [{ critere: 0, type: "outil", manque: "chercher_un_creneau", sorte: "outil" }] } });
    m.copier.mockResolvedValue({ data: { copie: true, test: { slug: "capture-simple" } } });
});
afterEach(() => {
    cleanup();
    vi.clearAllMocks();
});

/** Un menu Radix s'ouvre au pointeur, pas au clic. */
function ouvrir(nom: RegExp) {
    const bouton = screen.getByRole("button", { name: nom });
    fireEvent.pointerDown(bouton, { button: 0, ctrlKey: false });
}

describe("la liste de l'onglet", () => {
    it("rend cases, sorte, obligatoire, dernier résultat et modifié, par dossier", async () => {
        render(<PageTests workflowId={42} />);
        await screen.findByText("Numéro dit");
        expect(m.liste).toHaveBeenCalledWith({ path: { workflow_id: 42 } });
        // K3 (maquette) : le dossier se lit sous le nom du test, plus en ligne de titre.
        expect(screen.getAllByText(/Sécurité/)).toHaveLength(1);
        expect(screen.getByText("2/3")).toBeTruthy();
        expect(screen.getByText(/Le numéro reste muet/)).toBeTruthy();
        expect(screen.getAllByText("–").length).toBeGreaterThan(0);
        expect(screen.getByText("2026-10-31 11:00")).toBeTruthy();
        expect(screen.getAllByRole("checkbox")).toHaveLength(2);
        expect(parDossier(TESTS).map(([d]) => d)).toEqual(["Sécurité", ""]);
    });

    it("liste les exécutions passées de tous les tests", async () => {
        render(<PageTests workflowId={42} />);
        await screen.findByText("Numéro dit");
        fireEvent.click(screen.getByRole("button", { name: "Past runs" }));
        const passees = await screen.findByTestId("executions-passees");
        expect(passees.textContent).toContain("Numéro dit");
        expect(passees.textContent).toContain("2/3");
        fireEvent.click(within(passees).getByText("Numéro dit"));
        expect((await screen.findByTestId("fenetre-d-execution")).textContent).toContain("Numéro dit");
    });

    it("dit ce qui bloque la publication : le contrôle du prompt et les tests obligatoires", async () => {
        render(<PageTests workflowId={42} />);
        const bandeau = await screen.findByTestId("bandeau-publication");
        expect(bandeau.textContent).toContain("Publication blocked");
        expect(bandeau.textContent).toContain("phone number as an example");
        expect(bandeau.textContent).toContain("failed (2/3)");
        expect(bandeau.textContent).toContain("A fact is written in the prompt");
    });

    it("dit comment créer un premier test quand il n'y en a pas, et grise « Tout jouer »", async () => {
        m.liste.mockResolvedValue({ data: { tests: [] } });
        render(<PageTests workflowId={42} />);
        expect((await screen.findByTestId("aucun-test")).textContent).toContain("No test");
        expect((screen.getByRole("button", { name: /Play all/ }) as HTMLButtonElement).disabled).toBe(true);
    });

    it("montre l'erreur du serveur telle qu'elle vient", async () => {
        m.liste.mockResolvedValue({ error: { detail: "Workflow not found" } });
        render(<PageTests workflowId={42} />);
        expect((await screen.findByRole("alert")).textContent).toBe("Workflow not found");
    });
});

describe("« Tout jouer »", () => {
    it("rejoue la suite entière avec le nombre d'essais et montre la raison, la réplique fautive et le diagnostic", async () => {
        render(<PageTests workflowId={42} />);
        await screen.findByText("Numéro dit");
        ouvrir(/More ways to play/);
        fireEvent.click(await screen.findByRole("menuitem", { name: "The whole suite" }));
        const echec = await screen.findByTestId("echec-de-la-suite");
        expect(m.rejouer).toHaveBeenCalledWith({ path: { workflow_id: 42 }, body: { repetitions: 3 } });
        expect(echec.textContent).toContain("Je lance outil_interne.");
        expect(screen.getByTestId("diagnostic").textContent).toContain("Nothing is changed without your agreement");
        expect(screen.getByTestId("resultat-de-la-suite").textContent).toContain("Refused: a required test fails");
        await waitFor(() => expect(m.liste.mock.calls.length).toBeGreaterThan(1));
    });

    it("rejoue la sélection cochée, puis les obligatoires", async () => {
        render(<PageTests workflowId={42} />);
        await screen.findByText("Numéro dit");
        fireEvent.click(screen.getByRole("checkbox", { name: /Appelant pressé/ }));
        fireEvent.click(screen.getByRole("button", { name: /Play the selection \(1\)/ }));
        await waitFor(() => expect(m.rejouer).toHaveBeenCalledWith({ path: { workflow_id: 42 }, body: { repetitions: 3, tests: ["libre"] } }));
        ouvrir(/More ways to play/);
        fireEvent.click(await screen.findByRole("menuitem", { name: /Play the required tests/ }));
        await waitFor(() => expect(m.rejouer).toHaveBeenLastCalledWith({ path: { workflow_id: 42 }, body: { repetitions: 3, tests: ["numero-dit"] } }));
    });
});

describe("la fenêtre d'un test", () => {
    const nouveau = async () => {
        render(<PageTests workflowId={42} />);
        await screen.findByText("Numéro dit");
        ouvrir(/Add a test/);
        fireEvent.click(await screen.findByRole("menuitem", { name: "Create a test" }));
        return await screen.findByTestId("fenetre-de-test");
    };

    it("crée une conversation simulée avec un personnage de la bibliothèque, puis la joue", async () => {
        const fenetre = await nouveau();
        fireEvent.change(within(fenetre).getByLabelText("Test name"), { target: { value: "Pressé" } });
        fireEvent.change(within(fenetre).getByLabelText("Scenario"), { target: { value: "Veut un rendez-vous." } });
        fireEvent.change(within(fenetre).getByLabelText("Text"), { target: { value: "outil_interne" } });
        fireEvent.click(within(fenetre).getByRole("button", { name: "Create and play" }));
        await waitFor(() => expect(m.creer).toHaveBeenCalled());
        const corps = m.creer.mock.calls[0][0].body;
        expect(corps).toMatchObject({ nom: "Pressé", scenario: "Veut un rendez-vous.", criteres: [{ type: "texte_absent", texte: "outil_interne" }], origine: "manuel" });
        expect(corps.replique).toBeUndefined();
        await waitFor(() => expect(m.rejouer).toHaveBeenCalledWith({ path: { workflow_id: 42 }, body: { tests: ["nouveau"], repetitions: 3 } }));
    });

    it("crée une réplique suivante avec son historique, et un appel d'outil dont la liste vient de l'agent", async () => {
        const fenetre = await nouveau();
        fireEvent.click(within(fenetre).getByRole("button", { name: "Next reply" }));
        fireEvent.change(within(fenetre).getByLabelText("Test name"), { target: { value: "Suite" } });
        fireEvent.click(within(fenetre).getByRole("button", { name: "Agent turn" }));
        fireEvent.change(within(fenetre).getByLabelText("Turn 1"), { target: { value: "Bonjour" } });
        fireEvent.change(within(fenetre).getByLabelText("Reply"), { target: { value: "Je veux un devis." } });
        fireEvent.change(within(fenetre).getByLabelText("Text"), { target: { value: "devis" } });
        fireEvent.click(within(fenetre).getByRole("button", { name: "Create" }));
        await waitFor(() => expect(m.creer).toHaveBeenCalled());
        expect(m.creer.mock.calls[0][0].body).toMatchObject({ replique: "Je veux un devis.", historique: [{ role: "assistant", texte: "Bonjour" }] });
        expect(m.creer.mock.calls[0][0].body.scenario).toBeUndefined();
    });

    it("l'appel d'outil n'offre que le critère outil, et ne propose pas l'ancien « merci »", async () => {
        const fenetre = await nouveau();
        fireEvent.click(within(fenetre).getByRole("button", { name: "Tool call" }));
        expect(within(fenetre).getByText("A tool is called")).toBeTruthy();
        expect(within(fenetre).queryByText(/Merci/)).toBeNull();
    });

    it("rouvre un test existant, le modifie par la route de modification et ne perd pas l'ancien critère « merci »", async () => {
        render(<PageTests workflowId={42} />);
        fireEvent.click(await screen.findByText("Numéro dit"));
        const fenetre = await screen.findByTestId("fenetre-de-test");
        expect((within(fenetre).getByLabelText("Test name") as HTMLInputElement).value).toBe("Numéro dit");
        expect((within(fenetre).getByLabelText("Reply") as HTMLTextAreaElement).value).toBe("Bonjour");
        expect(within(fenetre).getByText(/starting with « Merci »/)).toBeTruthy();
        fireEvent.change(within(fenetre).getByLabelText("Reply"), { target: { value: "Bonsoir" } });
        fireEvent.click(within(fenetre).getByRole("button", { name: "Save" }));
        await waitFor(() => expect(m.changer).toHaveBeenCalled());
        const appel = m.changer.mock.calls[0][0];
        expect(appel.path).toEqual({ workflow_id: 42, slug: "numero-dit" });
        expect(appel.body).toMatchObject({ replique: "Bonsoir", obligatoire: true, dossier: "Sécurité" });
        expect(appel.body.criteres).toHaveLength(2);
        expect(m.creer).not.toHaveBeenCalled();
    });

    it("supprime un test depuis sa fenêtre", async () => {
        render(<PageTests workflowId={42} />);
        fireEvent.click(await screen.findByText("Numéro dit"));
        const fenetre = await screen.findByTestId("fenetre-de-test");
        fireEvent.click(within(fenetre).getByRole("button", { name: "Delete" }));
        // K3 (maquette) : un geste sûr, on demande confirmation avant de supprimer.
        expect(m.supprimer).not.toHaveBeenCalled();
        fireEvent.click(within(fenetre).getByRole("button", { name: "Delete" }));
        await waitFor(() => expect(m.supprimer).toHaveBeenCalledWith({ path: { workflow_id: 42, slug: "numero-dit" } }));
    });

    it("lit la sorte d'un test enregistré", () => {
        expect(sorteDuTest({ scenario: { but: "x" }, criteres: [] })).toBe("conversation");
        expect(sorteDuTest({ criteres: [{ type: "outil" }] })).toBe("outil");
        expect(sorteDuTest({ criteres: [{ type: "texte_absent" }] })).toBe("replique");
    });
});

describe("« Depuis la bibliothèque »", () => {
    const ouvrirLaBibliotheque = async () => {
        render(<PageTests workflowId={42} />);
        await screen.findByText("Numéro dit");
        ouvrir(/Add a test/);
        fireEvent.click(await screen.findByRole("menuitem", { name: "From the library" }));
        return await screen.findByTestId("depuis-la-bibliotheque");
    };

    it("dit ce qui manque à l'agent avant de copier, puis copie quand même sur demande", async () => {
        const fenetre = await ouvrirLaBibliotheque();
        fireEvent.click(within(fenetre).getByText("Capture simple"));
        const bilan = await within(fenetre).findByTestId("bilan-du-scenario");
        expect(bilan.textContent).toContain("chercher_un_creneau");
        expect(m.examiner).toHaveBeenCalledWith({ path: { slug: "capture-simple" }, body: { workflow_id: 42 } });
        expect(m.copier).not.toHaveBeenCalled();
        fireEvent.click(within(fenetre).getByRole("button", { name: "Copy anyway" }));
        await waitFor(() => expect(m.copier).toHaveBeenCalledWith({ path: { slug: "capture-simple" }, body: { workflow_id: 42, copier_quand_meme: true } }));
    });

    it("copie sans insister quand l'agent a tout", async () => {
        m.examiner.mockResolvedValue({ data: { titre: "Capture simple", but: null, personnage_absent: false, absents: [] } });
        const fenetre = await ouvrirLaBibliotheque();
        fireEvent.click(within(fenetre).getByText("Capture simple"));
        await within(fenetre).findByTestId("bilan-du-scenario");
        fireEvent.click(within(fenetre).getByRole("button", { name: "Copy as a test" }));
        await waitFor(() => expect(m.copier).toHaveBeenCalledWith({ path: { slug: "capture-simple" }, body: { workflow_id: 42, copier_quand_meme: false } }));
    });
});

describe("ce qui est gardé de la page d'avant", () => {
    it("écrit la raison sous la réplique fautive, pas ailleurs", async () => {
        render(<PageTests workflowId={42} />);
        fireEvent.click(await screen.findByText("2/3"));
        await screen.findByTestId("detail-du-test");
        fireEvent.click(screen.getByRole("button", { name: /Attempt 2/ }));
        const conversation = await screen.findByTestId("conversation-du-test");
        const fautives = conversation.querySelectorAll("[data-faute]");
        expect(fautives).toHaveLength(1);
        expect(within(fautives[0] as HTMLElement).getByTestId("raison-de-l-echec").textContent).toContain("which it must not");
        expect(fautesDeLaReplique(DETAIL.resultats[0].essais[1].criteres as never, 0)).toHaveLength(0);
        expect(fautesDeLaReplique(DETAIL.resultats[0].essais[1].criteres as never, 1)).toHaveLength(1);
    });

    it("garde l'avis du juge à part, et le noter appelle la calibration", async () => {
        render(<PageTests workflowId={42} />);
        fireEvent.click(await screen.findByText("2/3"));
        const juge = await screen.findByTestId("avis-du-juge");
        expect(juge.textContent).toContain("blocks nothing");
        fireEvent.click(within(juge).getByRole("button", { name: /I agree/ }));
        await waitFor(() => expect(m.note).toHaveBeenCalledWith({ path: { workflow_id: 42 }, body: { identifiant: "numero-dit:2026-10-31T10:00:00+00:00:0", ok: true } }));
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
        Object.assign(URL, { createObjectURL: vi.fn(() => "blob:test"), revokeObjectURL: vi.fn() });
        const clic = vi.spyOn(HTMLAnchorElement.prototype, "click").mockImplementation(() => undefined);
        render(<PageTests workflowId={42} />);
        await screen.findByText("Numéro dit");
        fireEvent.click(screen.getByRole("button", { name: /Export for the lab/ }));
        await waitFor(() => expect(clic).toHaveBeenCalled());
        expect(m.exporter).toHaveBeenCalledWith({ path: { workflow_id: 42 } });
        clic.mockRestore();
    });
});
