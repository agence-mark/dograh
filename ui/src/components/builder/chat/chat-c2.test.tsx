/**
 * [.mark] builder partie 2, U5 (lot C2) : les cartes du fil (rapport, dépense, correction, proposition), la revue champ par champ,
 * les sous-agents et la visionneuse de fichiers.
 *
 * Questions : une dépense annoncée garde-t-elle sa place et change-t-elle d'état à la réponse ? La revue montre-t-elle « 2/3 » et
 * envoie-t-elle le bon rang ? Un sous-agent en cours montre-t-il Arrêter ? La recherche du fichier compte-t-elle et surligne-t-elle ?
 */
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

const accepter = vi.fn(async (_o?: unknown) => ({ data: { acceptes: 1 } }));
const refuser = vi.fn(async (_o?: unknown) => ({ data: { refuses: 1 } }));
const restaurer = vi.fn(async (_o?: unknown) => ({ data: { version: 3 } }));
const lireTexte = vi.fn(async ({ query }: { query: { page: number } }) => ({
    data: { genre: "pages", page: query.page, pages: 2, texte: query.page === 1 ? "Bonjour le monde" : "le monde est grand" },
}));

vi.mock("@/client", () => ({
    accepterLesChangementsApiV1BuilderFilsFilIdChangementsAccepterPost: (o: unknown) => accepter(o),
    refuserLesChangementsApiV1BuilderFilsFilIdChangementsRefuserPost: (o: unknown) => refuser(o),
    restaurerUneVersionApiV1BuilderAgentsWorkflowIdVersionsNumeroRestaurerPost: (o: unknown) => restaurer(o),
    lireLesChangementsApiV1BuilderFilsFilIdChangementsGet: async () => ({
        data: {
            total: 3,
            changements: [
                { rang: 0, op: "modifier_noeud", cible: "1", champ: "nom", avant: "Départ", apres: "Accueil" },
                { rang: 1, op: "modifier_noeud", cible: "1", champ: "prompt", avant: "p1", apres: "nouveau" },
                { rang: 2, op: "supprimer_noeud", cible: "2", champ: "noeud", avant: "Fin", apres: null },
            ],
        },
    }),
    listerLesVersionsApiV1BuilderAgentsWorkflowIdVersionsGet: async () => ({
        data: [{ numero: 2, cause: "acceptation", date: "2026-11-03T10:00:00Z" }],
    }),
    lireLeTexteDUnFichierApiV1BuilderFichiersDocumentUuidTexteGet: (o: unknown) => lireTexte(o as never),
    arreterUnFilApiV1BuilderFilsFilIdArreterPost: vi.fn(async () => ({ data: {} })),
    arreterTousLesSousAgentsApiV1BuilderFilsFilIdSousAgentsArreterPost: vi.fn(async () => ({ data: {} })),
    listerLesSousAgentsApiV1BuilderFilsFilIdSousAgentsGet: async () => ({ data: { actif: true, sous_agents: [] } }),
    reglerLInterrupteurApiV1BuilderFilsFilIdSousAgentsInterrupteurPut: vi.fn(async () => ({ data: {} })),
}));

import { compterDans, FenetreFichier, lireCsv, Surligne } from "../fichier/FenetreFichier";
import { CarteCorrection, CarteDepense, CartePropositionTest, CarteRapport } from "./cartes-c2";
import { appliquer, type EvenementDuFil, type LigneDuFil } from "./evenements";
import { montrer, RevueChampParChamp } from "./RevueChampParChamp";
import { CarteSousAgents, ListeDesSousAgents, type SousAgent } from "./SousAgents";

afterEach(() => {
    cleanup();
    vi.clearAllMocks();
});

const rejouer = (flux: [number, EvenementDuFil][]): LigneDuFil[] => flux.reduce<LigneDuFil[]>((l, [id, e]) => appliquer(l, id, e), []);

describe("evenements C2", () => {
    it("la dépense garde sa place et change d'état à la réponse", () => {
        const lignes = rejouer([
            [1, { type: "carte", carte: { type: "depense", id: "d1", motif: "Rejouer", montant_estime: 0.4, statut: "attente" } }],
            [2, { type: "texte", texte: "J'attends" }],
            [3, { type: "depense_reponse", id: "d1", statut: "accordee" }],
        ]);
        expect(lignes[0]).toMatchObject({ genre: "carte", carte: { statut: "accordee" } });
        expect(lignes).toHaveLength(2);
    });

    it("une délégation devient une carte, puis passe à finie", () => {
        const lignes = rejouer([
            [1, { type: "delegation", id: "ab", usage: "analyser", total: 3, modele: "m" }],
            [2, { type: "delegation_fin", id: "ab", cout: 0.2 }],
        ]);
        expect(lignes[0]).toMatchObject({ genre: "carte", carte: { type: "delegation", fini: true, total: 3 } });
    });
});

describe("cartes", () => {
    it("le rapport de fin montre les tests réussis, la raison d'un échec, les phrases et les points ouverts", () => {
        render(
            <CarteRapport
                carte={{
                    type: "rapport",
                    resume: "L'agent prend les rendez-vous.",
                    reussis: 1,
                    tests: [
                        { nom: "t1", ok: true },
                        { nom: "t2", ok: false, pourquoi: "Dit le nom d'un outil." },
                    ],
                    phrases_a_essayer: ["Je voudrais un rendez-vous."],
                    points_ouverts: ["Numéro de transfert."],
                }}
            />,
        );
        expect(screen.getByText(/1\/2/)).toBeTruthy();
        expect(screen.getByText(/Dit le nom d'un outil/)).toBeTruthy();
        expect(screen.getByText("Je voudrais un rendez-vous.")).toBeTruthy();
        expect(screen.getByText("Numéro de transfert.")).toBeTruthy();
    });

    it("la dépense attend l'accord : Accorder répond vrai, Refuser répond faux, puis elle affiche la réponse", () => {
        const repondre = vi.fn();
        const carte = { type: "depense", id: "d1", motif: "Rejouer la suite", montant_estime: 0.4, statut: "attente" };
        const { rerender } = render(<CarteDepense carte={carte} repondre={repondre} active />);
        fireEvent.click(screen.getByText("Agree"));
        fireEvent.click(screen.getByText("Refuse"));
        expect(repondre.mock.calls).toEqual([[true], [false]]);
        rerender(<CarteDepense carte={{ ...carte, statut: "accordee" }} repondre={repondre} active />);
        expect(screen.queryByText("Refuse")).toBeNull();
        expect(screen.getByText("Agreed")).toBeTruthy();
    });

    it("la correction montre l'avant et l'après ; renvoyer demande une note et l'envoie", () => {
        const repondre = vi.fn();
        render(
            <CarteCorrection
                carte={{ type: "correction", cause: "Oublie le nom", replique: "Bonjour.", objet: "etape", cible: "accueil", avant: "ancien texte", apres: "nouveau texte" }}
                repondre={repondre}
                active
            />,
        );
        expect(screen.getByText("ancien texte")).toBeTruthy();
        expect(screen.getByText("nouveau texte")).toBeTruthy();
        fireEvent.click(screen.getByText("Send back"));
        fireEvent.change(screen.getByPlaceholderText("What should change?"), { target: { value: "Plus court" } });
        fireEvent.click(screen.getByText("Send"));
        expect(repondre).toHaveBeenCalledWith("Sent back. Plus court");
    });

    it("la proposition de suppression d'un test n'efface rien : elle renvoie vers l'onglet Tests", () => {
        render(<CartePropositionTest carte={{ type: "proposition_test", genre: "suppression", workflow_id: 7, test: { nom: "Prise de RDV", slug: "prise" } }} />);
        expect(screen.getByText(/Prise de RDV/)).toBeTruthy();
        expect(screen.getByText("Open the Tests tab").getAttribute("href")).toBe("/agents/7/tests");
    });
});

describe("revue champ par champ", () => {
    it("affiche 1/3, passe au suivant, envoie le rang du changement accepté, et propose de revenir en arrière", async () => {
        render(<RevueChampParChamp filId={5} workflowId={9} />);
        await screen.findByText("Change 1/3");
        expect(screen.getByText("Départ")).toBeTruthy();
        fireEvent.click(screen.getByLabelText(">"));
        await screen.findByText("Change 2/3");
        fireEvent.click(screen.getByText("Accept"));
        await waitFor(() => expect(accepter).toHaveBeenCalledWith({ path: { fil_id: 5 }, body: { rangs: [1] } }));
        fireEvent.click(screen.getByText("Refuse all"));
        await waitFor(() => expect(refuser).toHaveBeenCalledWith({ path: { fil_id: 5 }, body: { rangs: [] } }));
        fireEvent.click(await screen.findByText("Go back before this"));
        await waitFor(() => expect(restaurer).toHaveBeenCalledWith({ path: { workflow_id: 9, numero: 2 } }));
    });

    it("montre (vide) pour une valeur absente", () => {
        expect(montrer(null, "(vide)")).toBe("(vide)");
        expect(montrer({ a: 1 }, "(vide)")).toContain('"a": 1');
    });
});

const sous = (plus: Partial<SousAgent>): SousAgent => ({
    id: 1, delegation: "ab", titre: "Lot 1", usage: "analyser", etat: "en_cours", modele: "m", cout: 0.05, resume: null, en_cours: true, ...plus,
});

describe("sous-agents", () => {
    it("la carte compte les terminés, offre Arrêter à celui qui travaille et Voir à tous", () => {
        const voir = vi.fn();
        render(
            <CarteSousAgents
                carte={{ id: "ab", usage: "analyser", total: 2 }}
                sousAgents={[sous({}), sous({ id: 2, titre: "Lot 2", etat: "terminee", en_cours: false, resume: "Rien d'anormal." })]}
                voir={voir}
                recharger={() => {}}
                filId={5}
            />,
        );
        expect(screen.getByText(/1\/2/)).toBeTruthy();
        expect(screen.getAllByText("Stop")).toHaveLength(1);
        fireEvent.click(screen.getAllByText("View")[1]);
        expect(voir).toHaveBeenCalledWith(2);
    });

    it("la liste attachée : conversation principale puis sous-agents ; elle bascule, et rien sans sous-agent", () => {
        const choisir = vi.fn();
        const { container, rerender } = render(
            <ListeDesSousAgents filId={5} actifDansLeChat sousAgents={[]} choisi={null} choisir={choisir} recharger={() => {}} />,
        );
        expect(container.innerHTML).toBe("");
        rerender(<ListeDesSousAgents filId={5} actifDansLeChat sousAgents={[sous({})]} choisi={null} choisir={choisir} recharger={() => {}} />);
        fireEvent.click(screen.getByLabelText("Sub-agents"));
        fireEvent.click(screen.getByText("Lot 1"));
        expect(choisir).toHaveBeenCalledWith(1);
        fireEvent.click(screen.getByText("Main conversation"));
        expect(choisir).toHaveBeenLastCalledWith(null);
    });
});

describe("visionneuse de fichiers", () => {
    it("compte et surligne les occurrences sans tenir compte de la casse", () => {
        expect(compterDans({ sorte: "texte", texte: "Le monde, LE MONDE, le monde" }, "monde")).toBe(3);
        expect(compterDans({ sorte: "pages", pages: ["a b", "b b"] }, "b")).toBe(3);
        expect(compterDans({ sorte: "tableau", colonnes: ["x"], lignes: [["abc"], ["cab"]] }, "ab")).toBe(2);
        expect(compterDans({ sorte: "texte", texte: "abc" }, "")).toBe(0);
        const { container } = render(<Surligne texte="Le Monde" q="monde" />);
        expect(container.querySelector("mark")?.textContent).toBe("Monde");
        expect(lireCsv("a;b\n1;2").lignes).toEqual([["1", "2"]]);
    });

    it("un fichier texte joint se lit dans le navigateur, avec recherche", async () => {
        const fichier = new File(["Bonjour le monde\nle monde est grand"], "notes.txt", { type: "text/plain" });
        render(<FenetreFichier nom="notes.txt" fichier={fichier} fermer={() => {}} />);
        await screen.findByPlaceholderText("Search in the file");
        fireEvent.change(screen.getByPlaceholderText("Search in the file"), { target: { value: "monde" } });
        await waitFor(() => expect(screen.getByText(/2 results/)).toBeTruthy());
        expect(document.querySelectorAll("mark")).toHaveLength(2);
    });

    it("un fichier déjà envoyé se lit par la route du serveur, page par page", async () => {
        render(<FenetreFichier nom="guide.pdf" documentUuid="u-1" fermer={() => {}} />);
        await screen.findByText(/Page 2 of 2/);
        expect(lireTexte).toHaveBeenCalledTimes(2);
        expect(screen.getByText("Bonjour le monde")).toBeTruthy();
    });
});
