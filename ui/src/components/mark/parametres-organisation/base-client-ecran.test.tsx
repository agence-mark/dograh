/**
 * [.mark] The client's database on screen (chantier l-agent-travaille, L3), rendered.
 *
 *   - « Client data », nothing attached: a name, « Create database » sends THAT name, the
 *     state that comes back is shown (version, last write); never a password field (B4);
 *   - attached and behind: « Upgrade » appears; refusals of the database are listed and
 *     put the theme's red dot on;
 *   - the retention is saved by its own button, with exactly the durations typed;
 *   - « Team and routing » without a database says where to attach it; with one, the modal
 *     loads the team, adds a person and saves exactly what is on screen.
 */
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import type { ReactNode } from "react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { FournisseurLangue } from "../langue/langue";
import { ThemeDonneesClient, useBaseClient } from "./ThemeDonneesClient";
import { charge_utile_equipe, ThemeEquipe } from "./ThemeEquipe";

const m = vi.hoisted(() => ({
    etat: vi.fn(),
    rattacher: vi.fn(),
    creer: vi.fn(),
    niveau: vi.fn(),
    resync: vi.fn(),
    conservation: vi.fn(),
    equipe: vi.fn(),
    saveEquipe: vi.fn(),
    choix: vi.fn(),
}));

vi.mock("@/client/sdk.gen", async (importOriginal) => (await import("../sdk-factice")).sdkFactice(await importOriginal(), {
    getBaseClientApiV1OrganizationsBaseClientGet: m.etat,
    putBaseClientApiV1OrganizationsBaseClientPut: m.rattacher,
    postCreerApiV1OrganizationsBaseClientCreerPost: m.creer,
    postMettreANiveauApiV1OrganizationsBaseClientMettreANiveauPost: m.niveau,
    postResynchroniserApiV1OrganizationsBaseClientResynchroniserPost: m.resync,
    putConservationApiV1OrganizationsBaseClientConservationPut: m.conservation,
    getEquipeApiV1OrganizationsEquipeGet: m.equipe,
    putEquipeApiV1OrganizationsEquipePut: m.saveEquipe,
    getChoixTraducteursApiV1ConnecteursTraducteursChoixGet: m.choix,
    getTraducteursApiV1ConnecteursTraducteursGet: () =>
        Promise.resolve({
            data: [{ systeme: "google_agenda", libelle: "Google Agenda", domaine: "agenda", integration: "google-calendar",
                     reference_agenda: { en: "Calendar ID", fr: "Identifiant de l'agenda" }, operations: {} }],
        }),
    getEtablissementsApiV1OrganizationsEtablissementsGet: () =>
        Promise.resolve({ data: { format: "etablissements-mark", version: 1, etablissements: [{ id: "creil", nom: "Site A", numeros: [] }] } }),
}));
vi.mock("sonner", () => ({ toast: { success: vi.fn(), error: vi.fn() } }));
vi.mock("@/lib/auth", () => ({ useAuth: () => ({ user: { id: 1 }, loading: false }) }));
vi.mock("@/components/ui/dialog", () => ({
    Dialog: ({ open, children }: { open: boolean; children: ReactNode }) => (open ? <div>{children}</div> : null),
    DialogContent: ({ children }: { children: ReactNode }) => <div>{children}</div>,
    DialogDescription: ({ children }: { children: ReactNode }) => <p>{children}</p>,
    DialogFooter: ({ children }: { children: ReactNode }) => <div>{children}</div>,
    DialogHeader: ({ children }: { children: ReactNode }) => <div>{children}</div>,
    DialogTitle: ({ children }: { children: ReactNode }) => <h2>{children}</h2>,
}));

const SANS_BASE = { serveur_configure: true, nom_base: null, joignable: false, version: null, version_attendue: 3, refus: [], conservation: [] };
const RATTACHEE = {
    serveur_configure: true,
    nom_base: "client_essai",
    joignable: true,
    version: 3,
    version_attendue: 3,
    derniere_ecriture: "2026-10-06T21:00:00Z",
    refus: [],
    conservation: [{ table_nom: "appel", duree_jours: 365, colonne_date: "debut", source: "défaut" }],
};

afterEach(() => {
    cleanup();
    vi.clearAllMocks();
});

const Donnees = ({ signaler = vi.fn() }: { signaler?: (id: string, modifie: boolean, enErreur: boolean) => void }) => {
    const base = useBaseClient();
    return <ThemeDonneesClient ouvert onBasculer={() => {}} ouvrir={() => {}} signaler={signaler} base={base} />;
};

const rendre = (noeud: ReactNode) => render(<FournisseurLangue>{noeud}</FournisseurLangue>);

describe("Client data", () => {
    it("creates the database under the typed name, and shows the state that comes back", async () => {
        m.etat.mockResolvedValue({ data: SANS_BASE });
        m.creer.mockResolvedValue({ data: RATTACHEE });
        rendre(<Donnees />);
        const champ = (await screen.findByLabelText(/Database name|Nom de la base/)) as HTMLInputElement;
        expect(document.querySelector('input[type="password"]')).toBeNull();
        fireEvent.change(champ, { target: { value: "client_essai" } });
        fireEvent.click(screen.getByTestId("creer-base-client"));
        await waitFor(() => expect(m.creer).toHaveBeenCalledWith({ body: { nom_base: "client_essai" } }));
        const etat = await screen.findByTestId("etat-base-client");
        expect(etat.textContent).toContain("client_essai");
        expect(etat.textContent).toContain("3 / 3");
        expect(screen.queryByTestId("mettre-a-niveau-base-client")).toBeNull();
    });

    it("says in the screen's language that a taken name is refused (409), never the server's English", async () => {
        m.etat.mockResolvedValue({ data: SANS_BASE });
        m.creer.mockResolvedValue({ error: { detail: "« client_essai » is attached to another organization" }, response: { status: 409 } });
        rendre(<Donnees />);
        const champ = (await screen.findByLabelText(/Database name|Nom de la base/)) as HTMLInputElement;
        fireEvent.change(champ, { target: { value: "client_essai" } });
        fireEvent.click(screen.getByTestId("creer-base-client"));
        const erreur = await screen.findByTestId("erreur-base-client");
        expect(erreur.textContent).toMatch(/Ce nom de base est déjà pris|This database name is taken/);
        expect(erreur.textContent).not.toContain("attached to another organization");
    });

    it("offers Upgrade when the connection account has no rights in the database yet (n° 317)", async () => {
        m.etat.mockResolvedValue({ data: { ...RATTACHEE, joignable: false, version: null, a_mettre_a_niveau: true, erreur: "upgrade the database" } });
        rendre(<Donnees />);
        expect(await screen.findByTestId("mettre-a-niveau-base-client")).toBeTruthy();
    });

    it("offers Upgrade when behind, lists the refusals and lights the red dot", async () => {
        const signaler = vi.fn();
        m.etat.mockResolvedValue({ data: { ...RATTACHEE, version: 2, refus: ["Site A: hours refused (ligne 1)"] } });
        rendre(<Donnees signaler={signaler} />);
        expect(await screen.findByTestId("mettre-a-niveau-base-client")).toBeTruthy();
        expect(screen.getByTestId("refus-base-client").textContent).toContain("Site A: hours refused");
        await waitFor(() => expect(signaler).toHaveBeenCalledWith("donnees", false, true));
    });

    it("saves the retention by its own button, with the durations typed", async () => {
        m.etat.mockResolvedValue({ data: RATTACHEE });
        m.conservation.mockImplementation(async ({ body }) => ({ data: { ...RATTACHEE, conservation: body } }));
        rendre(<Donnees />);
        const bouton = (await screen.findByTestId("enregistrer-conservation")) as HTMLButtonElement;
        expect(bouton.disabled).toBe(true);
        fireEvent.change(document.getElementById("conservation-appel")!, { target: { value: "90" } });
        expect(bouton.disabled).toBe(false);
        fireEvent.click(bouton);
        await waitFor(() =>
            expect(m.conservation).toHaveBeenCalledWith({ body: [{ ...RATTACHEE.conservation[0], duree_jours: 90 }] }),
        );
    });
});

describe("Team and routing", () => {
    it("without a database, says where to attach one", () => {
        rendre(<ThemeEquipe ouvert onBasculer={() => {}} ouvrir={() => {}} signaler={vi.fn()} baseRattachee={false} />);
        expect(screen.getByTestId("equipe-sans-base")).toBeTruthy();
        expect(screen.queryByTestId("ouvrir-equipe")).toBeNull();
    });

    it("loads the team, adds a person and saves exactly what is on screen", async () => {
        m.equipe.mockResolvedValue({
            data: { personnes: [{ cle: "p1", prenom: "Alice", etablissement: "creil", actif: true }], sujets: [] },
        });
        m.saveEquipe.mockImplementation(async ({ body }) => ({ data: body }));
        rendre(<ThemeEquipe ouvert onBasculer={() => {}} ouvrir={() => {}} signaler={vi.fn()} baseRattachee />);
        fireEvent.click(screen.getByTestId("ouvrir-equipe"));
        await screen.findByDisplayValue("Alice");
        fireEvent.click(screen.getByTestId("ajouter-personne"));
        const enregistrer = screen.getByTestId("enregistrer-equipe") as HTMLButtonElement;
        expect(enregistrer.disabled).toBe(true); // a person without a first name
        const prenoms = screen.getAllByLabelText(/First name|Prénom/) as HTMLInputElement[];
        fireEvent.change(prenoms[1], { target: { value: " Bruno " } });
        fireEvent.click(enregistrer);
        await waitFor(() => expect(m.saveEquipe).toHaveBeenCalledTimes(1));
        const envoye = m.saveEquipe.mock.calls[0][0].body;
        expect(envoye.personnes.map((p: { prenom: string }) => p.prenom)).toEqual(["Alice", "Bruno"]);
        expect(envoye.personnes[1].cle).toBe("personne-2");
    });

    it("l-agent-collegue C1: description, transfer and disclosures are on screen and saved as set", async () => {
        m.equipe.mockResolvedValue({
            data: { personnes: [{ cle: "p1", prenom: "Alice", etablissement: "creil", actif: true }], sujets: [] },
        });
        m.saveEquipe.mockReset();
        m.saveEquipe.mockImplementation(async ({ body }) => ({ data: body }));
        rendre(<ThemeEquipe ouvert onBasculer={() => {}} ouvrir={() => {}} signaler={vi.fn()} baseRattachee />);
        fireEvent.click(screen.getByTestId("ouvrir-equipe"));
        await screen.findByDisplayValue("Alice");
        const description = screen.getByLabelText(/What this person takes care of|Ce dont cette personne s'occupe/) as HTMLTextAreaElement;
        expect(description.maxLength).toBe(300);
        fireEvent.change(description, { target: { value: "  Les rendez-vous et les factures.  " } });
        const transfert = screen.getByLabelText(/may transfer calls|lui transférer un appel/) as HTMLInputElement;
        expect(transfert.checked).toBe(false); // off by default (C1)
        fireEvent.click(transfert);
        // No phone: the modal says the agent will pass the request on instead.
        expect(screen.getByTestId("transfert-sans-telephone")).toBeTruthy();
        fireEvent.click(screen.getByLabelText(/may give the e-mail|donner son e-mail/));
        expect((screen.getByLabelText(/may give the phone|donner son téléphone/) as HTMLInputElement).checked).toBe(false);
        fireEvent.click(screen.getByTestId("enregistrer-equipe"));
        await waitFor(() => expect(m.saveEquipe).toHaveBeenCalledTimes(1));
        expect(m.saveEquipe.mock.calls[0][0].body.personnes[0]).toMatchObject({
            description: "Les rendez-vous et les factures.",
            joignable_par_transfert: true,
            divulguer_mail: true,
            divulguer_telephone: false,
        });
    });

    it("l-agent-collegue L4 (H7): the person's agenda in the software chosen, saved as typed", async () => {
        m.equipe.mockResolvedValue({
            data: { personnes: [{ cle: "p1", prenom: "Alice", actif: true, agendas: { outlook_agenda: "a@x.org" } }], sujets: [] },
        });
        m.saveEquipe.mockReset();
        m.saveEquipe.mockImplementation(async ({ body }) => ({ data: body }));
        // Nothing chosen in « Integrations »: no agenda field (E8, it plays no role).
        m.choix.mockResolvedValue({ data: { agenda: null } });
        rendre(<ThemeEquipe ouvert onBasculer={() => {}} ouvrir={() => {}} signaler={vi.fn()} baseRattachee />);
        fireEvent.click(screen.getByTestId("ouvrir-equipe"));
        await screen.findByDisplayValue("Alice");
        expect(screen.queryByTestId("agenda-p1")).toBeNull();
        cleanup();

        m.choix.mockResolvedValue({ data: { agenda: "google_agenda" } });
        rendre(<ThemeEquipe ouvert onBasculer={() => {}} ouvrir={() => {}} signaler={vi.fn()} baseRattachee />);
        fireEvent.click(screen.getByTestId("ouvrir-equipe"));
        const champ = (await screen.findByTestId("agenda-p1")) as HTMLInputElement;
        expect(screen.getByText(/Identifiant de l'agenda|Calendar ID/)).toBeTruthy();
        fireEvent.change(champ, { target: { value: " alice@example.org " } });
        fireEvent.click(screen.getByTestId("enregistrer-equipe"));
        await waitFor(() => expect(m.saveEquipe).toHaveBeenCalledTimes(1));
        // The other software's agenda is kept; the one typed is trimmed.
        expect(m.saveEquipe.mock.calls[0][0].body.personnes[0].agendas).toEqual({
            outlook_agenda: "a@x.org",
            google_agenda: "alice@example.org",
        });
    });

    it("the payload trims, and empties become null", () => {
        const charge = charge_utile_equipe({
            personnes: [{ cle: "p1", prenom: " A ", nom: "  ", mail: "", etablissement: "" }],
            sujets: [{ code: "devis", libelle: " Devis ", mots_declencheurs: [" prix ", ""] }],
        });
        expect(charge.personnes?.[0]).toMatchObject({ prenom: "A", nom: null, mail: null, etablissement: null });
        expect(charge.sujets?.[0]).toMatchObject({ libelle: "Devis", mots_declencheurs: ["prix"] });
    });
});
