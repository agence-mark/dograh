/**
 * [.mark] Partie 3, sous-lot 5 (SE-11, C-3): l'onglet Environnement d'un test, les critères « dans cet ordre » et « une seule fois »,
 * « Ajouter un test › Depuis une conversation entière ».
 *
 * Questions de ce fichier :
 *
 *     La fenêtre d'un test a-t-elle un onglet Environnement qui envoie date, heure, numéro, variables et réponses d'outils
 *     simulées (dans l'ordre des appels) au serveur ? Un test dont on vide l'environnement l'envoie-t-il vide (le serveur le
 *     retire) ? L'environnement du serveur fait-il l'aller-retour du formulaire ? Les deux critères s'ajoutent-ils et partent-ils
 *     dans la forme que le code attend ? La page d'un appel crée-t-elle un test depuis la conversation entière, et le menu
 *     « Ajouter un test » l'offre-t-il ?
 */
import { cleanup, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { BoutonCreerUnTest } from "./BoutonCreerUnTest";
import { environnementEdite, environnementPourLeServeur, environnementVide } from "./EnvironnementDuTest";
import { critereDeLaLigne } from "./NouveauTest";
import { PageTests } from "./PageTests";
import type { EnvironnementServeur, ResumeDeTest } from "./types";

vi.mock("next/navigation", () => ({ useRouter: () => ({ push: vi.fn() }), usePathname: () => "/agents/42/tests" }));

/** Un menu Radix s'ouvre au pointeur, pas au clic. */
function ouvrir(nom: RegExp) {
    fireEvent.pointerDown(screen.getByRole("button", { name: nom }), { button: 0, ctrlKey: false });
}

const m = vi.hoisted(() => ({
    liste: vi.fn(),
    publication: vi.fn(),
    corrections: vi.fn(),
    passees: vi.fn(),
    ressources: vi.fn(),
    test: vi.fn(),
    changer: vi.fn(),
    creer: vi.fn(),
    entiere: vi.fn(),
}));

vi.mock("@/components/mark/studio/liste-deroulante", async () => await import("@/components/mark/studio/liste-deroulante-natif-test"));
vi.mock("@/client", () => ({
    lireLesTestsApiV1BuilderTestsWorkflowIdGet: (o: unknown) => m.liste(o),
    etatDeLaPublicationApiV1BuilderTestsWorkflowIdPublicationGet: (o: unknown) => m.publication(o),
    historiqueDesCorrectionsApiV1BuilderTestsWorkflowIdCorrectionsGet: (o: unknown) => m.corrections(o),
    executionsPasseesApiV1BuilderTestsWorkflowIdExecutionsGet: (o: unknown) => m.passees(o),
    ressourcesDeLAgentApiV1BuilderTestsWorkflowIdRessourcesGet: (o: unknown) => m.ressources(o),
    lireUnTestApiV1BuilderTestsWorkflowIdSlugGet: (o: unknown) => m.test(o),
    changerUnTestApiV1BuilderTestsWorkflowIdSlugPatch: (o: unknown) => m.changer(o),
    creerUnTestApiV1BuilderTestsWorkflowIdPost: (o: unknown) => m.creer(o),
    creerDepuisUneConversationApiV1BuilderTestsWorkflowIdDepuisUneConversationPost: (o: unknown) => m.entiere(o),
    rejouerLaSuiteApiV1BuilderTestsWorkflowIdRejouerPost: vi.fn(),
}));

const TESTS: ResumeDeTest[] = [
    { slug: "avec-env", nom: "Avec environnement", obligatoire: false, dossier: "", origine: "manuel", genre: "conversation", criteres: 1, avec_environnement: true, derniere: null },
];
const ENVIRONNEMENT: EnvironnementServeur = {
    date: "2026-11-08",
    heure: "19:40",
    numero: "06 39 98 00 01",
    masque: false,
    variables: { etablissement: "Beauvais" },
    simulations: [{ outil: "chercher_un_creneau", appels: [{ sorte: "delai", corps: null }, { sorte: "reponse", corps: { creneaux: ["lundi 9 h"] } }] }],
};
const DETAIL = {
    test: { slug: "avec-env", nom: "Avec environnement", obligatoire: false, dossier: "", origine: "manuel", criteres: [{ type: "sans_rigidite" }], scenario: { but: "Veut un rendez-vous." }, environnement: ENVIRONNEMENT },
    resultats: [],
};
const RESSOURCES = { etapes: ["Accueil"], outils: ["chercher_un_creneau", "noter"], issues: [], champs: [], personnages: [], scenarios_types: [] };

beforeEach(() => {
    m.liste.mockResolvedValue({ data: { tests: TESTS } });
    m.publication.mockResolvedValue({ data: { brouillon: true, bloque: false, controle: null, tests_obligatoires: [] } });
    m.corrections.mockResolvedValue({ data: { corrections: [] } });
    m.passees.mockResolvedValue({ data: { executions: [] } });
    m.ressources.mockResolvedValue({ data: RESSOURCES });
    m.test.mockResolvedValue({ data: DETAIL });
    m.changer.mockResolvedValue({ data: {} });
    m.creer.mockResolvedValue({ data: { ok: true, test: { slug: "nouveau" } } });
    m.entiere.mockResolvedValue({ data: { test: { slug: "entier" } } });
});
afterEach(() => {
    cleanup();
    vi.clearAllMocks();
});

describe("le formulaire de l'environnement", () => {
    it("fait l'aller-retour avec la forme du serveur, et un formulaire vide donne un objet vide", () => {
        const edite = environnementEdite(ENVIRONNEMENT);
        expect(edite.variables).toEqual([["etablissement", "Beauvais"]]);
        expect(edite.simulations[0].appels).toEqual([{ sorte: "delai", corps: "" }, { sorte: "reponse", corps: '{"creneaux":["lundi 9 h"]}' }]);
        expect(environnementPourLeServeur(edite)).toEqual({
            date: "2026-11-08",
            heure: "19:40",
            numero: "06 39 98 00 01",
            variables: { etablissement: "Beauvais" },
            simulations: [{ outil: "chercher_un_creneau", appels: [{ sorte: "delai" }, { sorte: "reponse", corps: '{"creneaux":["lundi 9 h"]}' }] }],
        });
        expect(environnementPourLeServeur(environnementVide())).toEqual({});
        expect(environnementPourLeServeur({ ...environnementVide(), numero: "06 39 98 00 01", masque: true })).toEqual({ masque: true });
    });
});

describe("l'onglet Environnement de la fenêtre d'un test", () => {
    const nouveau = async () => {
        render(<PageTests workflowId={42} />);
        await screen.findByText("Avec environnement");
        ouvrir(/Add a test/);
        fireEvent.click(await screen.findByRole("menuitem", { name: "Create a test" }));
        return await screen.findByTestId("fenetre-de-test");
    };

    it("envoie date, heure, numéro, variables et réponses d'outils en série à la création", async () => {
        const fenetre = await nouveau();
        fireEvent.change(within(fenetre).getByLabelText("Test name"), { target: { value: "Panne" } });
        fireEvent.change(within(fenetre).getByLabelText("Scenario"), { target: { value: "Veut un rendez-vous." } });
        fireEvent.change(within(fenetre).getByLabelText("Text"), { target: { value: "outil_interne" } });
        fireEvent.click(within(fenetre).getByRole("button", { name: "Environment" }));
        const env = await within(fenetre).findByTestId("environnement-du-test");
        fireEvent.change(within(env).getByLabelText("Date"), { target: { value: "2026-11-08" } });
        fireEvent.change(within(env).getByLabelText("Time"), { target: { value: "19:40" } });
        fireEvent.change(within(env).getByLabelText("Caller's number"), { target: { value: "06 39 98 00 01" } });
        fireEvent.click(within(env).getByRole("button", { name: "Add a variable" }));
        fireEvent.change(within(env).getByLabelText("Variable name"), { target: { value: "etablissement" } });
        fireEvent.change(within(env).getByLabelText("Value"), { target: { value: "Beauvais" } });
        fireEvent.click(within(env).getByRole("button", { name: "Simulate a tool" }));
        fireEvent.click(within(env).getByRole("button", { name: "Next call" }));
        fireEvent.change(within(env).getAllByLabelText("JSON answer")[1], { target: { value: '{"ok": true}' } });
        fireEvent.click(within(fenetre).getByRole("button", { name: "Create" }));
        await waitFor(() => expect(m.creer).toHaveBeenCalled());
        expect(m.creer.mock.calls[0][0].body.environnement).toEqual({
            date: "2026-11-08",
            heure: "19:40",
            numero: "06 39 98 00 01",
            variables: { etablissement: "Beauvais" },
            simulations: [{ outil: "chercher_un_creneau", appels: [{ sorte: "reponse", corps: "{}" }, { sorte: "reponse", corps: '{"ok": true}' }] }],
        });
    });

    it("rouvre l'environnement d'un test, et le vider l'envoie vide à la modification (le serveur le retire)", async () => {
        render(<PageTests workflowId={42} />);
        fireEvent.click(await screen.findByText("Avec environnement"));
        const fenetre = await screen.findByTestId("fenetre-de-test");
        fireEvent.click(within(fenetre).getByRole("button", { name: "Environment" }));
        const env = await within(fenetre).findByTestId("environnement-du-test");
        expect((within(env).getByLabelText("Date") as HTMLInputElement).value).toBe("2026-11-08");
        expect((within(env).getByLabelText("Caller's number") as HTMLInputElement).value).toBe("06 39 98 00 01");
        expect((within(env).getByLabelText("JSON answer") as HTMLTextAreaElement).value).toBe('{"creneaux":["lundi 9 h"]}');
        fireEvent.click(within(env).getByRole("button", { name: "Remove the simulation" }));
        fireEvent.click(within(env).getByRole("button", { name: "Remove the variable" }));
        fireEvent.change(within(env).getByLabelText("Date"), { target: { value: "" } });
        fireEvent.change(within(env).getByLabelText("Caller's number"), { target: { value: "" } });
        fireEvent.click(within(fenetre).getByRole("button", { name: "Save" }));
        await waitFor(() => expect(m.changer).toHaveBeenCalled());
        expect(m.changer.mock.calls[0][0].body.environnement).toEqual({});
    });

    it("« Masqué » vide le numéro et part comme masque", async () => {
        render(<PageTests workflowId={42} />);
        fireEvent.click(await screen.findByText("Avec environnement"));
        const fenetre = await screen.findByTestId("fenetre-de-test");
        fireEvent.click(within(fenetre).getByRole("button", { name: "Environment" }));
        const env = await within(fenetre).findByTestId("environnement-du-test");
        fireEvent.click(within(env).getByRole("switch", { name: "Withheld" }));
        expect((within(env).getByLabelText("Caller's number") as HTMLInputElement).disabled).toBe(true);
        fireEvent.click(within(fenetre).getByRole("button", { name: "Save" }));
        await waitFor(() => expect(m.changer).toHaveBeenCalled());
        expect(m.changer.mock.calls[0][0].body.environnement).toMatchObject({ masque: true });
        expect(m.changer.mock.calls[0][0].body.environnement.numero).toBeUndefined();
    });
});

describe("les critères « dans cet ordre » et « une seule fois »", () => {
    it("s'ajoutent depuis la liste et partent dans la forme du serveur", async () => {
        render(<PageTests workflowId={42} />);
        await screen.findByText("Avec environnement");
        ouvrir(/Add a test/);
        fireEvent.click(await screen.findByRole("menuitem", { name: "Create a test" }));
        const fenetre = await screen.findByTestId("fenetre-de-test");
        fireEvent.change(within(fenetre).getByLabelText("Test name"), { target: { value: "Ordre" } });
        fireEvent.change(within(fenetre).getByLabelText("Scenario"), { target: { value: "Veut un rendez-vous." } });
        ouvrir(/Add a criterion/);
        fireEvent.click(await screen.findByRole("menuitem", { name: "The tools are called in this order" }));
        const ordre = within(fenetre).getByTestId("ordre-des-outils");
        expect(within(ordre).getAllByRole("listitem").length).toBeGreaterThanOrEqual(3); // deux outils et « Outil suivant »
        ouvrir(/Add a criterion/);
        fireEvent.click(await screen.findByRole("menuitem", { name: "A tool is called exactly once" }));
        expect(within(fenetre).getByText("A tool is called exactly once")).toBeTruthy();
    });

    it("critereDeLaLigne écrit noms (dans l'ordre) et nom (une seule fois)", () => {
        expect(critereDeLaLigne({ type: "outils_dans_l_ordre", valeurs: { noms: "chercher, ,reserver, " } })).toEqual({ type: "outils_dans_l_ordre", noms: ["chercher", "reserver"] });
        expect(critereDeLaLigne({ type: "outil_une_seule_fois", valeurs: { nom: " envoyer_sms " } })).toEqual({ type: "outil_une_seule_fois", nom: "envoyer_sms" });
    });
});

describe("« Ajouter un test › Depuis une conversation entière »", () => {
    it("le menu de l'onglet Tests l'offre, vers les appels de l'agent", async () => {
        render(<PageTests workflowId={42} />);
        await screen.findByText("Avec environnement");
        ouvrir(/Add a test/);
        const item = await screen.findByRole("menuitem", { name: "From a whole conversation" });
        expect(item.getAttribute("href")).toContain("/runs");
    });

    const EVENEMENTS = [{ type: "rtf-user-transcription", payload: { final: true, text: "Je voudrais un devis" } }];

    it("la page d'un appel crée le test de la conversation entière avec le run, sans rang", async () => {
        render(<BoutonCreerUnTest workflowId={42} runId={9} evenements={EVENEMENTS} />);
        fireEvent.click(screen.getByRole("button", { name: /from the whole conversation/ }));
        const bouton = screen.getByRole("button", { name: "Create the test" });
        expect((bouton as HTMLButtonElement).disabled).toBe(true);
        fireEvent.change(screen.getByLabelText("Test name"), { target: { value: "Appel entier" } });
        fireEvent.click(bouton);
        await waitFor(() => expect(m.entiere).toHaveBeenCalledWith({ path: { workflow_id: 42 }, body: { run_id: 9, nom: "Appel entier" } }));
        expect((await screen.findByTestId("test-cree")).textContent).toContain("Test created");
    });

    it("dit pourquoi si le serveur refuse, sans texte brut", async () => {
        m.entiere.mockResolvedValue({ error: { detail: "Nothing to check in this call (no outcome, no tool): add a criterion." } });
        render(<BoutonCreerUnTest workflowId={42} runId={9} evenements={EVENEMENTS} />);
        fireEvent.click(screen.getByRole("button", { name: /from the whole conversation/ }));
        fireEvent.change(screen.getByLabelText("Test name"), { target: { value: "x" } });
        fireEvent.click(screen.getByRole("button", { name: "Create the test" }));
        expect((await screen.findByRole("alert")).textContent).not.toBe("");
        expect(screen.queryByTestId("test-cree")).toBeNull();
    });
});
