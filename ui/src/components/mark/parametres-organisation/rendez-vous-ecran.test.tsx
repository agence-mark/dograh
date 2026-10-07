/**
 * [.mark] The theme « Appointments » (chantier l-agent-collegue, L5), rendered.
 *
 *   - without a client database, it says where the rules live and offers nothing;
 *   - every rule of the planner is ON SCREEN (one entry per key of the published spec), with the
 *     value inherited shown in the empty field;
 *   - the organization's level and an establishment's are edited apart; the types are a list in a
 *     modal on a copy (« Cancel » / « Apply »); « Save » sends exactly what is on screen;
 *   - a value out of bounds is NAMED and blocks the save (E7).
 */
import { readFileSync } from "node:fs";
import { join } from "node:path";

import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import type { ReactNode } from "react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { FournisseurLangue } from "../langue/langue";
import { charge_utile_planificateur, ThemeRendezVous } from "./ThemeRendezVous";

const DEFAUTS = {
    nombre_creneaux: 3, delai_minimal_h: 24, horizon_jours: 14, pas_min: 30, plages: null, zone_rayon_km: null,
    zone_communes: null, trajets_comptes: false, coefficient_trajet: 1.3, vitesse_kmh: 50, repartition: "premier_libre",
    repli: "humain_puis_rappel", personne_visible: false, jours_feries: "metropole", fenetre_equite_jours: 30,
};
const LU = {
    reglages: { nombre_creneaux: 2 },
    par_etablissement: {},
    types: [{ code: "visite", etablissement: null, libelle: "Visite", duree_min: 60, sujet: "visite", marge_avant_min: 0, marge_apres_min: 0, actif: true }],
    defauts: DEFAUTS,
};

const m = vi.hoisted(() => ({ lire: vi.fn(), enregistrer: vi.fn() }));
vi.mock("@/client/sdk.gen", async (importOriginal) => (await import("../sdk-factice")).sdkFactice(await importOriginal(), {
    getPlanificateurApiV1OrganizationsPlanificateurGet: m.lire,
    putPlanificateurApiV1OrganizationsPlanificateurPut: m.enregistrer,
    getEtablissementsApiV1OrganizationsEtablissementsGet: () =>
        Promise.resolve({ data: { format: "etablissements-mark", version: 1, etablissements: [{ id: "nord", nom: "Site Nord", numeros: [] }] } }),
    getEquipeApiV1OrganizationsEquipeGet: () =>
        Promise.resolve({ data: { personnes: [], sujets: [{ code: "visite", libelle: "Visites", destinataires: [] }] } }),
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

afterEach(() => {
    cleanup();
    vi.clearAllMocks();
});

const rendre = (baseRattachee: boolean | null, adresseConnue: boolean | null = null) =>
    render(
        <FournisseurLangue>
            <ThemeRendezVous ouvert onBasculer={() => {}} ouvrir={() => {}} signaler={vi.fn()} baseRattachee={baseRattachee} adresseConnue={adresseConnue} />
        </FournisseurLangue>,
    );

const clesDuType = (nom: string): string[] => {
    const genere = readFileSync(join(process.cwd(), "src/client/types.gen.ts"), "utf8");
    const debut = `export type ${nom} = {`;
    const i = genere.indexOf(debut);
    const bloc = genere.slice(i + debut.length, genere.indexOf("\n};", i));
    return [...bloc.matchAll(/^ {4}([a-z_0-9]+)\??:/gm)].map((x) => x[1]);
};

describe("[.mark] l-agent-collegue L5: the theme « Appointments »", () => {
    it("says when a radius is set but no business address is saved (the zone would not apply)", async () => {
        m.lire.mockResolvedValue({ data: { ...structuredClone(LU), reglages: { zone_rayon_km: 30 } } });
        const { unmount } = rendre(true, false);
        expect(await screen.findByTestId("rdv-rayon-sans-adresse")).toBeTruthy();
        unmount();
        // An address saved, or none known yet: nothing said. No radius: nothing said either.
        m.lire.mockResolvedValue({ data: { ...structuredClone(LU), reglages: { zone_rayon_km: 30 } } });
        const avecAdresse = rendre(true, true);
        await screen.findByTestId("ouvrir-types-rdv");
        expect(screen.queryByTestId("rdv-rayon-sans-adresse")).toBeNull();
        avecAdresse.unmount();
        m.lire.mockResolvedValue({ data: structuredClone(LU) });
        rendre(true, false);
        await screen.findByTestId("ouvrir-types-rdv");
        expect(screen.queryByTestId("rdv-rayon-sans-adresse")).toBeNull();
    });

    it("without a database, says where the rules live and offers nothing", () => {
        rendre(false);
        expect(screen.getByTestId("rdv-sans-base")).toBeTruthy();
        expect(m.lire).not.toHaveBeenCalled();
        expect(screen.queryByTestId("ouvrir-types-rdv")).toBeNull();
    });

    it("draws every rule of the published spec, the inherited value in the empty field", async () => {
        m.lire.mockResolvedValue({ data: structuredClone(LU) });
        const { container } = rendre(true);
        await screen.findByTestId("ouvrir-types-rdv");
        const cles = clesDuType("ReglagesPlanificateur");
        expect(cles.length).toBe(15);
        for (const cle of cles) expect(container.querySelector(`[data-reglage="${cle}"]`), cle).not.toBeNull();
        expect(container.querySelector('[data-reglage="types"]')).not.toBeNull();
        expect((document.getElementById("rdv-nombre_creneaux") as HTMLInputElement).value).toBe("2");
        expect((document.getElementById("rdv-horizon_jours") as HTMLInputElement).placeholder).toMatch(/14/);
        // An establishment inherits the ORGANIZATION's value, not the default.
        fireEvent.change(document.getElementById("rdv-niveau-choix")!, { target: { value: "nord" } });
        const nombre = document.getElementById("rdv-nombre_creneaux") as HTMLInputElement;
        expect(nombre.value).toBe("");
        expect(nombre.placeholder).toMatch(/2/);
    });

    it("saves exactly the two levels and the types as set on screen", async () => {
        m.lire.mockResolvedValue({ data: structuredClone(LU) });
        m.enregistrer.mockImplementation(async ({ body }) => ({ data: { ...body, defauts: DEFAUTS } }));
        rendre(true);
        await screen.findByTestId("ouvrir-types-rdv");
        fireEvent.change(document.getElementById("rdv-repartition")!, { target: { value: "tour_de_role" } });
        fireEvent.change(document.getElementById("rdv-niveau-choix")!, { target: { value: "nord" } });
        fireEvent.change(document.getElementById("rdv-repli")!, { target: { value: "toujours_rappel" } });
        fireEvent.change(document.getElementById("rdv-jours_feries")!, { target: { value: "alsace_moselle" } });
        // This establishment's own type, in the modal (a copy).
        fireEvent.click(screen.getByTestId("ouvrir-types-rdv"));
        fireEvent.click(screen.getByTestId("ajouter-type-rdv"));
        const appliquer = screen.getByTestId("appliquer-types-rdv") as HTMLButtonElement;
        expect(appliquer.disabled).toBe(true); // a type without a name
        const ligne = screen.getByTestId("type-rdv-type_1");
        fireEvent.change(ligne.querySelector('input[aria-label="Libellé"]')!, { target: { value: " Visite longue " } });
        fireEvent.change(ligne.querySelector('input[aria-label="Durée (min)"]')!, { target: { value: "90" } });
        fireEvent.click(appliquer);
        fireEvent.click(screen.getByRole("button", { name: /Save Appointments|Enregistrer Rendez-vous/ }));
        await waitFor(() => expect(m.enregistrer).toHaveBeenCalledTimes(1));
        expect(m.enregistrer.mock.calls[0][0].body).toEqual({
            reglages: { nombre_creneaux: 2, repartition: "tour_de_role" },
            par_etablissement: { nord: { repli: "toujours_rappel", jours_feries: "alsace_moselle" } },
            types: [
                LU.types[0],
                { code: "type_1", etablissement: "nord", libelle: "Visite longue", duree_min: 90, sujet: null, marge_avant_min: 0, marge_apres_min: 0, actif: true },
            ],
        });
    });

    it("R-7: the fairness window is on screen with its bounds, inherited from the organization, and saved as set", async () => {
        m.lire.mockResolvedValue({ data: { ...structuredClone(LU), reglages: { repartition: "tour_de_role", fenetre_equite_jours: 45 } } });
        m.enregistrer.mockImplementation(async ({ body }) => ({ data: { ...body, defauts: DEFAUTS } }));
        const { container } = rendre(true);
        await screen.findByTestId("ouvrir-types-rdv");
        const champ = container.querySelector('[data-reglage="fenetre_equite_jours"]')!;
        expect(champ.textContent).toMatch(/Fairness window \(days\)|Fenêtre du tour de rôle/);
        expect(champ.textContent).toContain("≥ 1 · ≤ 365"); // the bounds, shown
        const entree = document.getElementById("rdv-fenetre_equite_jours") as HTMLInputElement;
        expect(entree.value).toBe("45");
        expect(champ.textContent).not.toMatch(/No effect here|Sans effet/); // the mode is « In turn »
        // An establishment inherits the ORGANIZATION's 45 days, and sets its own.
        fireEvent.change(document.getElementById("rdv-niveau-choix")!, { target: { value: "nord" } });
        const nord = document.getElementById("rdv-fenetre_equite_jours") as HTMLInputElement;
        expect(nord.value).toBe("");
        expect(nord.placeholder).toMatch(/45/);
        fireEvent.change(nord, { target: { value: "7" } });
        fireEvent.click(screen.getByRole("button", { name: /Save Appointments|Enregistrer Rendez-vous/ }));
        await waitFor(() => expect(m.enregistrer).toHaveBeenCalledTimes(1));
        expect(m.enregistrer.mock.calls[0][0].body).toEqual({
            reglages: { repartition: "tour_de_role", fenetre_equite_jours: 45 },
            par_etablissement: { nord: { fenetre_equite_jours: 7 } },
            types: LU.types,
        });
    });

    it("R-7: the window says it has no effect while no level distributes in turn, and is named out of bounds", async () => {
        m.lire.mockResolvedValue({ data: structuredClone(LU) });
        const { container } = rendre(true);
        await screen.findByTestId("ouvrir-types-rdv");
        const champ = () => container.querySelector('[data-reglage="fenetre_equite_jours"]')!.textContent ?? "";
        expect((document.getElementById("rdv-fenetre_equite_jours") as HTMLInputElement).placeholder).toMatch(/30/); // the default
        expect(champ()).toMatch(/No effect here|Sans effet ici/);
        fireEvent.change(document.getElementById("rdv-repartition")!, { target: { value: "tour_de_role" } });
        expect(champ()).not.toMatch(/No effect here|Sans effet ici/);
        fireEvent.change(document.getElementById("rdv-fenetre_equite_jours")!, { target: { value: "400" } });
        expect(screen.getByRole("button", { name: /Save Appointments|Enregistrer Rendez-vous/ }).hasAttribute("disabled")).toBe(true);
        expect(document.body.textContent).toContain("fenetre_equite_jours");
        expect(m.enregistrer).not.toHaveBeenCalled();
    });

    it("names a value out of bounds and blocks the save", async () => {
        m.lire.mockResolvedValue({ data: structuredClone(LU) });
        rendre(true);
        await screen.findByTestId("ouvrir-types-rdv");
        fireEvent.change(document.getElementById("rdv-nombre_creneaux")!, { target: { value: "9" } });
        expect(screen.getByRole("button", { name: /Save Appointments|Enregistrer Rendez-vous/ }).hasAttribute("disabled")).toBe(true);
        expect(document.body.textContent).toContain("nombre_creneaux");
        expect(m.enregistrer).not.toHaveBeenCalled();
    });

    it("the payload turns emptied fields into « inherited »", () => {
        expect(charge_utile_planificateur({ reglages: { nombre_creneaux: Number.NaN, plages: "" } }).reglages).toEqual({
            nombre_creneaux: null,
            plages: null,
        });
    });
});
