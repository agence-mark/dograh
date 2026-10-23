/**
 * [.mark] « Apply to all establishments » on screen (cloture-code D152, finished in correctifs-apres-banc-commun,
 * lot 9; convention `22-convention-ecran.md` § 5: display condition, payload tested, element found in the window).
 *
 *   - nothing is drawn for a single establishment (nobody to apply it to) ;
 *   - one button next to each setting of an establishment that can be copied (address, hours, announcements,
 *     a sentence of the establishment's level) ; the planner's settings are covered family by family ;
 *   - the button is off while something waits to be saved (the server copies the SAVED value) ;
 *   - a small centred window names the establishments written and the value, asks to confirm ; « Cancel » sends nothing ;
 *   - « Apply » sends the setting only (never the value), then the list is read again ;
 *   - a refusal of the server is shown and the window stays open.
 */
import { cleanup, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import type { ReactNode } from "react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { FournisseurLangue } from "../langue/langue";
import { ModaleEtablissements } from "./ModaleEtablissements";
import { FicheRendezVous } from "./FicheRendezVous";
import { CHOIX, FENETRE, NOMBRES, NOMBRES_TRAJETS, OUI_NON } from "./reglages-rendez-vous";

const m = vi.hoisted(() => ({ get: vi.fn(), save: vi.fn(), phrases: vi.fn(), appliquer: vi.fn() }));

vi.mock("@/client/sdk.gen", async (importOriginal) => (await import("../sdk-factice")).sdkFactice(await importOriginal(), {
    getEtablissementsApiV1OrganizationsEtablissementsGet: m.get,
    saveEtablissementsApiV1OrganizationsEtablissementsPut: m.save,
    getPhrasesApiV1OrganizationsPhrasesGet: m.phrases,
    appliquerATousLesEtablissementsApiV1OrganizationsEtablissementsIdentifiantAppliquerATousPost: m.appliquer,
    getCommunesDuCodePostalApiV1OrganizationsCommunesGet: () => Promise.resolve({ data: [] }),
}));
vi.mock("sonner", () => ({ toast: { success: vi.fn(), error: vi.fn() } }));
vi.mock("@/lib/auth", () => ({ useAuth: () => ({ user: { id: 1 }, loading: false }) }));
vi.mock("@/components/ui/dialog", () => ({
    Dialog: ({ open, children }: { open: boolean; children: ReactNode }) => (open ? <div>{children}</div> : null),
    DialogContent: ({ children, ...props }: { children: ReactNode; "data-testid"?: string }) => <div data-testid={props["data-testid"]}>{children}</div>,
    DialogDescription: ({ children }: { children: ReactNode }) => <p>{children}</p>,
    DialogFooter: ({ children }: { children: ReactNode }) => <div>{children}</div>,
    DialogHeader: ({ children }: { children: ReactNode }) => <div>{children}</div>,
    DialogTitle: ({ children }: { children: ReactNode }) => <h2>{children}</h2>,
}));

const lieu = (id: string, nom: string, plus = {}) => ({
    id,
    nom,
    numeros: [],
    second_numero: null,
    numero_transfert: null,
    adresse: null,
    horaires_ouverture: null,
    annonce_fermeture: null,
    annonce_pause: null,
    phrases: {},
    termes_lexique: [],
    ...plus,
});
const CREIL = lieu("creil", "Magasin de Creil", { horaires_ouverture: "lundi : 9h-12h" });
const SENLIS = lieu("senlis", "Magasin de Senlis");
const ANNONCE = { annonce_fermeture: "Fermés.", annonce_pause: "Pause.", etat_force: null, etat_force_jusqu_a: null };

const lire = (...lieux: ReturnType<typeof lieu>[]) =>
    m.get.mockResolvedValue({ data: { format: "etablissements-mark", version: 1, etablissements: lieux } });

const reinitialiser = () => {
    m.get.mockReset();
    lire(CREIL, SENLIS);
    m.save.mockReset().mockImplementation(async ({ body }) => ({ data: body }));
    m.phrases.mockReset().mockResolvedValue({
        data: {
            format: "phrases-mark",
            version: 1,
            phrases: [{ variable: "phrase_acces", description: "Access", contenu: "", niveau: "etablissement" }],
        },
    });
    m.appliquer.mockReset().mockResolvedValue({
        data: { source: "creil", reglage: "fiche", cle: "horaires_ouverture", etablissements: [{ id: "senlis", nom: "Magasin de Senlis" }] },
    });
};
reinitialiser();
afterEach(() => {
    cleanup();
    reinitialiser();
    window.localStorage.clear();
});

const ouvrir = async () => {
    window.localStorage.setItem("mark.langue", "en");
    render(
        <FournisseurLangue>
            <ModaleEtablissements ouverte onFermer={vi.fn()} adresseOrganisation={null} annonceOrganisation={ANNONCE} />
        </FournisseurLangue>,
    );
    await waitFor(() => expect(screen.getByTestId("fiche-etablissement")).toBeTruthy());
};

describe("[.mark] Apply to all establishments (D152)", () => {
    it("draws nothing for a single establishment", async () => {
        lire(CREIL);
        await ouvrir();
        expect(screen.queryByTestId("appliquer-a-tous-fiche-horaires_ouverture")).toBeNull();
    });

    it("draws one button next to each copiable setting of the establishment", async () => {
        await ouvrir();
        for (const id of [
            "appliquer-a-tous-fiche-adresse",
            "appliquer-a-tous-fiche-horaires_ouverture",
            "appliquer-a-tous-fiche-annonce_fermeture",
            "appliquer-a-tous-fiche-annonce_pause",
            "appliquer-a-tous-phrase-phrase_acces",
        ]) {
            expect(screen.getByTestId(id), id).toBeTruthy();
        }
    });

    it("names the establishments written and the value, sends only which setting, then reads the list again", async () => {
        await ouvrir();
        const lectures = m.get.mock.calls.length;
        fireEvent.click(screen.getByTestId("appliquer-a-tous-fiche-horaires_ouverture"));
        const fenetre = screen.getByTestId("modale-appliquer-a-tous");
        expect(within(fenetre).getByTestId("valeur-appliquee").textContent).toBe("lundi : 9h-12h");
        const touches = within(fenetre).getByTestId("etablissements-touches");
        expect(touches.textContent).toBe("Magasin de Senlis"); // the source itself is not listed
        fireEvent.click(within(fenetre).getByTestId("confirmer-appliquer-a-tous"));
        await waitFor(() => expect(m.appliquer).toHaveBeenCalledTimes(1));
        expect(m.appliquer.mock.calls[0][0]).toEqual({
            path: { identifiant: "creil" },
            body: { reglage: "fiche", cle: "horaires_ouverture" },
        });
        await waitFor(() => expect(screen.queryByTestId("modale-appliquer-a-tous")).toBeNull());
        await waitFor(() => expect(m.get.mock.calls.length).toBeGreaterThan(lectures));
    });

    it("says « nothing » when the setting is empty on the source, and Cancel sends nothing", async () => {
        await ouvrir();
        fireEvent.click(screen.getByTestId("appliquer-a-tous-fiche-annonce_pause"));
        expect(screen.getByTestId("valeur-appliquee").textContent).toMatch(/nothing/i);
        fireEvent.click(within(screen.getByTestId("modale-appliquer-a-tous")).getByRole("button", { name: /cancel/i }));
        expect(screen.queryByTestId("modale-appliquer-a-tous")).toBeNull();
        expect(m.appliquer).not.toHaveBeenCalled();
    });

    it("is off while something waits to be saved: the saved value is the one copied", async () => {
        await ouvrir();
        const bouton = screen.getByTestId("appliquer-a-tous-fiche-horaires_ouverture") as HTMLButtonElement;
        expect(bouton.disabled).toBe(false);
        fireEvent.change(document.getElementById("etablissement-horaires") as HTMLTextAreaElement, { target: { value: "lundi : 8h-12h" } });
        expect(bouton.disabled).toBe(true);
        expect(bouton.title).toMatch(/save the changes first/i);
    });

    it("shows a refusal of the server and keeps the window open", async () => {
        m.appliquer.mockResolvedValue({ error: { detail: "The client database is behind this installation." } });
        await ouvrir();
        fireEvent.click(screen.getByTestId("appliquer-a-tous-fiche-adresse"));
        fireEvent.click(screen.getByTestId("confirmer-appliquer-a-tous"));
        const erreur = await screen.findByTestId("erreur-appliquer-a-tous");
        expect(erreur.textContent).toContain("behind this installation");
        expect(screen.getByTestId("modale-appliquer-a-tous")).toBeTruthy();
    });
});

describe("[.mark] Apply to all establishments: the planner's settings, family by family", () => {
    it("offers the button on every setting of the appointments and zone, none left out", () => {
        const vus: string[] = [];
        render(
            <FournisseurLangue>
                <FicheRendezVous
                    id="creil"
                    reglages={{}}
                    defauts={{}}
                    onPoser={vi.fn()}
                    boutonPour={(cle) => {
                        vus.push(cle);
                        return null;
                    }}
                />
            </FournisseurLangue>,
        );
        const attendus = [
            ...NOMBRES.map((f) => f.cle),
            FENETRE.cle,
            ...NOMBRES_TRAJETS.map((f) => f.cle),
            ...CHOIX.map((f) => f.cle),
            ...OUI_NON.map((f) => f.cle),
            "plages",
            "zone_communes",
        ];
        expect([...new Set(vus)].sort()).toEqual([...new Set(attendus)].sort());
    });
});
