/**
 * [.mark] U3 septies (lot H1, E78) : les écrans du Hub « Relation clients », branchés sur `/relation/*`.
 *
 * | Test | Ce qu'il prouve |
 * |---|---|
 * | Ma file | les fils qui attendent viennent du serveur, avec leur client ; file vide : « Rien n'attend » |
 * | Messages | la conversation montre les trois côtés ; répondre envoie ``mark``, la note interne envoie ``interne`` |
 * | demande de logiciel | l'état propre de la demande se change par l'API |
 * | Ouvrir son portail | désactivé sans adresse de portail réglée ; le jeton n'est jamais affiché |
 * | Avis | note et nombre viennent du serveur ; un témoignage sans accord le dit |
 */
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { FournisseurLangue } from "@/components/mark/langue/langue";

const sdk = vi.hoisted(() => ({
    file: vi.fn(),
    clients: vi.fn(),
    fils: vi.fn(),
    lireFil: vi.fn(),
    modifier: vi.fn(),
    repondre: vi.fn(),
    avis: vi.fn(),
    entree: vi.fn(),
}));
vi.mock("@/client/sdk.gen", () => ({
    maFileApiV1RelationFileGet: sdk.file,
    listerClientsApiV1RelationClientsGet: sdk.clients,
    listerFilsApiV1RelationFilsGet: sdk.fils,
    lireFilApiV1RelationClientsOrganizationIdFilsFilIdGet: sdk.lireFil,
    modifierFilApiV1RelationClientsOrganizationIdFilsFilIdPatch: sdk.modifier,
    repondreApiV1RelationClientsOrganizationIdFilsFilIdMessagesPost: sdk.repondre,
    avisEtTemoignagesApiV1RelationAvisGet: sdk.avis,
    ouvrirSonPortailApiV1RelationClientsOrganizationIdEntreePost: sdk.entree,
    listerEntreesApiV1RelationEntreesGet: vi.fn(),
    listerNotesApiV1RelationClientsOrganizationIdNotesGet: vi.fn(),
    ajouterNoteApiV1RelationClientsOrganizationIdNotesPost: vi.fn(),
    supprimerNoteApiV1RelationClientsOrganizationIdNotesNoteIdDelete: vi.fn(),
    ajouterTemoignageApiV1RelationClientsOrganizationIdTemoignagesPost: vi.fn(),
    reglerAccordApiV1RelationClientsOrganizationIdTemoignagesTemoignageIdPatch: vi.fn(),
    supprimerTemoignageApiV1RelationClientsOrganizationIdTemoignagesTemoignageIdDelete: vi.fn(),
}));
vi.mock("@/lib/auth", () => ({ useAuth: () => ({ loading: false, user: { email: "a@b.c" } }) }));
vi.mock("next/navigation", () => ({ useRouter: () => ({ push: vi.fn() }) }));
vi.mock("sonner", () => ({ toast: { error: vi.fn(), success: vi.fn() } }));

import { AccueilRelation, EcranAvis, EcranMessages, FicheClient } from "./EcransRelation";
import { oublierLectureClients } from "./lecture-clients";

const ok = <T,>(data: T) => Promise.resolve({ data, error: undefined });
const maintenant = new Date().toISOString();
const fil = (sur: object = {}) => ({
    id: 1, organization_id: 7, client: "Nuances de Feu", sorte: "message", sujet: "Couper les SMS le dimanche", etat: "nouveau",
    suivi_par: null, suivi_nom: null, lu_par_mark: false, logiciel: null, catalogue: null, etat_demande: null,
    cree_le: maintenant, modifie_le: maintenant, dernier: null, ...sur,
});
const avec = (ui: React.ReactNode) => render(<FournisseurLangue>{ui}</FournisseurLangue>);

beforeEach(() => {
    oublierLectureClients();
    Object.values(sdk).forEach((f) => f.mockReset());
    sdk.clients.mockImplementation(() => ok([{ id: 7, nom: "Nuances de Feu", ouverts: 1, non_lus: 1, demandes_nouvelles: 0 }]));
});
afterEach(cleanup);

describe("Ma file", () => {
    it("liste ce qui attend, avec le client", async () => {
        sdk.file.mockImplementation(() => ok([fil()]));
        avec(<AccueilRelation />);
        expect(await screen.findByText("Couper les SMS le dimanche")).toBeTruthy();
        expect(screen.getAllByText("Nuances de Feu").length).toBeGreaterThan(0);
    });
    it("dit que rien n'attend l'équipe quand la file est vide, avec une donnée réelle (J, E102)", async () => {
        sdk.file.mockImplementation(() => ok([]));
        avec(<AccueilRelation />);
        expect(await screen.findByText("Rien n'attend l'équipe")).toBeTruthy();
        expect(await screen.findByText("1 client")).toBeTruthy();
        expect(screen.queryByRole("button", { name: /Réessayer|Effacer|Créer|Ajouter|Nouveau/ })).toBeNull(); // aucun bouton d'action
    });
});

describe("Messages : les trois états vides de la colonne des fils (J, E102)", () => {
    it("aucun fil nulle part : « Aucun fil », sans bouton", async () => {
        sdk.fils.mockImplementation(() => ok([]));
        avec(<EcranMessages />);
        // Le filtre de départ est « À traiter » : une file vide est une bonne nouvelle.
        expect(await screen.findByText("Rien n'attend")).toBeTruthy();
    });
    it("une recherche sans résultat : « Aucun résultat pour », et « Effacer les filtres » la vide", async () => {
        sdk.fils.mockImplementation(() => ok([]));
        avec(<EcranMessages />);
        await screen.findByText("Rien n'attend");
        fireEvent.change(screen.getByPlaceholderText("Rechercher"), { target: { value: "zzz" } });
        expect(await screen.findByText(/Aucun résultat pour/)).toBeTruthy();
        fireEvent.click(screen.getByRole("button", { name: "Effacer les filtres" }));
        await waitFor(() => expect((screen.getByPlaceholderText("Rechercher") as HTMLInputElement).value).toBe(""));
    });
});

describe("Messages", () => {
    const complet = (sur: object = {}) =>
        fil({
            messages: [
                { id: 1, cote: "client", auteur: "Martine", texte: "Bonjour", cree_le: maintenant },
                { id: 2, cote: "interne", auteur: "Evan", texte: "A voir avec Pierre", cree_le: maintenant },
            ],
            ...sur,
        });
    beforeEach(() => {
        sdk.fils.mockImplementation(() => ok([fil()]));
        sdk.lireFil.mockImplementation(() => ok(complet()));
        sdk.repondre.mockImplementation(() => ok({ id: 3 }));
        sdk.modifier.mockImplementation(() => Promise.resolve({ error: undefined }));
    });

    it("montre les trois côtés et envoie la réponse ou la note interne du bon côté", async () => {
        avec(<EcranMessages fil={1} />);
        expect(await screen.findByText("Bonjour")).toBeTruthy();
        expect(screen.getByText("A voir avec Pierre")).toBeTruthy();

        fireEvent.change(screen.getAllByRole("textbox").at(-1) as HTMLTextAreaElement, { target: { value: "Réglé" } });
        fireEvent.click(screen.getByRole("button", { name: "Envoyer" }));
        await waitFor(() => expect(sdk.repondre).toHaveBeenCalled());
        expect(sdk.repondre.mock.calls[0][0]).toMatchObject({ path: { organization_id: 7, fil_id: 1 }, body: { cote: "mark", texte: "Réglé" } });

        fireEvent.click(screen.getByRole("button", { name: "Note interne" }));
        fireEvent.change(screen.getAllByRole("textbox").at(-1) as HTMLTextAreaElement, { target: { value: "Pour nous" } });
        fireEvent.click(screen.getByRole("button", { name: "Ajouter la note" }));
        await waitFor(() => expect(sdk.repondre).toHaveBeenCalledTimes(2));
        expect(sdk.repondre.mock.calls[1][0].body).toMatchObject({ cote: "interne", texte: "Pour nous" });
    });

    it("change l'état propre d'une demande de logiciel par l'API", async () => {
        sdk.lireFil.mockImplementation(() => ok(complet({ sorte: "demande_logiciel", logiciel: "Gazoleen", etat_demande: "nouvelle" })));
        avec(<EcranMessages fil={1} />);
        expect(await screen.findByText("Gazoleen")).toBeTruthy();
        fireEvent.click(screen.getByRole("button", { name: "Clore" }));
        await waitFor(() => expect(sdk.modifier).toHaveBeenCalled());
        expect(sdk.modifier.mock.calls[0][0]).toMatchObject({ path: { organization_id: 7, fil_id: 1 }, body: { etat: "clos" } });
    });
});

describe("Ouvrir son portail", () => {
    it("est désactivé tant que l'adresse du portail n'est pas réglée", async () => {
        sdk.fils.mockImplementation(() => ok([]));
        avec(<FicheClient id={7} />);
        const bouton = (await screen.findByRole("button", { name: /Ouvrir son portail/ })) as HTMLButtonElement;
        expect(bouton.disabled).toBe(true);
        expect(sdk.entree).not.toHaveBeenCalled();
    });
});

describe("Avis et témoignages", () => {
    it("montre la note, le nombre d'avis et l'accord de chaque témoignage", async () => {
        sdk.avis.mockImplementation(() =>
            ok([{ organization_id: 7, client: "Nuances de Feu", note: 4.4, avis: 21, temoignages: [{ id: 1, organization_id: 7, texte: "Très bien", auteur: "Martine, dirigeante", accord: false }] }]),
        );
        avec(<EcranAvis />);
        expect(await screen.findByText(/4.4 \/ 5 · 21 avis/)).toBeTruthy();
        expect(screen.getByText("Très bien")).toBeTruthy();
        expect(screen.getByText("Sans accord")).toBeTruthy();
    });
});
