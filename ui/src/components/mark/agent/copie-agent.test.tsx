/**
 * [.mark] U2 quinquies (lot H2, E58, E33) : la fenêtre « Exporter vers un client » / « Ramener au Labo ».
 *
 * Questions de ce fichier :
 *
 *     La liste des organisations vient du serveur, se filtre par la recherche et dit si la copie existe déjà ? Le relevé met un
 *     choix par élément (la clé : laisser vide, jamais copier) et l'envoi porte ces choix tels quels, avec les tests si on le veut ?
 *     Le compte rendu dit ce qui est copié, relié, laissé vide, et mène à l'agent copié ? « Ramener » saute le choix de
 *     l'organisation (le Labo est la seule cible) ? Une copie qui échoue le dit par une notification, sans texte brut ?
 */
import { cleanup, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { FenetreCopieAgent } from "./copie/FenetreCopieAgent";

const m = vi.hoisted(() => ({
    push: vi.fn(),
    cibles: vi.fn(),
    releve: vi.fn(),
    copier: vi.fn(),
    echec: vi.fn(),
    succes: vi.fn(),
    retenir: vi.fn(),
}));
vi.mock("next/navigation", () => ({ useRouter: () => ({ push: m.push }) }));
vi.mock("@/client/sdk.gen", () => ({
    ciblesApiV1ExportAgentWorkflowIdCiblesGet: m.cibles,
    releveApiV1ExportAgentWorkflowIdReleveGet: m.releve,
    copierApiV1ExportAgentWorkflowIdCopierPost: m.copier,
}));
vi.mock("@/lib/espaceCourant", () => ({ retenirEspace: m.retenir }));
vi.mock("@/components/mark/notifications", () => ({
    notifier: {
        enCours: () => ({ succes: m.succes, echec: m.echec, fermer: vi.fn() }),
        echec: m.echec,
        succes: m.succes,
    },
}));

const CIBLES = {
    sens: "exporter",
    cibles: [
        { id: 7, nom: "Nuances de Feu", deja_copie: null },
        { id: 8, nom: "Vie et Véranda", deja_copie: { agent_id: 99, nom: "Accueil" } },
    ],
};
const RELEVE = {
    sens: "exporter",
    source_organization_id: 1,
    cible_organization_id: 7,
    agent_id: 5,
    agent_nom: "Accueil",
    nb_tests: 24,
    deja_copie: null,
    elements: [
        { type: "agent", ref: "5", nom: "Accueil", choix: ["copier"], defaut: "copier", cibles: [], code: "principal" },
        {
            type: "outil",
            ref: "t1",
            nom: "Prendre un rendez-vous",
            detail: "http_api",
            choix: ["relier", "copier", "vide"],
            defaut: "relier",
            cibles: [{ ref: "t-client", nom: "Prendre un rendez-vous" }],
            cible_par_defaut: "t-client",
        },
        { type: "document", ref: "d1", nom: "tarifs.pdf", choix: ["copier", "vide"], defaut: "copier", cibles: [] },
        { type: "cle", ref: "k1", nom: "Clé CRM", choix: ["vide"], defaut: "vide", cibles: [], code: "jamais_copiee" },
    ],
};
const COMPTE = {
    sens: "exporter",
    deja_copie: false,
    cible_organization_id: 7,
    agent_id: 50,
    dossier_id: null,
    tests_copies: 24,
    secrets_retires: 1,
    agents: [{ id: 50, nom: "Accueil" }],
    lignes: [
        { type: "agent", nom: "Accueil", action: "copier" },
        { type: "outil", nom: "Prendre un rendez-vous", action: "relier" },
        { type: "document", nom: "tarifs.pdf", action: "copier" },
        { type: "cle", nom: "Clé CRM", action: "vide" },
    ],
};

beforeEach(() => {
    m.cibles.mockResolvedValue({ data: CIBLES });
    m.releve.mockResolvedValue({ data: RELEVE });
    m.copier.mockResolvedValue({ data: COMPTE });
});
afterEach(() => {
    cleanup();
    Object.values(m).forEach((f) => f.mockReset());
});

const choisirNuances = async () => {
    fireEvent.click(await screen.findByText("Nuances de Feu"));
    fireEvent.click(screen.getByRole("button", { name: "Continue" }));
};

describe("Exporter vers un client", () => {
    it("liste les organisations du serveur, filtre par la recherche, dit si la copie existe déjà", async () => {
        render(<FenetreCopieAgent agentId={5} nom="Accueil" sens="exporter" fermer={vi.fn()} />);
        expect(await screen.findByText("Nuances de Feu")).toBeTruthy();
        expect(screen.getByText("Already copied")).toBeTruthy();
        expect(screen.getByText("Not copied yet")).toBeTruthy();
        expect(m.cibles).toHaveBeenCalledWith({ path: { workflow_id: 5 }, query: { sens: "exporter" } });
        fireEvent.change(screen.getByLabelText("Search an organization"), { target: { value: "véranda" } });
        expect(screen.queryByText("Nuances de Feu")).toBeNull();
        expect(screen.getByText("Vie et Véranda")).toBeTruthy();
        expect((screen.getByRole("button", { name: "Continue" }) as HTMLButtonElement).disabled).toBe(true);
    });

    it("le relevé met un choix par élément, la clé n'a que « laisser vide », et l'envoi porte les choix et les tests", async () => {
        render(<FenetreCopieAgent agentId={5} nom="Accueil" sens="exporter" fermer={vi.fn()} />);
        await choisirNuances();
        const outil = await waitFor(() => {
            const ligne = document.querySelector('[data-element="outil:t1"]');
            if (!ligne) throw new Error("pas encore");
            return ligne as HTMLElement;
        });
        expect(m.releve).toHaveBeenCalledWith({ path: { workflow_id: 5 }, query: { sens: "exporter", cible: 7 } });
        expect(within(outil).getByText("Link to Prendre un rendez-vous")).toBeTruthy();
        expect(within(document.querySelector('[data-element="cle:k1"]') as HTMLElement).getByText("A key is never copied")).toBeTruthy();
        expect(within(document.querySelector('[data-element="agent:5"]') as HTMLElement).getByText("Copy at the client")).toBeTruthy();

        fireEvent.click(screen.getByRole("switch", { name: "With its tests" }));
        fireEvent.click(screen.getByRole("button", { name: "Export as a draft" }));
        await waitFor(() => expect(m.copier).toHaveBeenCalledTimes(1));
        expect(m.copier).toHaveBeenCalledWith({
            path: { workflow_id: 5 },
            body: {
                sens: "exporter",
                cible_organization_id: 7,
                avec_tests: false,
                choix: [
                    { type: "agent", ref: "5", action: "copier", cible: null },
                    { type: "outil", ref: "t1", action: "relier", cible: "t-client" },
                    { type: "document", ref: "d1", action: "copier", cible: null },
                    { type: "cle", ref: "k1", action: "vide", cible: null },
                ],
            },
        });
    });

    it("le compte rendu dit copié, relié, laissé vide, et mène à l'agent copié dans l'espace de la cible", async () => {
        const fermer = vi.fn();
        render(<FenetreCopieAgent agentId={5} nom="Accueil" sens="exporter" fermer={fermer} />);
        await choisirNuances();
        fireEvent.click(await screen.findByRole("button", { name: "Export as a draft" }));
        expect(await screen.findByText(/2 copied, 1 linked, 1 left empty/)).toBeTruthy();
        expect(screen.getByText(/1 secret values removed/)).toBeTruthy();
        expect(m.succes).toHaveBeenCalled();
        fireEvent.click(screen.getByRole("button", { name: "Open at Nuances de Feu" }));
        expect(m.retenir).toHaveBeenCalledWith("/clients/7");
        expect(m.push).toHaveBeenCalledWith("/agents/50");
        expect(fermer).toHaveBeenCalled();
    });

    it("un échec de copie reste à l'étape du relevé et le dit par une notification, sans texte brut", async () => {
        m.copier.mockResolvedValue({ error: { detail: "Traceback interne" } });
        render(<FenetreCopieAgent agentId={5} nom="Accueil" sens="exporter" fermer={vi.fn()} />);
        await choisirNuances();
        fireEvent.click(await screen.findByRole("button", { name: "Export as a draft" }));
        await waitFor(() => expect(m.echec).toHaveBeenCalled());
        expect(m.echec.mock.calls[0][0]).toEqual({ en: "Copy impossible. Try again.", fr: "Copie impossible. Réessayez." });
        expect(screen.queryByText(/Traceback/)).toBeNull();
        expect(screen.getByRole("button", { name: "Export as a draft" })).toBeTruthy();
    });

    it("une copie déjà faite : rien n'est réécrit et la fenêtre le dit", async () => {
        m.copier.mockResolvedValue({ data: { ...COMPTE, deja_copie: true, lignes: [], tests_copies: 0 } });
        render(<FenetreCopieAgent agentId={5} nom="Accueil" sens="exporter" fermer={vi.fn()} />);
        fireEvent.click(await screen.findByText("Vie et Véranda"));
        fireEvent.click(screen.getByRole("button", { name: "Continue" }));
        fireEvent.click(await screen.findByRole("button", { name: "Export as a draft" }));
        expect(await screen.findByText(/already copied there: nothing was written/)).toBeTruthy();
    });
});

describe("Ramener au Labo", () => {
    it("n'a qu'une cible, le Labo : il passe directement au relevé et ouvre la copie au Labo", async () => {
        m.cibles.mockResolvedValue({ data: { sens: "ramener", cibles: [{ id: 1, nom: "Labo", deja_copie: null }] } });
        m.releve.mockResolvedValue({ data: { ...RELEVE, sens: "ramener", cible_organization_id: 1 } });
        m.copier.mockResolvedValue({ data: { ...COMPTE, sens: "ramener", cible_organization_id: 1, agent_id: 60 } });
        render(<FenetreCopieAgent agentId={5} nom="Accueil" sens="ramener" fermer={vi.fn()} />);
        fireEvent.click(await screen.findByRole("button", { name: "Bring back as a draft" }));
        expect(m.releve).toHaveBeenCalledWith({ path: { workflow_id: 5 }, query: { sens: "ramener", cible: 1 } });
        expect(screen.queryByRole("button", { name: "Continue" })).toBeNull();
        await waitFor(() => expect(m.copier).toHaveBeenCalled());
        expect(m.copier.mock.calls[0][0].body.sens).toBe("ramener");
        fireEvent.click(await screen.findByRole("button", { name: "Open in the Labo" }));
        expect(m.retenir).toHaveBeenCalledWith("/labo");
        expect(m.push).toHaveBeenCalledWith("/agents/60");
    });

    it("A-7 : le nom de la copie et le dossier du Labo se choisissent, et le nom part avec la copie", async () => {
        m.cibles.mockResolvedValue({ data: { sens: "ramener", cibles: [{ id: 1, nom: "Labo", deja_copie: null }] } });
        m.releve.mockResolvedValue({ data: { ...RELEVE, sens: "ramener", cible_organization_id: 1, dossiers: [{ id: 3, nom: "Variantes 2026" }] } });
        m.copier.mockResolvedValue({ data: { ...COMPTE, sens: "ramener", cible_organization_id: 1, agent_id: 60 } });
        render(<FenetreCopieAgent agentId={5} nom="Accueil" sens="ramener" fermer={vi.fn()} />);
        const nom = (await screen.findByLabelText("Name of the copy")) as HTMLInputElement;
        expect(document.querySelector("[data-ramener-destination]")).not.toBeNull();
        expect(screen.getByText("Copies de clients (default)")).toBeTruthy();
        fireEvent.change(nom, { target: { value: "Accueil modèle" } });
        fireEvent.click(screen.getByRole("button", { name: "Bring back as a draft" }));
        await waitFor(() => expect(m.copier).toHaveBeenCalled());
        expect(m.copier.mock.calls[0][0].body).toMatchObject({ sens: "ramener", nom: "Accueil modèle", dossier_id: null });
    });

    it("A-7 : l'export vers un client n'a ni nom ni dossier à choisir", async () => {
        render(<FenetreCopieAgent agentId={5} nom="Accueil" sens="exporter" fermer={vi.fn()} />);
        await choisirNuances();
        await screen.findByText("tarifs.pdf");
        expect(document.querySelector("[data-ramener-destination]")).toBeNull();
        expect(m.copier).not.toHaveBeenCalled();
    });

    it("SE-7 : la fiche d'établissement qui peut suivre est proposée en copie, dite « sans ses numéros »", async () => {
        m.releve.mockResolvedValue({
            data: { ...RELEVE, elements: [...RELEVE.elements, { type: "etablissement", ref: "site-nord", nom: "site-nord", choix: ["copier", "vide"], defaut: "copier", cibles: [], code: "sans_numeros" }] },
        });
        render(<FenetreCopieAgent agentId={5} nom="Accueil" sens="exporter" fermer={vi.fn()} />);
        await choisirNuances();
        await screen.findByText("site-nord");
        expect(screen.getByText("The fiche follows, without its phone numbers")).toBeTruthy();
    });
});
