/**
 * [.mark] K4 : les sous-onglets Entreprise à la forme de la maquette (tableaux nus, une fenêtre par objet).
 *
 *   - Équipe et routage : les deux tableaux, la fenêtre d'un sujet (ordre des clics), la fenêtre d'une personne ;
 *     l'écriture renvoie l'équipe ENTIÈRE avec la ligne changée (la route remplace tout) ;
 *   - Rendez-vous : le tableau des types, l'interrupteur « Proposé » agit seul, une section en lignes et sa fenêtre ;
 *   - Établissements : « + Établissement » ouvre la fenêtre d'une fiche neuve, un clic sur une ligne ouvre CETTE fiche.
 */
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { FournisseurLangue } from "../langue/langue";

const m = vi.hoisted(() => ({
    equipe: vi.fn(),
    ecrireEquipe: vi.fn(),
    planif: vi.fn(),
    ecrirePlanif: vi.fn(),
    etablissements: vi.fn(),
    ecrireEtablissements: vi.fn(),
}));

vi.mock("@/client/sdk.gen", async (importOriginal) =>
    (await import("../sdk-factice")).sdkFactice(await importOriginal(), {
        getEquipeApiV1OrganizationsEquipeGet: m.equipe,
        putEquipeApiV1OrganizationsEquipePut: m.ecrireEquipe,
        getPlanificateurApiV1OrganizationsPlanificateurGet: m.planif,
        putPlanificateurApiV1OrganizationsPlanificateurPut: m.ecrirePlanif,
        getEtablissementsApiV1OrganizationsEtablissementsGet: m.etablissements,
        saveEtablissementsApiV1OrganizationsEtablissementsPut: m.ecrireEtablissements,
        getDernieresModificationsApiV1OrganizationsEtablissementsDernieresModificationsGet: () => Promise.resolve({ data: [] }),
        getPhrasesApiV1OrganizationsPhrasesGet: () => Promise.resolve({ data: { phrases: [] } }),
    }),
);
vi.mock("sonner", () => ({ toast: { success: vi.fn(), error: vi.fn() } }));
vi.mock("@/lib/auth", () => ({ useAuth: () => ({ user: { id: 1 }, loading: false }) }));
vi.stubGlobal("ResizeObserver", class { observe() {} unobserve() {} disconnect() {} });
Element.prototype.hasPointerCapture = vi.fn(() => false);
Element.prototype.scrollIntoView = vi.fn();

const { OngletEquipe } = await import("./OngletEquipe");
const { OngletRendezVous } = await import("./OngletRendezVous");
const { ModaleEtablissements } = await import("../parametres-organisation/ModaleEtablissements");

const EQUIPE = {
    personnes: [
        { cle: "sophie", prenom: "Sophie", nom: "Marchand", role: "Accueil", actif: true, destinataire_defaut: true, etablissements: [] },
        { cle: "marc", prenom: "Marc", nom: "Lefèvre", role: "Technicien", actif: true, destinataire_defaut: false, etablissements: ["nord"], joignable_par_transfert: true },
    ],
    sujets: [{ code: "sav", libelle: "SAV", mots_declencheurs: ["panne"], urgent: false, actif: true, destinataires: ["marc"] }],
};
const FICHES = { format: "etablissements-mark", version: 1, etablissements: [{ id: "nord", nom: "Nord", horaires_ouverture: "lundi : fermé" }] };
const PLAN = {
    reglages: {},
    par_etablissement: { nord: { nombre_creneaux: 3 } },
    defauts: { nombre_creneaux: 3, pas_min: 30 },
    types: [{ code: "entretien", etablissement: "nord", libelle: "Entretien annuel", duree_min: 60, sujet: "sav", marge_avant_min: 15, marge_apres_min: 15, actif: true }],
};

const rendre = (noeud: React.ReactNode) => render(<FournisseurLangue>{noeud}</FournisseurLangue>);
const reinitialiser = () => {
    m.equipe.mockReset().mockImplementation(() => Promise.resolve({ data: structuredClone(EQUIPE) }));
    m.ecrireEquipe.mockReset().mockImplementation(() => Promise.resolve({ data: {} }));
    m.planif.mockReset().mockImplementation(() => Promise.resolve({ data: structuredClone(PLAN) }));
    m.ecrirePlanif.mockReset().mockImplementation(({ body }: { body: unknown }) => Promise.resolve({ data: structuredClone(body) }));
    m.etablissements.mockReset().mockImplementation(() => Promise.resolve({ data: structuredClone(FICHES) }));
    m.ecrireEtablissements.mockReset().mockImplementation(() => Promise.resolve({ data: {} }));
};
reinitialiser();
afterEach(() => {
    cleanup();
    reinitialiser();
});

describe("[.mark] K4 : Équipe et routage", () => {
    it("montre les deux tableaux, et un clic sur un sujet ouvre la fenêtre de CE sujet", async () => {
        rendre(<OngletEquipe baseRattachee />);
        expect((await screen.findAllByText("Marc Lefèvre")).length).toBeGreaterThan(0);
        expect(screen.getByText("Routage par sujet")).toBeTruthy();
        // Le routage dit « Reçu par, dans l'ordre » : le nom, jamais la clé technique.
        const ligne = screen.getByText("SAV").closest("tr") as HTMLElement;
        expect(ligne.textContent).toContain("Marc Lefèvre");
        fireEvent.click(ligne);
        expect(await screen.findByDisplayValue("SAV")).toBeTruthy();
    });

    it("enregistre l'équipe entière avec le sujet changé : l'ordre des clics fait l'ordre des destinataires", async () => {
        rendre(<OngletEquipe baseRattachee />);
        fireEvent.click((await screen.findByText("SAV")).closest("tr") as HTMLElement);
        await screen.findByDisplayValue("SAV");
        // Marc est déjà reçu ; on ajoute Sophie (après lui).
        fireEvent.click(screen.getByRole("button", { name: "Sophie Marchand" }));
        fireEvent.click(screen.getByRole("button", { name: /Enregistrer|Save/ }));
        await waitFor(() => expect(m.ecrireEquipe).toHaveBeenCalledTimes(1));
        const corps = m.ecrireEquipe.mock.calls[0][0].body;
        expect(corps.personnes).toHaveLength(2);
        expect(corps.sujets[0].destinataires).toEqual(["marc", "sophie"]);
    });

    it("sans base rattachée : un état vide, rien à modifier", () => {
        rendre(<OngletEquipe baseRattachee={false} />);
        expect(screen.getByTestId("equipe-sans-base")).toBeTruthy();
        expect(screen.queryByTestId("ajouter-personne")).toBeNull();
    });

    it("refuse une personne sans prénom, sous le champ, sans rien écrire", async () => {
        rendre(<OngletEquipe baseRattachee />);
        fireEvent.click(await screen.findByTestId("ajouter-personne"));
        fireEvent.click(await screen.findByRole("button", { name: /Enregistrer|Save/ }));
        expect(await screen.findByText(/prénom est obligatoire|first name is required/i)).toBeTruthy();
        expect(m.ecrireEquipe).not.toHaveBeenCalled();
    });
});

describe("[.mark] K4 : Rendez-vous", () => {
    it("le tableau des types du niveau, et l'interrupteur « Proposé » écrit seul", async () => {
        rendre(<OngletRendezVous baseRattachee />);
        // Le niveau de départ est « les valeurs de départ » : on choisit l'établissement.
        expect(await screen.findByText("Types de rendez-vous")).toBeTruthy();
        expect(screen.getByText(/Valeurs de départ/)).toBeTruthy();
        fireEvent.pointerDown(screen.getAllByRole("combobox")[0], { button: 0, ctrlKey: false });
        fireEvent.click(screen.getAllByRole("combobox")[0]);
        fireEvent.click(await screen.findByRole("option", { name: "Nord" }));
        const ligne = (await screen.findByText("Entretien annuel")).closest("tr") as HTMLElement;
        expect(ligne.textContent).toContain("60 min");
        fireEvent.click(ligne.querySelector('[role="switch"]') as HTMLElement);
        await waitFor(() => expect(m.ecrirePlanif).toHaveBeenCalledTimes(1));
        expect(m.ecrirePlanif.mock.calls[0][0].body.types[0]).toMatchObject({ code: "entretien", actif: false });
    });

    it("une section en lignes : « Modifier » ouvre sa fenêtre, une valeur vide s'écrit « défaut » (null)", async () => {
        rendre(<OngletRendezVous baseRattachee />);
        await screen.findByText("Créneaux");
        fireEvent.click(screen.getByText("Créneaux").closest("section")!.querySelector("button") as HTMLElement);
        const champ = await screen.findByLabelText("Créneaux proposés");
        fireEvent.change(champ, { target: { value: "" } });
        fireEvent.click(screen.getByRole("button", { name: /Enregistrer|Save/ }));
        await waitFor(() => expect(m.ecrirePlanif).toHaveBeenCalledTimes(1));
        expect(m.ecrirePlanif.mock.calls[0][0].body.reglages.nombre_creneaux).toBeNull();
    });
});

describe("[.mark] K4 : fenêtre d'UNE fiche d'établissement", () => {
    const ouvrir = (fiche: string) =>
        rendre(<ModaleEtablissements ouverte fiche={fiche} onFermer={() => {}} adresseOrganisation={null} annonceOrganisation={{ annonce_fermeture: "", annonce_pause: "", etat_force: null, etat_force_jusqu_a: null }} />);

    it("« nouveau » ouvre une fiche neuve, sans la liste des autres, et l'enregistre avec elles", async () => {
        ouvrir("nouveau");
        expect(await screen.findByDisplayValue(/New establishment|Nouvel établissement/)).toBeTruthy();
        expect(screen.queryByTestId("liste-etablissements")).toBeNull();
        fireEvent.click(screen.getByTestId("enregistrer-etablissements"));
        await waitFor(() => expect(m.ecrireEtablissements).toHaveBeenCalledTimes(1));
        expect(m.ecrireEtablissements.mock.calls[0][0].body.etablissements).toHaveLength(2);
    });

    it("une fiche existante : titre = son nom, « Retirer » demande confirmation puis écrit la liste sans elle", async () => {
        ouvrir("nord");
        await screen.findByDisplayValue("Nord");
        expect(screen.queryByTestId("liste-etablissements")).toBeNull();
        const retirer = screen.getByTestId("retirer-etablissement");
        fireEvent.click(retirer);
        expect(m.ecrireEtablissements).not.toHaveBeenCalled();
        fireEvent.click(retirer);
        await waitFor(() => expect(m.ecrireEtablissements).toHaveBeenCalledTimes(1));
        expect(m.ecrireEtablissements.mock.calls[0][0].body.etablissements).toHaveLength(0);
    });
});
