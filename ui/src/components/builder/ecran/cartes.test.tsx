/**
 * [.mark] builder-agent-vocal (lot 4): the cards of the Builder AI panel.
 *
 * Questions of this file:
 *
 *     Does the client sheet keep « Validate » closed while a gap is open, show each line with its source and the place
 *     of the fact, and send a person's answer as a line sourced from that person? Does a deposit show an unreadable
 *     file as unreadable, with its reason? Does a knowledge-base document wait for a person (validate / reject)? Does a
 *     result card of an action « not available yet » say so instead of showing it as done, and show the items of a
 *     result of any shape? Does the design document wait for approval?
 */
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { CarteBase } from "./cartes/CarteBase";
import { CarteConception } from "./cartes/CarteConception";
import { CarteDepot } from "./cartes/CarteDepot";
import { CarteFiche } from "./cartes/CarteFiche";
import { CarteResultat, elementsDe, nonDisponible } from "./cartes/CarteResultat";
import { useBuilderEcran } from "./store";

const m = vi.hoisted(() => ({
    ecrireLigne: vi.fn(),
    validerFiche: vi.fn(),
    lireConception: vi.fn(),
    decider: vi.fn(),
    validerBase: vi.fn(),
    rejeterBase: vi.fn(),
    contexte: vi.fn(),
    retirerDepot: vi.fn(),
}));

vi.mock("@/client", () => ({
    ecrireUneLigneDeLaFicheApiV1BuilderFicheWorkflowIdLignePut: (...a: unknown[]) => m.ecrireLigne(...a),
    validerLaFicheApiV1BuilderFicheWorkflowIdValiderPost: (...a: unknown[]) => m.validerFiche(...a),
    lireLaConceptionApiV1BuilderConceptionWorkflowIdGet: (...a: unknown[]) => m.lireConception(...a),
    deciderDeLaConceptionApiV1BuilderConceptionWorkflowIdDecisionPost: (...a: unknown[]) => m.decider(...a),
    validerUnDocumentDeBaseApiV1BuilderBaseWorkflowIdDocumentIdValiderPost: (...a: unknown[]) => m.validerBase(...a),
    rejeterUnDocumentDeBaseApiV1BuilderBaseWorkflowIdDocumentIdRejeterPost: (...a: unknown[]) => m.rejeterBase(...a),
    lireLeContexteApiV1BuilderContexteWorkflowIdGet: (...a: unknown[]) => m.contexte(...a),
    retirerUnDepotApiV1BuilderDepotWorkflowIdDepotIdDelete: (...a: unknown[]) => m.retirerDepot(...a),
    deposerUnFichierApiV1BuilderDepotWorkflowIdPost: vi.fn(),
    deposerUnSiteApiV1BuilderDepotWorkflowIdSitePost: vi.fn(),
}));

const VUE = (extra: Record<string, unknown> = {}) => ({
    depots: [],
    fiche: { champs: {}, trous: [] },
    classements: {},
    base: [],
    ...extra,
});

function poser(contexte: ReturnType<typeof VUE>) {
    useBuilderEcran.setState({ contexte: contexte as never });
    m.contexte.mockResolvedValue({ data: contexte });
}

beforeEach(() => {
    Object.values(m).forEach((f) => f.mockReset());
    useBuilderEcran.getState().reinitialiser();
    m.ecrireLigne.mockResolvedValue({ data: {} });
    m.validerFiche.mockResolvedValue({ data: {} });
    m.decider.mockResolvedValue({ data: {} });
    m.validerBase.mockResolvedValue({ data: {} });
    m.rejeterBase.mockResolvedValue({ data: {} });
});
afterEach(cleanup);

const FICHE = {
    champs: {
        horaires: { valeur: "9h-18h", source: "audit.pdf, p. 2", classement: "objet" },
        motifs_d_appel: { valeur: "rendez-vous", source: "audit.pdf, p. 1", classement: "regle" },
        catalogue: { valeur: "long...", source: "site, /produits", classement: "base" },
    },
    trous: [{ champ: "zone", question: "Quelle zone ?", reponse_suggeree: "Le département" }],
    valide_par: null,
};

describe("la carte « Fiche client »", () => {
    it("montre chaque ligne avec sa source et la place du fait (objet, base de connaissances, règle du prompt)", () => {
        poser(VUE({ fiche: FICHE, classements: { horaires: "objet", motifs_d_appel: "regle", catalogue: "base" } }));
        render(<CarteFiche workflowId={5} />);
        expect(screen.getByText(/audit.pdf, p. 2/)).toBeTruthy();
        const place = (champ: string) => document.querySelector(`[data-ligne="${champ}"] [data-classement]`)?.textContent ?? "";
        expect(place("horaires")).toContain("an object");
        expect(place("catalogue")).toContain("the knowledge base");
        expect(place("motifs_d_appel")).toContain("a prompt rule");
    });

    it("garde « Valider la fiche » fermé tant qu'un trou est ouvert", () => {
        poser(VUE({ fiche: FICHE }));
        render(<CarteFiche workflowId={5} />);
        expect((screen.getByRole("button", { name: "Validate the sheet" }) as HTMLButtonElement).disabled).toBe(true);
        expect(screen.getByText("Quelle zone ?")).toBeTruthy();
        expect(screen.getByText(/Suggested answer/)).toBeTruthy();
    });

    it("répondre à un trou envoie la réponse de la personne, puis relit le contexte", async () => {
        poser(VUE({ fiche: FICHE }));
        render(<CarteFiche workflowId={5} />);
        fireEvent.change(screen.getByLabelText("Quelle zone ?"), { target: { value: "Oise et Paris" } });
        fireEvent.click(screen.getByRole("button", { name: "Answer" }));
        await waitFor(() => expect(m.ecrireLigne).toHaveBeenCalled());
        expect(m.ecrireLigne.mock.calls[0][0]).toMatchObject({ path: { workflow_id: 5 }, body: { champ: "zone", valeur: "Oise et Paris" } });
        await waitFor(() => expect(m.contexte).toHaveBeenCalled());
    });

    it("reprendre la réponse suggérée écrit cette valeur", async () => {
        poser(VUE({ fiche: FICHE }));
        render(<CarteFiche workflowId={5} />);
        fireEvent.click(screen.getByRole("button", { name: "Use it" }));
        await waitFor(() => expect(m.ecrireLigne).toHaveBeenCalled());
        expect(m.ecrireLigne.mock.calls[0][0].body).toMatchObject({ champ: "zone", valeur: "Le département" });
    });

    it("sans trou, la fiche se valide ; validée, elle le dit", async () => {
        poser(VUE({ fiche: { ...FICHE, trous: [] } }));
        render(<CarteFiche workflowId={5} />);
        fireEvent.click(screen.getByRole("button", { name: "Validate the sheet" }));
        await waitFor(() => expect(m.validerFiche).toHaveBeenCalledTimes(1));
        cleanup();
        poser(VUE({ fiche: { ...FICHE, trous: [], valide_par: "Marie" } }));
        render(<CarteFiche workflowId={5} />);
        expect(document.querySelector("[data-validee]")?.textContent).toContain("Marie");
        expect(screen.queryByRole("button", { name: "Validate the sheet" })).toBeNull();
    });

    it("affiche le refus du serveur tel qu'il vient", async () => {
        m.validerFiche.mockResolvedValue({ error: { detail: "2 gap(s) are still open" } });
        poser(VUE({ fiche: { ...FICHE, trous: [] } }));
        render(<CarteFiche workflowId={5} />);
        fireEvent.click(screen.getByRole("button", { name: "Validate the sheet" }));
        expect((await screen.findByRole("alert")).textContent).toContain("2 gap(s) are still open");
    });
});

describe("la carte « Dépôt »", () => {
    it("montre un fichier illisible comme illisible, avec sa raison, jamais comme lu", () => {
        poser(
            VUE({
                depots: [
                    { id: "a", nom: "audit.pdf", genre: "fichier", statut: "lu", pages: 4, caracteres: 100, tronque: false },
                    { id: "b", nom: "scan.pdf", genre: "fichier", statut: "illisible", raison: "The PDF has no text layer (a scan?)", pages: 0, caracteres: 0 },
                    { id: "c", nom: "https://client.example", genre: "site", statut: "lu", pages: 3, refusees: [{ adresse: "https://client.example/prive", raison: "robots" }] },
                ],
            }),
        );
        render(<CarteDepot workflowId={5} />);
        expect(document.querySelector('[data-depot="audit.pdf"]')?.textContent).toContain("read");
        expect(document.querySelector('[data-depot="scan.pdf"]')?.textContent).toContain("unreadable");
        expect(document.querySelector('[data-depot="scan.pdf"]')?.textContent).toContain("no text layer");
        expect(document.querySelector('[data-depot="https://client.example"]')?.textContent).toContain("client.example/prive");
    });

    it("retirer un dépôt le demande au serveur puis relit", async () => {
        poser(VUE({ depots: [{ id: "a", nom: "audit.pdf", genre: "fichier", statut: "lu", pages: 1, caracteres: 10 }] }));
        m.retirerDepot.mockResolvedValue({ data: {} });
        render(<CarteDepot workflowId={5} />);
        fireEvent.click(screen.getByLabelText("Remove audit.pdf"));
        await waitFor(() => expect(m.retirerDepot).toHaveBeenCalled());
        expect(m.retirerDepot.mock.calls[0][0].path).toEqual({ workflow_id: 5, depot_id: "a" });
    });
});

describe("la carte « Base de connaissances »", () => {
    const DOC = {
        id: "d1",
        titre: "Devis et délais",
        contenu: "Le devis est réalisé sur place.",
        etat: "propose",
        sources: [{ document: "faq.md", page: 1, extrait: "Le devis est réalisé sur place" }],
        rattache_a: [],
    };

    it("un document proposé attend une personne : Valider ou Rejeter, jamais déjà dans la base", async () => {
        poser(VUE({ base: [DOC] }));
        render(<CarteBase workflowId={5} />);
        expect(document.querySelector('[data-document-base="Devis et délais"]')?.textContent).toContain("proposed");
        fireEvent.click(screen.getByRole("button", { name: "Validate" }));
        await waitFor(() => expect(m.validerBase).toHaveBeenCalled());
        expect(m.validerBase.mock.calls[0][0].path).toEqual({ workflow_id: 5, document_id: "d1" });
        fireEvent.click(screen.getByRole("button", { name: "Reject" }));
        await waitFor(() => expect(m.rejeterBase).toHaveBeenCalled());
    });

    it("un document validé n'a plus de boutons et montre où il est rattaché", () => {
        poser(VUE({ base: [{ ...DOC, etat: "valide", rattache_a: ["2"] }] }));
        render(<CarteBase workflowId={5} />);
        expect(screen.queryByRole("button", { name: "Validate" })).toBeNull();
        expect(screen.getByText(/Attached to 2/)).toBeTruthy();
    });
});

describe("la carte « Document de conception »", () => {
    const ETAT = (etat: string) => ({
        data: {
            conception: {
                etat,
                revision: 2,
                note: etat === "renvoye" ? "Précise les horaires" : null,
                decide_par: null,
                conception: {
                    objectif: "Prendre les demandes",
                    reussite: "Nom et numéro pris",
                    hypotheses: ["Horaires à jour"],
                    donnees: [{ nom: "numero", si_absente: "Proposer un rappel" }],
                    outils: [{ nom: "noter", reponses: ["ok", "erreur"], si_indisponible: "Proposer un rappel" }],
                    exemples_appels: ["Je voudrais être rappelé."],
                },
            },
        },
    });

    it("montre les rubriques (dont « système indisponible ») et attend l'approbation", async () => {
        m.lireConception.mockResolvedValue(ETAT("propose"));
        render(<CarteConception workflowId={5} />);
        expect(await screen.findByText("Prendre les demandes")).toBeTruthy();
        expect(screen.getAllByText(/Proposer un rappel/).length).toBeGreaterThanOrEqual(2);
        fireEvent.click(screen.getByRole("button", { name: "Approve" }));
        await waitFor(() => expect(m.decider).toHaveBeenCalled());
        expect(m.decider.mock.calls[0][0].body).toEqual({ approuve: true, note: null });
    });

    it("renvoyer demande une note", async () => {
        m.lireConception.mockResolvedValue(ETAT("propose"));
        render(<CarteConception workflowId={5} />);
        await screen.findByText("Prendre les demandes");
        fireEvent.click(screen.getByRole("button", { name: "Send back with a note" }));
        const envoyer = screen.getByRole("button", { name: "Send back with a note" }) as HTMLButtonElement;
        expect(envoyer.disabled).toBe(true);
        fireEvent.change(screen.getByLabelText("Note for the builder"), { target: { value: "Plus court" } });
        fireEvent.click(screen.getByRole("button", { name: "Send back with a note" }));
        await waitFor(() => expect(m.decider).toHaveBeenCalled());
        expect(m.decider.mock.calls[0][0].body).toEqual({ approuve: false, note: "Plus court" });
    });

    it("approuvé, plus de boutons", async () => {
        m.lireConception.mockResolvedValue(ETAT("approuve"));
        render(<CarteConception workflowId={5} />);
        await screen.findByText("Prendre les demandes");
        expect(screen.queryByRole("button", { name: "Approve" })).toBeNull();
    });
});

describe("les cartes de résultat (contrôle, outils, tests, rapport)", () => {
    it("une action pas encore disponible est dite telle quelle, jamais comme faite", () => {
        render(<CarteResultat nomDeLAction="tests_rejouer" resultat={{ disponible: false, message: "pas encore" }} />);
        expect(document.querySelector("[data-non-disponible]")).toBeTruthy();
        expect(document.querySelector('[data-statut="ok"]')).toBeNull();
    });

    it("lit les éléments d'un résultat de n'importe quelle forme (liste, statut, message)", () => {
        const resultat = {
            ok: true,
            defauts: [
                { regle: "regle_en_double", statut: "echec", message: "écrite deux fois" },
                { nom: "longueur", ok: true },
                { nom: "genre", statut: "avertissement", detail: "différent de la voix" },
            ],
        };
        expect(elementsDe(resultat)).toEqual([
            { nom: "regle_en_double", statut: "echec", message: "écrite deux fois" },
            { nom: "longueur", statut: "ok", message: undefined },
            { nom: "genre", statut: "avertissement", message: "différent de la voix" },
        ]);
        render(<CarteResultat nomDeLAction="prompt_controler" resultat={resultat} />);
        expect(document.querySelectorAll("[data-statut]")).toHaveLength(3);
        expect(screen.getByText("Prompt check")).toBeTruthy();
    });

    it("trouve la première liste d'objets quand la clé est inconnue, et garde le résultat brut lisible", () => {
        const resultat = { ok: true, resume: "x", suite: [{ test: "t1", statut: "reussi" }] };
        expect(elementsDe(resultat)[0]).toMatchObject({ nom: "t1", statut: "ok" });
        render(<CarteResultat nomDeLAction="tests_creer" resultat={resultat} />);
        expect(screen.getByText("Raw result")).toBeTruthy();
    });

    it("sait reconnaître le « pas encore disponible » du serveur", () => {
        expect(nonDisponible({ disponible: false })).toBe(true);
        expect(nonDisponible({ ok: true })).toBe(false);
        expect(nonDisponible(undefined)).toBe(false);
    });

    it("une action en échec montre son erreur", () => {
        render(<CarteResultat nomDeLAction="outil_essayer" resultat={{ ok: false, erreur: "no answer" }} erreur />);
        expect(screen.getByText(/The action failed:/).textContent).toContain("no answer");
    });
});
