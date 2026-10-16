/**
 * [.mark] The complete fiche on screen (chantier agents-specialises, lot 11 = lot 4 of the fiche plan;
 * convention `22-convention-ecran.md` § 5, items 5, 6 and 8: display condition, payload tested, the element
 * found in the rendered window).
 *
 *   - the fiche's immediate closing (C5): drawn, payload as chosen, a date only with a state, untouched saved as read;
 *   - the fiche's appointments and zone (M2): every setting drawn with its bounds and default, written WITH the
 *     fiche (fiches first, then the planner), nothing written when untouched, said when there is no client database;
 *   - « Create by copy » (F2): the request, the list read again, the notice of what was not copied, refused while
 *     something waits to be saved;
 *   - the takeover: the trial run first, written only on the second click, what it cannot decide listed apart;
 *   - the places of a person: boxes, none ticked = the whole company (M5), both fields emptied;
 *   - the test window: the choice of the establishment only for an agent without a fiche (C8).
 */
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import type { ReactNode } from "react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { ChoixEtablissementEssai } from "../etablissements/ChoixEtablissementEssai";
import { FournisseurLangue } from "../langue/langue";
import { ModaleEtablissements } from "./ModaleEtablissements";
import { ModaleReprise } from "./ModaleReprise";
import { charge_utile_equipe, lieuxDe, ThemeEquipe } from "./ThemeEquipe";

const m = vi.hoisted(() => ({
    get: vi.fn(),
    save: vi.fn(),
    phrases: vi.fn(),
    planif: vi.fn(),
    putPlanif: vi.fn(),
    copier: vi.fn(),
    reprise: vi.fn(),
    equipe: vi.fn(),
    saveEquipe: vi.fn(),
    ordre: [] as string[],
}));

vi.mock("@/client/sdk.gen", async (importOriginal) => (await import("../sdk-factice")).sdkFactice(await importOriginal(), {
    getEtablissementsApiV1OrganizationsEtablissementsGet: m.get,
    saveEtablissementsApiV1OrganizationsEtablissementsPut: m.save,
    getPhrasesApiV1OrganizationsPhrasesGet: m.phrases,
    getPlanificateurApiV1OrganizationsPlanificateurGet: m.planif,
    putPlanificateurApiV1OrganizationsPlanificateurPut: m.putPlanif,
    copierEtablissementApiV1OrganizationsEtablissementsCopierPost: m.copier,
    repriseDesFichesApiV1OrganizationsEtablissementsReprisePost: m.reprise,
    getEquipeApiV1OrganizationsEquipeGet: m.equipe,
    putEquipeApiV1OrganizationsEquipePut: m.saveEquipe,
    getChoixTraducteursApiV1ConnecteursTraducteursChoixGet: () => Promise.resolve({ data: { agenda: null } }),
    getTraducteursApiV1ConnecteursTraducteursGet: () => Promise.resolve({ data: [] }),
    getCommunesDuCodePostalApiV1OrganizationsCommunesGet: () => Promise.resolve({ data: [{ code_insee: "60612", nom: "Senlis" }] }),
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

const CREIL = {
    id: "creil",
    nom: "Magasin de Creil",
    numeros: ["+33344000001"],
    second_numero: null,
    numero_transfert: null,
    adresse: null,
    horaires_ouverture: null,
    annonce_fermeture: null,
    annonce_pause: null,
    phrases: {},
    termes_lexique: [],
};
const SENLIS = { ...CREIL, id: "senlis", nom: "Magasin de Senlis", numeros: [] };
const ANNONCE = { annonce_fermeture: "Fermé.", annonce_pause: "En pause.", etat_force: null, etat_force_jusqu_a: null };
const DEFAUTS = {
    nombre_creneaux: 3,
    delai_minimal_h: 24,
    horizon_jours: 14,
    pas_min: 30,
    trajets_comptes: false,
    coefficient_trajet: 1.3,
    vitesse_kmh: 50,
    repartition: "premier_libre",
    repli: "humain_puis_rappel",
    personne_visible: false,
    jours_feries: "metropole",
    fenetre_equite_jours: 30,
};
const PLANIFICATEUR = { reglages: {}, par_etablissement: {}, types: [], defauts: DEFAUTS };

const catalogue = (...fiches: unknown[]) => ({ data: { format: "etablissements-mark", version: 1, etablissements: fiches } });

const reinitialiser = () => {
    m.ordre = [];
    m.get.mockReset().mockResolvedValue(catalogue(CREIL));
    m.save.mockReset().mockImplementation(async ({ body }) => {
        m.ordre.push("etablissements");
        return { data: body };
    });
    m.phrases.mockReset().mockResolvedValue({ data: { format: "phrases-mark", version: 1, phrases: [] } });
    m.planif.mockReset().mockResolvedValue({ data: PLANIFICATEUR });
    m.putPlanif.mockReset().mockImplementation(async ({ body }) => {
        m.ordre.push("planificateur");
        return { data: { ...body, defauts: DEFAUTS } };
    });
    m.copier.mockReset();
    m.reprise.mockReset();
    m.equipe.mockReset();
    m.saveEquipe.mockReset().mockImplementation(async ({ body }) => ({ data: body }));
};
reinitialiser();
afterEach(() => {
    cleanup();
    reinitialiser();
    window.localStorage.clear();
});

const ouvrir = async (onFermer = vi.fn()) => {
    window.localStorage.setItem("mark.langue", "en");
    render(
        <FournisseurLangue>
            <ModaleEtablissements ouverte onFermer={onFermer} adresseOrganisation={null} annonceOrganisation={ANNONCE} />
        </FournisseurLangue>,
    );
    await waitFor(() => expect(screen.getByTestId("fiche-etablissement")).toBeTruthy());
    await waitFor(() => expect(m.planif).toHaveBeenCalled());
    return onFermer;
};
const reglage = (cle: string) => document.querySelector(`[data-reglage="${cle}"]`);
const enregistrer = () => screen.getByTestId("enregistrer-etablissements");

describe("[.mark] the fiche's immediate closing (C5)", () => {
    it("is drawn with its default, and found in the window", async () => {
        await ouvrir();
        expect(document.getElementById("fiche-fermeture")).not.toBeNull();
        expect(reglage("fiche.etat_force")).not.toBeNull();
        expect(reglage("fiche.etat_force")?.textContent).toContain("Default: computed from the hours");
        expect((document.getElementById("fiche-etat-force") as HTMLSelectElement).value).toBe("");
        // The date only means something with a state (the server refuses it alone): not drawn without one.
        expect(reglage("fiche.etat_force_jusqu_a")).toBeNull();
    });

    it("sends the state and its end, and clears both when it goes back to computed", async () => {
        await ouvrir();
        fireEvent.change(document.getElementById("fiche-etat-force")!, { target: { value: "FERME" } });
        expect(reglage("fiche.etat_force_jusqu_a")).not.toBeNull();
        fireEvent.change(document.getElementById("fiche-etat-force-jusqua")!, { target: { value: "2026-12-26T09:00" } });
        fireEvent.click(enregistrer());
        await waitFor(() => expect(m.save).toHaveBeenCalledTimes(1));
        expect(m.save.mock.calls[0][0].body.etablissements[0]).toMatchObject({ etat_force: "FERME", etat_force_jusqu_a: "2026-12-26T09:00" });

        cleanup();
        reinitialiser();
        m.get.mockResolvedValue(catalogue({ ...CREIL, etat_force: "FERME", etat_force_jusqu_a: "2026-12-26T09:00:00" }));
        await ouvrir();
        expect((document.getElementById("fiche-etat-force-jusqua") as HTMLInputElement).value).toBe("2026-12-26T09:00");
        fireEvent.change(document.getElementById("fiche-etat-force")!, { target: { value: "" } });
        fireEvent.click(enregistrer());
        await waitFor(() => expect(m.save).toHaveBeenCalledTimes(1));
        expect(m.save.mock.calls[0][0].body.etablissements[0]).toMatchObject({ etat_force: null, etat_force_jusqu_a: null });
    });

    it("keeps a closing it read when the fiche is saved untouched (never wiped by a save)", async () => {
        const fermee = { ...CREIL, etat_force: "PAUSE", etat_force_jusqu_a: "2026-12-26T09:00:00" };
        m.get.mockResolvedValue(catalogue(fermee));
        await ouvrir();
        fireEvent.click(enregistrer());
        await waitFor(() => expect(m.save).toHaveBeenCalledTimes(1));
        expect(m.save.mock.calls[0][0].body.etablissements[0]).toEqual(fermee);
    });
});

describe("[.mark] the fiche's appointments and zone (M2)", () => {
    const CLES = [
        "nombre_creneaux", "delai_minimal_h", "horizon_jours", "pas_min", "plages", "jours_feries", "repartition",
        "fenetre_equite_jours", "personne_visible", "repli",
        "trajets_comptes", "coefficient_trajet", "vitesse_kmh", "zone_rayon_km", "zone_communes",
    ];

    it("draws every setting of both groups, with its bounds and its default, and finds each in the window", async () => {
        await ouvrir();
        expect(document.getElementById("fiche-rendez-vous")).not.toBeNull();
        expect(document.getElementById("fiche-zone")).not.toBeNull();
        for (const cle of CLES) expect(reglage(`par_etablissement.${cle}`), cle).not.toBeNull();
        // Bounds and defaults, as the theme « Appointments » says them.
        expect(reglage("par_etablissement.nombre_creneaux")?.textContent).toContain("≥ 1 · ≤ 6");
        expect((document.getElementById("fiche-rdv-creil-nombre_creneaux") as HTMLInputElement).placeholder).toBe("default : 3");
        expect((document.getElementById("fiche-rdv-creil-repartition") as HTMLSelectElement).options[0].textContent).toContain("First free");
        // Nothing inherited from the organization (C3): the fiche says so.
        expect(document.getElementById("fiche-rendez-vous")?.textContent).toContain("nothing is inherited from the organization");
    });

    it("writes the fiches first, then the planner level of the fiche", async () => {
        await ouvrir();
        fireEvent.change(document.getElementById("fiche-rdv-creil-nombre_creneaux")!, { target: { value: "5" } });
        fireEvent.change(document.getElementById("fiche-rdv-creil-zone_rayon_km")!, { target: { value: "25" } });
        fireEvent.change(document.getElementById("fiche-rdv-creil-zone_communes")!, { target: { value: "60057, 60175" } });
        fireEvent.change(document.getElementById("fiche-rdv-creil-repartition")!, { target: { value: "tour_de_role" } });
        fireEvent.click(enregistrer());
        await waitFor(() => expect(m.putPlanif).toHaveBeenCalledTimes(1));
        expect(m.ordre).toEqual(["etablissements", "planificateur"]);
        const envoye = m.putPlanif.mock.calls[0][0].body;
        expect(envoye.par_etablissement.creil).toEqual({ nombre_creneaux: 5, zone_rayon_km: 25, zone_communes: ["60057", "60175"], repartition: "tour_de_role" });
        // The organization's level and the types go back as they were read.
        expect(envoye.reglages).toEqual({});
        expect(envoye.types).toEqual([]);
    });

    it("an empty field goes back to null, and an untouched save writes no planner at all", async () => {
        await ouvrir();
        fireEvent.click(enregistrer());
        await waitFor(() => expect(m.save).toHaveBeenCalledTimes(1));
        expect(m.putPlanif).not.toHaveBeenCalled();

        cleanup();
        reinitialiser();
        m.planif.mockResolvedValue({ data: { ...PLANIFICATEUR, par_etablissement: { creil: { nombre_creneaux: 5 } } } });
        await ouvrir();
        expect((document.getElementById("fiche-rdv-creil-nombre_creneaux") as HTMLInputElement).value).toBe("5");
        fireEvent.change(document.getElementById("fiche-rdv-creil-nombre_creneaux")!, { target: { value: "" } });
        fireEvent.click(enregistrer());
        await waitFor(() => expect(m.putPlanif).toHaveBeenCalledTimes(1));
        expect(m.putPlanif.mock.calls[0][0].body.par_etablissement.creil.nombre_creneaux).toBeNull();
    });

    it("says the rules live in the client's database when there is none, and still saves the fiche", async () => {
        m.planif.mockResolvedValue({ error: { detail: "Attach a client database first: the team lives there." } });
        await ouvrir();
        expect(screen.getByTestId("fiche-rdv-sans-base").textContent).toContain("live in the client's database");
        expect(reglage("par_etablissement.nombre_creneaux")).toBeNull();
        fireEvent.change(screen.getByLabelText("Name"), { target: { value: "Creil centre" } });
        fireEvent.click(enregistrer());
        await waitFor(() => expect(m.save).toHaveBeenCalledTimes(1));
        expect(m.putPlanif).not.toHaveBeenCalled();
    });

    it("keeps the window open and says it when the planner is refused after the fiches were saved", async () => {
        m.putPlanif.mockResolvedValue({ error: { detail: "Booking ranges (creil): ligne 1 : heure illisible" } });
        const onFermer = await ouvrir();
        fireEvent.change(document.getElementById("fiche-rdv-creil-plages")!, { target: { value: "n'importe quoi" } });
        fireEvent.click(enregistrer());
        await waitFor(() => expect(screen.getByTestId("erreur-etablissements").textContent).toContain("heure illisible"));
        expect(screen.getByTestId("erreur-etablissements").textContent).toContain("Establishments saved, but the appointments and zone were not");
        expect(onFermer).not.toHaveBeenCalled();
        // The fiches ARE saved: closing tells the caller to read the list again.
        fireEvent.click(screen.getByText("Cancel"));
        expect(onFermer).toHaveBeenCalledWith(true);
    });

    it("does not send the planner level of a fiche that was removed", async () => {
        m.get.mockResolvedValue(catalogue(CREIL, SENLIS));
        m.planif.mockResolvedValue({ data: { ...PLANIFICATEUR, par_etablissement: { senlis: { nombre_creneaux: 4 }, creil: { nombre_creneaux: 2 } } } });
        await ouvrir();
        fireEvent.click(screen.getAllByLabelText("Remove this establishment")[1]);
        fireEvent.click(enregistrer());
        await waitFor(() => expect(m.putPlanif).toHaveBeenCalledTimes(1));
        expect(Object.keys(m.putPlanif.mock.calls[0][0].body.par_etablissement)).toEqual(["creil"]);
    });
});

describe("[.mark] « Create by copy » (F2)", () => {
    it("copies the chosen fiche, reads the list again, opens the new one and says what was not copied", async () => {
        m.copier.mockImplementation(async () => {
            m.get.mockResolvedValue(catalogue(CREIL, { ...SENLIS, nom: "Magasin de Senlis" }));
            return {
                data: {
                    etablissement: { ...SENLIS, nom: "Magasin de Senlis" },
                    reglages_rendez_vous_copies: true,
                    types_rendez_vous_copies: 2,
                    non_copie: ["numeros", "second_numero", "numero_transfert", "etat_force", "etat_force_jusqu_a"],
                },
            };
        });
        const onFermer = await ouvrir();
        expect(screen.getByTestId("creer-par-copie")).toBeTruthy();
        fireEvent.click(screen.getByTestId("creer-par-copie"));
        expect((screen.getByTestId("copier-la-fiche") as HTMLButtonElement).disabled).toBe(true); // no name yet
        fireEvent.change(document.getElementById("copie-nom")!, { target: { value: "Magasin de Senlis" } });
        expect(screen.getByTestId("copie-identifiant").textContent).toBe("magasin-de-senlis");
        fireEvent.click(screen.getByTestId("copier-la-fiche"));
        await waitFor(() => expect(m.copier).toHaveBeenCalledTimes(1));
        expect(m.copier.mock.calls[0][0].body).toEqual({ source: "creil", id: "magasin-de-senlis", nom: "Magasin de Senlis" });
        // The new fiche is read back from the server and opened.
        await waitFor(() => expect((screen.getByLabelText("Name") as HTMLInputElement).value).toBe("Magasin de Senlis"));
        const note = screen.getByTestId("resultat-copie").textContent ?? "";
        expect(note).toContain("Not copied, to fill on this fiche");
        expect(note).toContain("Appointment settings copied (2 type(s))");
        // Closing after a copy tells the caller to read the list again, saved or not.
        fireEvent.click(screen.getByText("Cancel"));
        expect(onFermer).toHaveBeenCalledWith(true);
    });

    it("shows the refusal of the server and stays in the window", async () => {
        m.copier.mockResolvedValue({ error: { detail: "The identifier « senlis » already belongs to a fiche." } });
        await ouvrir();
        fireEvent.click(screen.getByTestId("creer-par-copie"));
        fireEvent.change(document.getElementById("copie-nom")!, { target: { value: "Senlis" } });
        fireEvent.click(screen.getByTestId("copier-la-fiche"));
        await waitFor(() => expect(screen.getByTestId("erreur-copie-fiche").textContent).toContain("already belongs"));
    });

    it("is refused while something waits to be saved (the copy is written at once)", async () => {
        await ouvrir();
        expect((screen.getByTestId("creer-par-copie") as HTMLButtonElement).disabled).toBe(false);
        fireEvent.change(screen.getByLabelText("Name"), { target: { value: "Creil centre" } });
        expect((screen.getByTestId("creer-par-copie") as HTMLButtonElement).disabled).toBe(true);
        expect(screen.getByTestId("copie-apres-enregistrement")).toBeTruthy();
    });
});

describe("[.mark] the takeover of the fiches and agents", () => {
    const ESSAI = {
        ecrit: false,
        deja_a_jour: 1,
        actions: [
            { sujet: "fiche", cible: "creil", champ: "horaires_ouverture", avant: null, apres: "lundi : fermé" },
            { sujet: "agent", cible: "Accueil (34)", champ: "etablissement_id", avant: null, apres: "creil" },
        ],
        a_decider: ["Agent « Standard » (35): its numbers lead to two fiches."],
    };

    it("runs the trial first and writes nothing; the second click writes", async () => {
        m.reprise.mockImplementation(async ({ body }) => ({ data: { ...ESSAI, ecrit: body.ecrire } }));
        const onFermer = vi.fn();
        window.localStorage.setItem("mark.langue", "en");
        render(
            <FournisseurLangue>
                <ModaleReprise ouverte onFermer={onFermer} />
            </FournisseurLangue>,
        );
        await waitFor(() => expect(screen.getByTestId("actions-reprise")).toBeTruthy());
        expect(m.reprise).toHaveBeenCalledTimes(1);
        expect(m.reprise.mock.calls[0][0].body).toEqual({ ecrire: false });
        expect(screen.getByTestId("etat-reprise").textContent).toContain("Trial run, nothing written");
        const tableau = screen.getByTestId("actions-reprise").textContent ?? "";
        expect(tableau).toContain("horaires_ouverture");
        expect(tableau).toContain("Accueil (34)");
        expect(screen.getByTestId("a-decider-reprise").textContent).toContain("its numbers lead to two fiches");
        fireEvent.click(screen.getByTestId("ecrire-la-reprise"));
        await waitFor(() => expect(m.reprise).toHaveBeenCalledTimes(2));
        expect(m.reprise.mock.calls[1][0].body).toEqual({ ecrire: true });
        await waitFor(() => expect(screen.getByTestId("etat-reprise").textContent).toContain("Written"));
        expect(screen.queryByTestId("ecrire-la-reprise")).toBeNull();
        // Closing after a write tells the caller to read the list again.
        fireEvent.click(screen.getByText("Close"));
        expect(onFermer).toHaveBeenCalledWith(true);
    });

    it("has nothing to write when everything is up to date, and the button stays asleep", async () => {
        m.reprise.mockResolvedValue({ data: { ecrit: false, actions: [], a_decider: [], deja_a_jour: 4 } });
        window.localStorage.setItem("mark.langue", "en");
        render(
            <FournisseurLangue>
                <ModaleReprise ouverte onFermer={vi.fn()} />
            </FournisseurLangue>,
        );
        await waitFor(() => expect(screen.getByTestId("reprise-rien")).toBeTruthy());
        expect((screen.getByTestId("ecrire-la-reprise") as HTMLButtonElement).disabled).toBe(true);
    });

    it("shows the refusal of the server (a client database it cannot read)", async () => {
        m.reprise.mockResolvedValue({ error: { detail: "The appointment settings in the client database cannot be read. Nothing was changed." } });
        window.localStorage.setItem("mark.langue", "en");
        render(
            <FournisseurLangue>
                <ModaleReprise ouverte onFermer={vi.fn()} />
            </FournisseurLangue>,
        );
        await waitFor(() => expect(screen.getByTestId("erreur-reprise").textContent).toContain("Nothing was changed"));
    });
});

describe("[.mark] the places of a person (M5)", () => {
    const rendre = () => {
        window.localStorage.setItem("mark.langue", "en");
        m.get.mockResolvedValue(catalogue(CREIL, SENLIS));
        render(
            <FournisseurLangue>
                <ThemeEquipe ouvert onBasculer={() => {}} ouvrir={() => {}} signaler={vi.fn()} baseRattachee />
            </FournisseurLangue>,
        );
        fireEvent.click(screen.getByTestId("ouvrir-equipe"));
    };

    it("draws one box per fiche, ticked as the person's places, none ticked = the whole company", async () => {
        m.equipe.mockResolvedValue({ data: { personnes: [{ cle: "p1", prenom: "Alice", etablissement: "creil", etablissements: ["creil", "senlis"], actif: true }], sujets: [] } });
        rendre();
        await screen.findByDisplayValue("Alice");
        const lieux = await screen.findByTestId("lieux-p1");
        const cases = [...lieux.querySelectorAll("input")] as HTMLInputElement[];
        expect(cases.map((c) => c.checked)).toEqual([true, true]);
        expect(lieux.textContent).toContain("Magasin de Creil");
        fireEvent.click(cases[0]);
        fireEvent.click(cases[1]);
        expect(lieux.textContent).toContain("None ticked: the whole company.");
    });

    it("sends the list and empties both fields to put a person back on the whole company", async () => {
        m.equipe.mockResolvedValue({ data: { personnes: [{ cle: "p1", prenom: "Alice", etablissement: "creil", etablissements: ["creil", "senlis"], actif: true }], sujets: [] } });
        rendre();
        await screen.findByDisplayValue("Alice");
        const lieux = await screen.findByTestId("lieux-p1");
        // Untick Creil: the list is Senlis alone, the legacy field mirrors its first.
        fireEvent.click(lieux.querySelectorAll("input")[0]);
        fireEvent.click(screen.getByTestId("enregistrer-equipe"));
        await waitFor(() => expect(m.saveEquipe).toHaveBeenCalledTimes(1));
        expect(m.saveEquipe.mock.calls[0][0].body.personnes[0]).toMatchObject({ etablissements: ["senlis"], etablissement: "senlis" });
    });

    it("empties both fields when no box is ticked", async () => {
        m.equipe.mockResolvedValue({ data: { personnes: [{ cle: "p1", prenom: "Alice", etablissement: "creil", etablissements: ["creil"], actif: true }], sujets: [] } });
        rendre();
        await screen.findByDisplayValue("Alice");
        const lieux = await screen.findByTestId("lieux-p1");
        fireEvent.click(lieux.querySelectorAll("input")[0]);
        fireEvent.click(screen.getByTestId("enregistrer-equipe"));
        await waitFor(() => expect(m.saveEquipe).toHaveBeenCalledTimes(1));
        const personne = m.saveEquipe.mock.calls[0][0].body.personnes[0];
        expect(personne.etablissements).toEqual([]);
        expect(personne.etablissement).toBeNull();
    });

    it("reads an older answer (a single place) as a list", () => {
        expect(lieuxDe({ etablissement: "creil" })).toEqual(["creil"]);
        expect(lieuxDe({ etablissement: null })).toEqual([]);
        expect(lieuxDe({ etablissement: "creil", etablissements: [] })).toEqual([]);
        const charge = charge_utile_equipe({ personnes: [{ cle: "p1", prenom: "A", etablissement: "creil" }], sujets: [] });
        expect(charge.personnes?.[0]).toMatchObject({ etablissements: ["creil"], etablissement: "creil" });
    });
});

describe("[.mark] the test window (C8)", () => {
    it("offers the choice of the establishment to an agent without a fiche only", async () => {
        window.localStorage.setItem("mark.langue", "en");
        const { unmount } = render(
            <FournisseurLangue>
                <ChoixEtablissementEssai valeur="" onChange={vi.fn()} ficheDeLagent={null} />
            </FournisseurLangue>,
        );
        await waitFor(() => expect(screen.getByTestId("choix-etablissement-essai")).toBeTruthy());
        unmount();
        render(
            <FournisseurLangue>
                <ChoixEtablissementEssai valeur="" onChange={vi.fn()} ficheDeLagent="creil" />
            </FournisseurLangue>,
        );
        await waitFor(() => expect(m.get).toHaveBeenCalled());
        expect(screen.queryByTestId("choix-etablissement-essai")).toBeNull();
    });
});
