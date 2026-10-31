/**
 * [.mark] builder-agent-vocal (lot 4): the stream, the store, the settings, the panel and the top bar.
 *
 * Questions of this file:
 *
 *     Is the stream cut into events whatever the chunks? Do the events become the parts of an assistant message, and
 *     do the construction operations reach the screen's state the first time with a snapshot of the graph from before?
 *     Is the builder's key written, never read back or shown? Does the panel draw the cards of the actions of a streamed
 *     answer (and a line of the checklist for the others), say that an action is not available yet, and does the
 *     « Changes » card hold Accept and Refuse until the draft is saved? Are « Builder AI » and « Tests » in the top bar,
 *     and « Publish » greyed with its reason?
 */
import { cleanup, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { appliquerLEvenement } from "./adaptateur";
import { BarreDuBuilder } from "./BarreDuBuilder";
import { ajouterAuxParties, type EvenementDuBuilder, lireLeFlux, lireUnBloc } from "./flux";
import type { GrapheDuBuilder } from "./graphe";
import { PanneauBuilder } from "./PanneauBuilder";
import { ReglagesDuBuilder } from "./ReglagesDuBuilder";
import { useBuilderEcran } from "./store";

const m = vi.hoisted(() => ({
    parler: vi.fn(),
    historique: vi.fn(),
    contexte: vi.fn(),
    cerveauLire: vi.fn(),
    cerveauEcrire: vi.fn(),
    prefsLire: vi.fn(),
    prefsEcrire: vi.fn(),
    versions: vi.fn(),
}));

vi.mock("@/client", () => ({
    parlerAuBuilderApiV1BuilderConversationPost: (...a: unknown[]) => m.parler(...a),
    lireLaConversationApiV1BuilderConversationWorkflowIdGet: (...a: unknown[]) => m.historique(...a),
    lireLeContexteApiV1BuilderContexteWorkflowIdGet: (...a: unknown[]) => m.contexte(...a),
    lireLeCerveauApiV1BuilderCerveauGet: (...a: unknown[]) => m.cerveauLire(...a),
    reglerLeCerveauApiV1BuilderCerveauPut: (...a: unknown[]) => m.cerveauEcrire(...a),
    lireLesPreferencesApiV1BuilderPreferencesGet: (...a: unknown[]) => m.prefsLire(...a),
    ecrireLesPreferencesApiV1BuilderPreferencesPut: (...a: unknown[]) => m.prefsEcrire(...a),
    getWorkflowVersionsApiV1WorkflowWorkflowIdVersionsGet: (...a: unknown[]) => m.versions(...a),
    lireLaConceptionApiV1BuilderConceptionWorkflowIdGet: vi.fn().mockResolvedValue({ data: { conception: null } }),
    deposerUnFichierApiV1BuilderDepotWorkflowIdPost: vi.fn(),
    deposerUnSiteApiV1BuilderDepotWorkflowIdSitePost: vi.fn(),
    retirerUnDepotApiV1BuilderDepotWorkflowIdDepotIdDelete: vi.fn(),
    ecrireUneLigneDeLaFicheApiV1BuilderFicheWorkflowIdLignePut: vi.fn(),
    validerLaFicheApiV1BuilderFicheWorkflowIdValiderPost: vi.fn(),
    validerUnDocumentDeBaseApiV1BuilderBaseWorkflowIdDocumentIdValiderPost: vi.fn(),
    rejeterUnDocumentDeBaseApiV1BuilderBaseWorkflowIdDocumentIdRejeterPost: vi.fn(),
    deciderDeLaConceptionApiV1BuilderConceptionWorkflowIdDecisionPost: vi.fn(),
}));

vi.mock("sonner", () => ({ toast: { success: vi.fn(), error: vi.fn(), message: vi.fn() } }));
vi.mock("next/link", () => ({ default: ({ children, href, ...r }: { children: React.ReactNode; href: string }) => <a href={href} {...r}>{children}</a> }));
vi.mock("@/app/workflow/[workflowId]/components/WorkflowVersionDiffDialog", () => ({
    WorkflowVersionDiffDialog: () => <div data-testid="comparatif" />,
}));

function fluxDe(evenements: EvenementDuBuilder[]): ReadableStream<Uint8Array> {
    const codeur = new TextEncoder();
    return new ReadableStream({
        start(controle) {
            for (const e of evenements) controle.enqueue(codeur.encode(`data: ${JSON.stringify(e)}\n\n`));
            controle.close();
        },
    });
}

const GRAPHE: GrapheDuBuilder = {
    nodes: [{ id: "1", type: "startCall", position: { x: 0, y: 0 }, data: { name: "Départ", prompt: "p" } }] as never,
    edges: [],
};

// jsdom has neither; assistant-ui's viewport watches the size of its content.
class ObservateurFactice {
    observe() {}
    unobserve() {}
    disconnect() {}
}
vi.stubGlobal("ResizeObserver", ObservateurFactice);
vi.stubGlobal("IntersectionObserver", ObservateurFactice);
Element.prototype.scrollTo = Element.prototype.scrollTo ?? (() => {});
Element.prototype.scrollIntoView = Element.prototype.scrollIntoView ?? (() => {});

beforeEach(() => {
    Object.values(m).forEach((f) => f.mockReset());
    useBuilderEcran.getState().reinitialiser();
    m.historique.mockResolvedValue({ data: { messages: [], resume: "", depense: {}, en_cours: false } });
    m.contexte.mockResolvedValue({ data: { depots: [], fiche: { champs: {}, trous: [] }, classements: {}, base: [] } });
    m.cerveauLire.mockResolvedValue({ data: { format: "anthropic", modele: "modele-x", cle_posee: true, plafond_depense: 2, plafond_jetons: 1500000 } });
    m.prefsLire.mockResolvedValue({ data: { texte: "" } });
});
afterEach(cleanup);

describe("le flux du builder", () => {
    it("coupe le flux en événements, même quand un morceau arrive coupé en deux", async () => {
        const texte = `data: ${JSON.stringify({ type: "texte", texte: "Bon" })}\n\ndata: ${JSON.stringify({ type: "fin", raison: "fin" })}\n\n`;
        const octets = new TextEncoder().encode(texte);
        const flux = new ReadableStream<Uint8Array>({
            start(c) {
                c.enqueue(octets.slice(0, 20));
                c.enqueue(octets.slice(20, 60));
                c.enqueue(octets.slice(60));
                c.close();
            },
        });
        const lus: EvenementDuBuilder[] = [];
        for await (const e of lireLeFlux(flux)) lus.push(e);
        expect(lus.map((e) => e.type)).toEqual(["texte", "fin"]);
    });

    it("ignore une ligne illisible sans faire tomber la conversation", () => {
        expect(lireUnBloc("data: {pas du json")).toBeNull();
        expect(lireUnBloc(": commentaire")).toBeNull();
        expect(lireUnBloc('data: {"type":"fin","raison":"x"}')).toEqual({ type: "fin", raison: "x" });
    });

    it("assemble le texte, une action par carte et son résultat", () => {
        let parties = ajouterAuxParties([], { type: "texte", texte: "Je " });
        parties = ajouterAuxParties(parties, { type: "texte", texte: "lis." });
        parties = ajouterAuxParties(parties, { type: "action", id: "a1", nom: "fiche_ecrire", arguments: { x: 1 } });
        parties = ajouterAuxParties(parties, { type: "resultat", id: "a1", nom: "fiche_ecrire", ok: false, resultat: { erreur: "non" } });
        expect(parties).toEqual([
            { type: "text", text: "Je lis." },
            { type: "tool-call", toolCallId: "a1", toolName: "fiche_ecrire", args: { x: 1 }, argsText: '{"x":1}', result: { erreur: "non" }, isError: true },
        ]);
    });
});

describe("l'état de l'écran", () => {
    const options = { workflowId: 5, lireLeGraphe: () => GRAPHE, recharger: vi.fn().mockResolvedValue(true), echec: "x" };

    it("la première opération garde le graphe d'avant, les suivantes s'ajoutent sans l'écraser", async () => {
        await appliquerLEvenement({ type: "operation", operation: { op: "ajouter_noeud", id: "2", type: "endCall", nom: "Fin" } }, options);
        const autre: GrapheDuBuilder = { nodes: [...GRAPHE.nodes, GRAPHE.nodes[0]] as never, edges: [] };
        await appliquerLEvenement({ type: "operation", operation: { op: "supprimer_noeud", id: "2" } }, { ...options, lireLeGraphe: () => autre });
        const s = useBuilderEcran.getState();
        expect(s.avant).toBe(GRAPHE);
        expect(s.operationsVives).toHaveLength(2);
        expect(s.bascule).toBe("apres");
    });

    it("l'enregistrement du brouillon relit le graphe du serveur et garde la relecture", async () => {
        const recharger = vi.fn().mockResolvedValue(true);
        await appliquerLEvenement({ type: "operation", operation: { op: "supprimer_noeud", id: "1" } }, { ...options, recharger });
        await appliquerLEvenement(
            { type: "carte", carte: { type: "changements", version: 3, nombre_operations: 1, noeuds: 2, liaisons: 1 } },
            { ...options, recharger },
        );
        const s = useBuilderEcran.getState();
        expect(recharger).toHaveBeenCalledTimes(1);
        expect(s.operationsVives).toEqual([]); // elles font désormais partie du graphe enregistré
        expect(s.avant).toBe(GRAPHE); // et la relecture reste ouverte
        expect(s.changements).toMatchObject({ version: 3, nombreOperations: 1 });
    });

    it("un résultat d'action relit le contexte (dépôts, fiche, base)", async () => {
        await appliquerLEvenement({ type: "resultat", id: "a", nom: "fiche_ecrire", ok: true, resultat: {} }, options);
        expect(m.contexte).toHaveBeenCalledWith({ path: { workflow_id: 5 } });
    });

    it("Accepter ou Refuser soldent la relecture", () => {
        useBuilderEcran.getState().recevoirUneOperation({ op: "supprimer_noeud", id: "1" }, GRAPHE);
        useBuilderEcran.getState().solderLesChangements();
        expect(useBuilderEcran.getState()).toMatchObject({ avant: null, operationsVives: [], changements: null });
    });
});

describe("les réglages du builder", () => {
    it("la clé s'écrit, ne se relit jamais, et un champ vide garde la clé enregistrée", async () => {
        m.cerveauLire.mockResolvedValue({ data: { format: "openai", modele: "gpt-x", adresse: "", cle_posee: true, plafond_depense: 2, plafond_jetons: 1000000 } });
        m.cerveauEcrire.mockResolvedValue({ data: { format: "openai", modele: "gpt-y", cle_posee: true } });
        m.prefsEcrire.mockResolvedValue({ data: {} });
        render(<ReglagesDuBuilder ouvert onOuvertChange={vi.fn()} />);
        const cle = (await screen.findByLabelText("Key")) as HTMLInputElement;
        await waitFor(() => expect((screen.getByLabelText("Model") as HTMLInputElement).value).toBe("gpt-x"));
        expect(cle.value).toBe("");
        expect(cle.type).toBe("password");
        expect(document.querySelector("[data-cle-posee]")?.getAttribute("data-cle-posee")).toBe("oui");
        fireEvent.change(screen.getByLabelText("Model"), { target: { value: "gpt-y" } });
        fireEvent.click(screen.getByRole("button", { name: "Save" }));
        await waitFor(() => expect(m.cerveauEcrire).toHaveBeenCalled());
        expect(m.cerveauEcrire.mock.calls[0][0].body).toMatchObject({ format: "openai", modele: "gpt-y", cle: null });
        // Une nouvelle clé part, puis le champ se vide.
        fireEvent.change(cle, { target: { value: "cle-factice-0123456789" } });
        fireEvent.click(screen.getByRole("button", { name: "Save" }));
        await waitFor(() => expect(m.cerveauEcrire).toHaveBeenCalledTimes(2));
        expect(m.cerveauEcrire.mock.calls[1][0].body.cle).toBe("cle-factice-0123456789");
        await waitFor(() => expect((screen.getByLabelText("Key") as HTMLInputElement).value).toBe(""));
        expect(document.body.innerHTML).not.toContain("cle-factice-0123456789");
    });

    it("montre le refus du serveur (réservé à l'équipe) sans écrire les préférences", async () => {
        m.cerveauEcrire.mockResolvedValue({ error: { detail: "Reserved to the .mark team" } });
        render(<ReglagesDuBuilder ouvert onOuvertChange={vi.fn()} />);
        await waitFor(() => expect((screen.getByLabelText("Model") as HTMLInputElement).value).toBe("modele-x"));
        fireEvent.click(screen.getByRole("button", { name: "Save" }));
        expect((await screen.findByRole("alert")).textContent).toContain("Reserved to the .mark team");
        expect(m.prefsEcrire).not.toHaveBeenCalled();
    });
});

describe("le panneau « Builder IA »", () => {
    const contexteDuPanneau = () => ({
        workflowId: 5,
        lireLeGraphe: () => GRAPHE,
        recharger: vi.fn().mockResolvedValue(true),
        restaurer: vi.fn().mockResolvedValue(true),
        appelerLAgent: vi.fn(),
        essayerAuClavier: vi.fn(),
    });

    async function envoyer(evenements: EvenementDuBuilder[], message = "lis les documents") {
        m.parler.mockResolvedValue({ data: fluxDe(evenements) });
        const contexte = contexteDuPanneau();
        render(<PanneauBuilder contexte={contexte} noeuds={GRAPHE.nodes} />);
        const zone = (await screen.findByLabelText("Write to the builder...")) as HTMLTextAreaElement;
        fireEvent.change(zone, { target: { value: message } });
        fireEvent.click(screen.getByRole("button", { name: "Send" }));
        return contexte;
    }

    it("envoie le message à la route du builder avec l'agent, et dessine une carte par action", async () => {
        await envoyer([
            { type: "texte", texte: "Je lis." },
            { type: "action", id: "a1", nom: "fiche_ecrire", arguments: {} },
            { type: "resultat", id: "a1", nom: "fiche_ecrire", ok: true, resultat: { lignes: 1 } },
            { type: "action", id: "a2", nom: "tests_rejouer", arguments: {} },
            { type: "resultat", id: "a2", nom: "tests_rejouer", ok: true, resultat: { disponible: false, message: "pas encore" } },
            { type: "action", id: "a3", nom: "reglages_lire", arguments: {} },
            { type: "resultat", id: "a3", nom: "reglages_lire", ok: true, resultat: {} },
            { type: "fin", raison: "fin" },
        ]);
        await waitFor(() => expect(m.parler).toHaveBeenCalled());
        expect(m.parler.mock.calls[0][0]).toMatchObject({ body: { workflow_id: 5, message: "lis les documents" }, parseAs: "stream" });
        expect(await screen.findByText("Je lis.")).toBeTruthy();
        expect(await waitFor(() => document.querySelector('[data-carte="fiche"]'))).toBeTruthy();
        // « Pas encore disponible » : dit comme tel (carte de résultat), jamais présenté comme fait.
        await waitFor(() => expect(document.querySelector("[data-non-disponible]")).toBeTruthy());
        // Une action sans carte laisse une ligne de la liste des tâches.
        expect(document.querySelector('[data-tache="reglages_lire"]')).toBeTruthy();
    });

    it("une même carte vivante n'est dessinée qu'une fois par message, même si l'action est appelée trois fois", async () => {
        const appels = ["a1", "a2", "a3"].flatMap((id): EvenementDuBuilder[] => [
            { type: "action", id, nom: "fiche_ecrire", arguments: {} },
            { type: "resultat", id, nom: "fiche_ecrire", ok: true, resultat: {} },
        ]);
        await envoyer([...appels, { type: "fin", raison: "fin" }]);
        await waitFor(() => expect(document.querySelectorAll('[data-carte="fiche"]').length).toBeGreaterThan(0));
        expect(document.querySelectorAll('[data-carte="fiche"]')).toHaveLength(1);
    });

    it("les opérations de construction montrent la carte des changements et gardent Accepter fermé tant que le brouillon n'est pas enregistré", async () => {
        await envoyer([
            { type: "action", id: "o1", nom: "brouillon_operation", arguments: {} },
            { type: "operation", operation: { op: "ajouter_noeud", id: "2", type: "endCall", nom: "Fin" } },
            { type: "resultat", id: "o1", nom: "brouillon_operation", ok: true, resultat: { en_attente: 1 } },
            { type: "fin", raison: "fin" },
        ]);
        const carte = await waitFor(() => {
            const c = document.querySelector('[data-carte="changements"]');
            if (!c) throw new Error("pas de carte");
            return c as HTMLElement;
        });
        expect(carte.textContent).toContain("1");
        expect((within(carte).getByRole("button", { name: "Accept" }) as HTMLButtonElement).disabled).toBe(true);
        expect((within(carte).getByRole("button", { name: "Refuse" }) as HTMLButtonElement).disabled).toBe(true);
        expect(document.querySelector('[data-bandeau="brouillon"]')).toBeTruthy();
        expect((screen.getByRole("button", { name: "Publish" }) as HTMLButtonElement).disabled).toBe(true); // seule une personne publie
    });

    it("une fois le brouillon enregistré, Refuser remet le graphe d'avant et solde la relecture", async () => {
        const contexte = await envoyer([
            { type: "action", id: "o1", nom: "brouillon_operation", arguments: {} },
            { type: "operation", operation: { op: "ajouter_noeud", id: "2", type: "endCall", nom: "Fin" } },
            { type: "resultat", id: "o1", nom: "brouillon_operation", ok: true, resultat: {} },
            { type: "carte", carte: { type: "changements", version: 2, nombre_operations: 1, noeuds: 2, liaisons: 0 } },
            { type: "fin", raison: "fin" },
        ]);
        await waitFor(() => expect(useBuilderEcran.getState().changements).not.toBeNull());
        const carte = document.querySelector('[data-carte="changements"]') as HTMLElement;
        const refuser = within(carte).getByRole("button", { name: "Refuse" }) as HTMLButtonElement;
        await waitFor(() => expect(refuser.disabled).toBe(false));
        fireEvent.click(refuser);
        await waitFor(() => expect(contexte.restaurer).toHaveBeenCalledWith(GRAPHE));
        await waitFor(() => expect(useBuilderEcran.getState().avant).toBeNull());
        expect(document.querySelector('[data-bandeau="brouillon"]')).toBeNull();
    });

    it("« Appeler l'agent » et « Essayer au clavier » passent par les fenêtres d'essai existantes", async () => {
        const contexte = contexteDuPanneau();
        render(<PanneauBuilder contexte={contexte} noeuds={GRAPHE.nodes} />);
        fireEvent.click(await screen.findByRole("button", { name: "Call the agent" }));
        fireEvent.click(screen.getByText("Try by keyboard"));
        expect(contexte.appelerLAgent).toHaveBeenCalledTimes(1);
        expect(contexte.essayerAuClavier).toHaveBeenCalledTimes(1);
    });

    it("un nœud cité depuis le graphe (« Demander au builder ») arrive dans la zone d'écriture", async () => {
        render(<PanneauBuilder contexte={contexteDuPanneau()} noeuds={GRAPHE.nodes} />);
        const zone = (await screen.findByLabelText("Write to the builder...")) as HTMLTextAreaElement;
        useBuilderEcran.getState().citer({ id: "1", nom: "Départ" });
        await waitFor(() => expect(zone.value).toContain("@Départ"));
        expect(useBuilderEcran.getState().citation).toBeNull();
    });

    it("l'historique de l'agent est relu à l'ouverture", async () => {
        m.historique.mockResolvedValue({
            data: { messages: [{ role: "user", content: "[Résumé]\nx\n\n[Message de la personne]\nBonjour" }, { role: "assistant", content: "Salut" }], resume: "", depense: {}, en_cours: false },
        });
        render(<PanneauBuilder contexte={contexteDuPanneau()} noeuds={GRAPHE.nodes} />);
        expect(await screen.findByText("Bonjour")).toBeTruthy(); // seulement les mots de la personne
        expect(await screen.findByText("Salut")).toBeTruthy();
        expect(screen.queryByText(/Résumé/)).toBeNull();
    });

    it("dit quel cerveau travaille, ou qu'il n'y en a pas", async () => {
        render(<PanneauBuilder contexte={contexteDuPanneau()} noeuds={GRAPHE.nodes} />);
        await waitFor(() => expect(document.querySelector("[data-cerveau]")?.textContent).toContain("modele-x"));
        cleanup();
        m.cerveauLire.mockResolvedValue({ data: { format: "anthropic", modele: "", cle_posee: false } });
        render(<PanneauBuilder contexte={contexteDuPanneau()} noeuds={GRAPHE.nodes} />);
        await waitFor(() => expect(document.querySelector("[data-cerveau]")?.textContent).toContain("No brain set"));
    });
});

describe("la barre du haut", () => {
    it("« Builder IA » ouvre et ferme le panneau, « Tests » mène à la page des tests de l'agent", () => {
        const onToggle = vi.fn();
        render(<BarreDuBuilder ouvert={false} onToggle={onToggle} testsHref="/workflow/5/tests" />);
        fireEvent.click(screen.getByRole("button", { name: "Builder AI" }));
        expect(onToggle).toHaveBeenCalledTimes(1);
        expect(screen.getByRole("link", { name: "Tests" }).getAttribute("href")).toBe("/workflow/5/tests");
        expect(screen.getByRole("button", { name: "Builder AI" }).getAttribute("aria-pressed")).toBe("false");
    });
});
