/**
 * [.mark] J : l'inventaire des réglages d'Équipe et routage et de Rendez-vous, prouvé sur les FENÊTRES de l'écran
 * Entreprise (les anciens thèmes `ThemeEquipe` et `ThemeRendezVous` sont retirés ; leurs tests sont portés ici).
 *
 *   Rendez-vous : chaque réglage du planificateur publié se retrouve dans une fenêtre, la valeur du niveau et le défaut
 *   commun sont lus en clair, « Enregistrer » envoie le planificateur entier avec la part changée, une valeur hors
 *   bornes est nommée sous le champ et n'écrit rien, « Appliquer à tous » copie un type, le contenu envoyé vide les champs.
 *   Équipe : une personne s'ajoute, sa description, son transfert, ses divulgations, son agenda et ses lieux sont à
 *   l'écran et enregistrés tels quels ; l'équipe entière est renvoyée (la route remplace tout).
 */
import { readFileSync } from "node:fs";
import { join } from "node:path";

import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { FournisseurLangue } from "../langue/langue";
import { charge_utile_equipe, DESCRIPTION_MAX, lieuxDe } from "../parametres-organisation/charge-utile-equipe";
import { charge_utile_planificateur } from "../parametres-organisation/charge-utile-planificateur";
import { CHOIX, FENETRE, NOMBRES, NOMBRES_TRAJETS, OUI_NON } from "../parametres-organisation/reglages-rendez-vous";

const DEFAUTS = {
    nombre_creneaux: 3, delai_minimal_h: 24, horizon_jours: 14, pas_min: 30, plages: null, zone_rayon_km: null,
    zone_communes: null, trajets_comptes: false, coefficient_trajet: 1.3, vitesse_kmh: 50, repartition: "premier_libre",
    repli: "humain_puis_rappel", personne_visible: false, jours_feries: "metropole", fenetre_equite_jours: 30,
};
const PLAN = {
    reglages: { nombre_creneaux: 2 },
    par_etablissement: {},
    types: [{ code: "visite", etablissement: null, libelle: "Visite", duree_min: 60, sujet: "visite", marge_avant_min: 0, marge_apres_min: 0, actif: true }],
    defauts: DEFAUTS,
};
const SITES = [
    { id: "creil", nom: "Magasin de Creil", numeros: [] as string[] },
    { id: "senlis", nom: "Magasin de Senlis", numeros: [] as string[] },
];

const m = vi.hoisted(() => ({
    equipe: vi.fn(),
    ecrireEquipe: vi.fn(),
    planif: vi.fn(),
    ecrirePlanif: vi.fn(),
    appliquer: vi.fn(),
    choix: vi.fn(),
    sites: [] as Array<{ id: string; nom: string; numeros: string[] }>,
}));

vi.mock("@/client/sdk.gen", async (importOriginal) =>
    (await import("../sdk-factice")).sdkFactice(await importOriginal(), {
        getEquipeApiV1OrganizationsEquipeGet: m.equipe,
        putEquipeApiV1OrganizationsEquipePut: m.ecrireEquipe,
        getPlanificateurApiV1OrganizationsPlanificateurGet: m.planif,
        putPlanificateurApiV1OrganizationsPlanificateurPut: m.ecrirePlanif,
        getEtablissementsApiV1OrganizationsEtablissementsGet: () =>
            Promise.resolve({ data: { format: "etablissements-mark", version: 1, etablissements: m.sites } }),
        appliquerATousLesEtablissementsApiV1OrganizationsEtablissementsIdentifiantAppliquerATousPost: m.appliquer,
        getChoixTraducteursApiV1ConnecteursTraducteursChoixGet: m.choix,
        getTraducteursApiV1ConnecteursTraducteursGet: () =>
            Promise.resolve({
                data: [{ systeme: "google_agenda", libelle: "Google Agenda", domaine: "agenda", integration: "google-calendar",
                         reference_agenda: { en: "Calendar ID", fr: "Identifiant de l'agenda" }, operations: {} }],
            }),
    }),
);
vi.mock("sonner", () => ({ toast: { success: vi.fn(), error: vi.fn() } }));
vi.mock("@/lib/auth", () => ({ useAuth: () => ({ user: { id: 1 }, loading: false }) }));
vi.stubGlobal("ResizeObserver", class { observe() {} unobserve() {} disconnect() {} });
Element.prototype.hasPointerCapture = vi.fn(() => false);
Element.prototype.scrollIntoView = vi.fn();

const { OngletEquipe } = await import("./OngletEquipe");
const { OngletRendezVous } = await import("./OngletRendezVous");

const rendre = (noeud: React.ReactNode) => render(<FournisseurLangue>{noeud}</FournisseurLangue>);
const reinitialiser = () => {
    m.sites = structuredClone(SITES);
    m.equipe.mockReset().mockResolvedValue({ data: { personnes: [], sujets: [] } });
    m.ecrireEquipe.mockReset().mockImplementation(async ({ body }: { body: unknown }) => ({ data: structuredClone(body) }));
    m.planif.mockReset().mockImplementation(() => Promise.resolve({ data: structuredClone(PLAN) }));
    m.ecrirePlanif.mockReset().mockImplementation(async ({ body }: { body: unknown }) => ({ data: { ...structuredClone(body as object), defauts: DEFAUTS } }));
    m.appliquer.mockReset();
    m.choix.mockReset().mockResolvedValue({ data: { agenda: null } });
};
reinitialiser();
afterEach(() => {
    cleanup();
    reinitialiser();
});

const clesDuType = (nom: string): string[] => {
    const genere = readFileSync(join(process.cwd(), "src/client/types.gen.ts"), "utf8");
    const debut = `export type ${nom} = {`;
    const i = genere.indexOf(debut);
    const bloc = genere.slice(i + debut.length, genere.indexOf("\n};", i));
    return [...bloc.matchAll(/^ {4}([a-z_0-9]+)\??:/gm)].map((x) => x[1]);
};

const ouvrirSection = async (titre: string) => {
    const section = (await screen.findByText(titre)).closest("section") as HTMLElement;
    fireEvent.click(Array.from(section.querySelectorAll("button")).find((b) => /Modifier|Edit/.test(b.textContent ?? "")) as HTMLElement);
};
const enregistrer = () => fireEvent.click(screen.getByRole("button", { name: /^(Enregistrer|Save)$/ }));
const choisirNiveau = async (nom: string) => {
    await screen.findByText("Types de rendez-vous");
    fireEvent.pointerDown(screen.getAllByRole("combobox")[0], { button: 0, ctrlKey: false });
    fireEvent.click(screen.getAllByRole("combobox")[0]);
    fireEvent.click(await screen.findByRole("option", { name: nom }));
};

describe("[.mark] J : Rendez-vous, l'inventaire sur les fenêtres", () => {
    it("sans base rattachée : dit où vivent les règles, ne lit rien et ne propose rien", () => {
        rendre(<OngletRendezVous baseRattachee={false} />);
        expect(screen.getByTestId("rdv-sans-base")).toBeTruthy();
        expect(m.planif).not.toHaveBeenCalled();
        expect(screen.queryByTestId("ajouter-type-rdv")).toBeNull();
    });

    it("chaque réglage du planificateur publié est dans une fenêtre, avec son libellé", async () => {
        const cles = clesDuType("ReglagesPlanificateur");
        expect(cles.length).toBe(15);
        const connus = new Set<string>(["plages", "zone_communes", ...[...NOMBRES, ...NOMBRES_TRAJETS, FENETRE, ...CHOIX, ...OUI_NON].map((f) => f.cle)]);
        for (const cle of cles) expect(connus.has(cle), `${cle} n'a aucun champ`).toBe(true);

        const parSection: Array<[string, string[]]> = [
            ["Créneaux", ["Plages de rendez-vous", ...NOMBRES.map((f) => f.libelle.fr)]],
            ["Zone et trajets", [NOMBRES_TRAJETS[2].libelle.fr, "Zone desservie : communes (codes INSEE)", OUI_NON[0].libelle.fr, NOMBRES_TRAJETS[0].libelle.fr, NOMBRES_TRAJETS[1].libelle.fr]],
            ["Répartition et repli", [...CHOIX.map((f) => f.libelle.fr), FENETRE.libelle.fr, OUI_NON[1].libelle.fr]],
        ];
        for (const [titre, libelles] of parSection) {
            const { unmount } = rendre(<OngletRendezVous baseRattachee />);
            await ouvrirSection(titre);
            const dialogue = await screen.findByRole("dialog");
            for (const l of libelles) expect(dialogue.textContent, `${titre} : ${l}`).toContain(l);
            unmount();
        }
    });

    it("lit la valeur du niveau, et le défaut commun quand le champ est vide (un établissement n'hérite de rien)", async () => {
        rendre(<OngletRendezVous baseRattachee />);
        const ligne = (await screen.findByText("Créneaux proposés")).closest("div") as HTMLElement;
        expect(ligne.textContent).toContain("2");
        await choisirNiveau("Magasin de Creil");
        await waitFor(() => expect((screen.getByText("Créneaux proposés").closest("div") as HTMLElement).textContent).toContain("3 (défaut)"));
    });

    it("« Enregistrer » envoie le planificateur entier avec la part changée, rien d'autre ne bouge", async () => {
        m.planif.mockImplementation(() => Promise.resolve({ data: { ...structuredClone(PLAN), par_etablissement: { creil: { repli: "toujours_rappel" } } } }));
        rendre(<OngletRendezVous baseRattachee />);
        await ouvrirSection("Créneaux");
        fireEvent.change(await screen.findByLabelText("Créneaux proposés"), { target: { value: "4" } });
        enregistrer();
        await waitFor(() => expect(m.ecrirePlanif).toHaveBeenCalledTimes(1));
        expect(m.ecrirePlanif.mock.calls[0][0].body).toEqual({
            reglages: { nombre_creneaux: 4, plages: null, delai_minimal_h: null, horizon_jours: null, pas_min: null },
            par_etablissement: { creil: { repli: "toujours_rappel" } },
            types: PLAN.types,
        });
    });

    it("R-7 : la fenêtre du tour de rôle est dans « Répartition et repli », avec ses bornes, et s'écrit au niveau choisi", async () => {
        rendre(<OngletRendezVous baseRattachee />);
        await choisirNiveau("Magasin de Senlis");
        await ouvrirSection("Répartition et repli");
        const champ = await screen.findByLabelText(FENETRE.libelle.fr);
        expect(screen.getByRole("dialog").textContent).toMatch(/de 1 à 365/);
        fireEvent.change(champ, { target: { value: "7" } });
        enregistrer();
        await waitFor(() => expect(m.ecrirePlanif).toHaveBeenCalledTimes(1));
        const corps = m.ecrirePlanif.mock.calls[0][0].body;
        expect(corps.par_etablissement.senlis).toMatchObject({ fenetre_equite_jours: 7 });
        expect(corps.reglages).toEqual(PLAN.reglages);
        expect(corps.types).toEqual(PLAN.types);
    });

    it("nomme sous le champ une valeur hors bornes et n'écrit rien", async () => {
        rendre(<OngletRendezVous baseRattachee />);
        await ouvrirSection("Créneaux");
        fireEvent.change(await screen.findByLabelText("Créneaux proposés"), { target: { value: "99" } });
        enregistrer();
        expect(await screen.findByText(/Entre \d+ et \d+\./)).toBeTruthy();
        expect(m.ecrirePlanif).not.toHaveBeenCalled();
    });

    it("« Appliquer à tous » copie un type enregistré, côté serveur, depuis la fenêtre du type d'un établissement", async () => {
        m.planif.mockImplementation(() =>
            Promise.resolve({
                data: {
                    ...structuredClone(PLAN),
                    types: [...PLAN.types, { code: "type_1", etablissement: "creil", libelle: "Visite longue", duree_min: 90, sujet: null, marge_avant_min: 0, marge_apres_min: 0, actif: true }],
                },
            }),
        );
        m.appliquer.mockResolvedValue({ data: { source: "creil", reglage: "type", cle: "type_1", etablissements: [{ id: "senlis", nom: "Magasin de Senlis" }] } });
        rendre(<OngletRendezVous baseRattachee />);
        await choisirNiveau("Magasin de Creil");
        fireEvent.click((await screen.findByText("Visite longue")).closest("tr") as HTMLElement);
        fireEvent.click(await screen.findByTestId("appliquer-a-tous-type-type_1"));
        fireEvent.click(await screen.findByTestId("confirmer-appliquer-a-tous"));
        await waitFor(() => expect(m.appliquer).toHaveBeenCalledTimes(1));
        expect(m.appliquer.mock.calls[0][0]).toMatchObject({ path: { identifiant: "creil" }, body: { reglage: "type", cle: "type_1" } });
        await waitFor(() => expect(m.planif).toHaveBeenCalledTimes(2)); // le planificateur est relu
    });

    it("avec un seul établissement, « Appliquer à tous » n'existe pas", async () => {
        m.sites = [SITES[0]];
        m.planif.mockImplementation(() =>
            Promise.resolve({
                data: { ...structuredClone(PLAN), types: [{ code: "type_1", etablissement: "creil", libelle: "Visite longue", duree_min: 90, sujet: null, marge_avant_min: 0, marge_apres_min: 0, actif: true }] },
            }),
        );
        rendre(<OngletRendezVous baseRattachee />);
        await choisirNiveau("Magasin de Creil");
        fireEvent.click((await screen.findByText("Visite longue")).closest("tr") as HTMLElement);
        await screen.findByDisplayValue("Visite longue");
        expect(screen.queryByTestId("appliquer-a-tous-type-type_1")).toBeNull();
    });

    it("le contenu envoyé transforme les champs vidés en « hérité » (null)", () => {
        expect(charge_utile_planificateur({ reglages: { nombre_creneaux: Number.NaN, plages: "" } }).reglages).toEqual({
            nombre_creneaux: null,
            plages: null,
        });
    });
});

describe("[.mark] J : Équipe et routage, l'inventaire sur les fenêtres", () => {
    const ALICE = { cle: "p1", prenom: "Alice", etablissement: "creil", actif: true };
    const avecAlice = (plus: object = {}) => m.equipe.mockResolvedValue({ data: { personnes: [{ ...ALICE, ...plus }], sujets: [] } });
    const ouvrirAlice = async () => {
        fireEvent.click((await screen.findByText("Alice")).closest("tr") as HTMLElement);
        await screen.findByDisplayValue("Alice");
    };

    it("sans base rattachée : dit où l'attacher et ne propose rien", () => {
        rendre(<OngletEquipe baseRattachee={false} />);
        expect(screen.getByTestId("equipe-sans-base")).toBeTruthy();
        expect(screen.queryByTestId("ajouter-personne")).toBeNull();
    });

    it("ajoute une personne et enregistre exactement ce qui est à l'écran, l'équipe entière avec elle", async () => {
        avecAlice();
        rendre(<OngletEquipe baseRattachee />);
        fireEvent.click(await screen.findByTestId("ajouter-personne"));
        enregistrer();
        expect(await screen.findByText(/prénom est obligatoire/i)).toBeTruthy(); // sans prénom : refusé sous le champ
        expect(m.ecrireEquipe).not.toHaveBeenCalled();
        fireEvent.change(screen.getByLabelText("Prénom"), { target: { value: " Bruno " } });
        enregistrer();
        await waitFor(() => expect(m.ecrireEquipe).toHaveBeenCalledTimes(1));
        const envoye = m.ecrireEquipe.mock.calls[0][0].body;
        expect(envoye.personnes.map((p: { prenom: string }) => p.prenom)).toEqual(["Alice", "Bruno"]);
        expect(envoye.personnes[1].cle).toBeTruthy();
    });

    it("C1 : description, transfert et divulgations sont à l'écran et enregistrés tels quels", async () => {
        avecAlice();
        rendre(<OngletEquipe baseRattachee />);
        await ouvrirAlice();
        fireEvent.change(screen.getByLabelText("Ce dont cette personne s'occupe"), { target: { value: "  Les rendez-vous et les factures.  " } });
        const transfert = screen.getByLabelText("L'agent peut lui transférer un appel");
        expect(transfert.getAttribute("aria-checked")).toBe("false"); // éteint par défaut (C1)
        fireEvent.click(transfert);
        fireEvent.click(screen.getByLabelText("L'agent peut donner son e-mail"));
        expect(screen.getByLabelText("L'agent peut donner son téléphone").getAttribute("aria-checked")).toBe("false");
        enregistrer();
        await waitFor(() => expect(m.ecrireEquipe).toHaveBeenCalledTimes(1));
        expect(m.ecrireEquipe.mock.calls[0][0].body.personnes[0]).toMatchObject({
            description: "Les rendez-vous et les factures.",
            joignable_par_transfert: true,
            divulguer_mail: true,
            divulguer_telephone: false,
        });
    });

    it("la description est bornée comme le serveur : au-delà, nommée sous le champ, rien n'est écrit", async () => {
        avecAlice();
        rendre(<OngletEquipe baseRattachee />);
        await ouvrirAlice();
        fireEvent.change(screen.getByLabelText("Ce dont cette personne s'occupe"), { target: { value: "x".repeat(DESCRIPTION_MAX + 1) } });
        enregistrer();
        expect(await screen.findByText(new RegExp(`${DESCRIPTION_MAX} caractères au plus`))).toBeTruthy();
        expect(m.ecrireEquipe).not.toHaveBeenCalled();
    });

    it("L4 : l'agenda de la personne dans le logiciel choisi, enregistré tel que saisi ; rien de choisi, pas de champ", async () => {
        avecAlice({ agendas: { outlook_agenda: "a@x.org" } });
        rendre(<OngletEquipe baseRattachee />);
        await ouvrirAlice();
        expect(screen.queryByLabelText(/Agenda dans/)).toBeNull();
        cleanup();

        m.choix.mockResolvedValue({ data: { agenda: "google_agenda" } });
        rendre(<OngletEquipe baseRattachee />);
        await ouvrirAlice();
        fireEvent.change(await screen.findByLabelText("Agenda dans Google Agenda"), { target: { value: " alice@example.org " } });
        enregistrer();
        await waitFor(() => expect(m.ecrireEquipe).toHaveBeenCalledTimes(1));
        // L'agenda de l'autre logiciel est gardé ; celui qui est saisi est nettoyé.
        expect(m.ecrireEquipe.mock.calls[0][0].body.personnes[0].agendas).toEqual({ outlook_agenda: "a@x.org", google_agenda: "alice@example.org" });
    });

    it("M5 : un bouton par fiche, coché selon les lieux de la personne ; décocher Creil laisse Senlis, tout décocher = toute l'entreprise", async () => {
        avecAlice({ etablissements: ["creil", "senlis"] });
        rendre(<OngletEquipe baseRattachee />);
        await ouvrirAlice();
        const creil = screen.getByRole("button", { name: "Magasin de Creil" });
        const senlis = screen.getByRole("button", { name: "Magasin de Senlis" });
        expect([creil, senlis].map((b) => b.getAttribute("aria-pressed"))).toEqual(["true", "true"]);
        fireEvent.click(creil);
        enregistrer();
        await waitFor(() => expect(m.ecrireEquipe).toHaveBeenCalledTimes(1));
        expect(m.ecrireEquipe.mock.calls[0][0].body.personnes[0]).toMatchObject({ etablissements: ["senlis"], etablissement: "senlis" });

        cleanup();
        m.ecrireEquipe.mockClear();
        avecAlice({ etablissements: ["creil"] });
        rendre(<OngletEquipe baseRattachee />);
        await ouvrirAlice();
        fireEvent.click(screen.getByRole("button", { name: "Magasin de Creil" }));
        enregistrer();
        await waitFor(() => expect(m.ecrireEquipe).toHaveBeenCalledTimes(1));
        const personne = m.ecrireEquipe.mock.calls[0][0].body.personnes[0];
        expect(personne.etablissements).toEqual([]);
        expect(personne.etablissement).toBeNull();
    });

    it("lit une ancienne réponse (un seul lieu) comme une liste, et nettoie le contenu envoyé", () => {
        expect(lieuxDe({ etablissement: "creil" })).toEqual(["creil"]);
        expect(lieuxDe({ etablissement: null })).toEqual([]);
        expect(lieuxDe({ etablissement: "creil", etablissements: [] })).toEqual([]);
        const charge = charge_utile_equipe({ personnes: [{ cle: "p1", prenom: "A", etablissement: "creil" }], sujets: [] });
        expect(charge.personnes?.[0]).toMatchObject({ etablissements: ["creil"], etablissement: "creil" });
        const net = charge_utile_equipe({
            personnes: [{ cle: "p1", prenom: " A ", nom: "  ", mail: "", etablissement: "" }],
            sujets: [{ code: "devis", libelle: " Devis ", mots_declencheurs: [" prix ", ""] }],
        });
        expect(net.personnes?.[0]).toMatchObject({ prenom: "A", nom: null, mail: null, etablissement: null });
        expect(net.sujets?.[0]).toMatchObject({ libelle: "Devis", mots_declencheurs: ["prix"] });
    });
});
