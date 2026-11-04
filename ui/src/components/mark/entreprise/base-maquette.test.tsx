/**
 * [.mark] K4b : les pages Base et automatisations, Vérification de l'appelant et Écoute et sons à la forme de la maquette
 * (tableaux nus, lignes en lecture, une fenêtre par bloc, explications dans un « ! »).
 *
 *   - Base : lignes de la base, conservation par table (tableau), conservation des appels (lignes + fenêtre), cases des listes
 *     (tableaux), « Changer de base » ; chaque écriture envoie ce qui est à l'écran ;
 *   - Après l'appel : un bloc en lignes, sa fenêtre enregistre ce qui est saisi, « Annuler » défait la saisie ;
 *   - Vérification : puces à la place des cases, « Enregistrer » à droite du titre ;
 *   - Lexique : tableau, la fenêtre d'un terme renvoie le lexique ENTIER avec la ligne changée.
 */
import { cleanup, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { FormeMaquette } from "../ecran/forme-maquette";
import { FournisseurLangue } from "../langue/langue";

const m = vi.hoisted(() => ({
    base: vi.fn(),
    rattacher: vi.fn(),
    creer: vi.fn(),
    conservation: vi.fn(),
    appels: vi.fn(),
    ecrireAppels: vi.fn(),
    listes: vi.fn(),
    ecrireListes: vi.fn(),
    apres: vi.fn(),
    ecrireApres: vi.fn(),
    verif: vi.fn(),
    ecrireVerif: vi.fn(),
    lexique: vi.fn(),
    ecrireLexique: vi.fn(),
}));

vi.mock("@/client/sdk.gen", async (importOriginal) =>
    (await import("../sdk-factice")).sdkFactice(await importOriginal(), {
        getBaseClientApiV1OrganizationsBaseClientGet: m.base,
        putBaseClientApiV1OrganizationsBaseClientPut: m.rattacher,
        postCreerApiV1OrganizationsBaseClientCreerPost: m.creer,
        putConservationApiV1OrganizationsBaseClientConservationPut: m.conservation,
        getConservationDesAppelsApiV1OrganizationsConservationAppelsGet: m.appels,
        putConservationDesAppelsApiV1OrganizationsConservationAppelsPut: m.ecrireAppels,
        getListesValeursApiV1OrganizationsListesValeursGet: m.listes,
        putListesValeursApiV1OrganizationsListesValeursPut: m.ecrireListes,
        getApresAppelApiV1OrganizationsApresAppelGet: m.apres,
        putApresAppelApiV1OrganizationsApresAppelPut: m.ecrireApres,
        getVerificationAppelantApiV1OrganizationsVerificationAppelantGet: m.verif,
        putVerificationAppelantApiV1OrganizationsVerificationAppelantPut: m.ecrireVerif,
        getLogicielsDossierApiV1OrganizationsVerificationAppelantLogicielsGet: () => Promise.resolve({ data: [] }),
        getLexiqueApiV1OrganizationsLexiqueGet: m.lexique,
        saveLexiqueApiV1OrganizationsLexiquePut: m.ecrireLexique,
        budgetLexiqueApiV1OrganizationsLexiqueBudgetPost: () => Promise.resolve({ data: undefined }),
        listerLesClesApiV1ClesGet: () => Promise.resolve({ data: [] }),
        fournisseursDesClesApiV1ClesFournisseursGet: () => Promise.resolve({ data: ["mistral", "smtp", "webhook"] }),
    }),
);
vi.mock("sonner", () => ({ toast: { success: vi.fn(), error: vi.fn() } }));
vi.mock("@/lib/auth", () => ({ useAuth: () => ({ user: { id: 1 }, loading: false }) }));
vi.stubGlobal("ResizeObserver", class { observe() {} unobserve() {} disconnect() {} });
Element.prototype.hasPointerCapture = vi.fn(() => false);
Element.prototype.scrollIntoView = vi.fn();

const { ThemeDonneesClient, useBaseClient } = await import("../parametres-organisation/ThemeDonneesClient");
const { ThemeApresAppel, useApresAppel } = await import("../parametres-organisation/ThemeApresAppel");
const { ThemeVerification } = await import("../parametres-organisation/ThemeVerification");
const { SectionLexiqueMetier } = await import("../SectionLexiqueMetier");

const BASE = {
    serveur_configure: true,
    nom_base: "client_essai",
    joignable: true,
    version: 21,
    version_attendue: 21,
    derniere_ecriture: "2026-10-06T21:00:00Z",
    refus: [],
    conservation: [
        { table_nom: "appel", duree_jours: 365, colonne_date: "debut", source: "défaut" },
        { table_nom: "demande", duree_jours: 730, colonne_date: "creee_le", source: "défaut" },
    ],
};
const DEFAUTS = { format: "conservation-appels-mark", version: 1, purge_activee: true, duree_mois: 6, audio_enregistre: false, audio_duree_mois: 6, essai_a_blanc: true };
const valeur = (code: string, libelle: string, cases: Record<string, boolean> = {}) => ({ code, libelle, ordre: 1, actif: true, regle_seul: false, opportunite: false, urgent: false, ...cases });
const LISTES = { listes: [{ liste: "issue_appel", cases: ["regle_seul"], valeurs: [valeur("autre", "Autre"), valeur("regle", "Réglé", { regle_seul: true })] }] };
const APRES = {
    reglages: {
        format: "apres-appel-mark",
        version: 1,
        synthese: { modele: "mistral-small-latest", cle: null, nom_assistant: null, nom_entreprise: null, consigne: null },
        smtp: { hote: "smtp.example.org", port: 587, securite: "starttls", utilisateur: null, mot_de_passe: null, expediteur: "agent@example.org", nom_expediteur: null },
        recapitulatif: { actif: false, heures: [8] },
        webhook: { url: null, secret: null },
    },
    adresses: { organisation: [], installation: [] },
    smtp_installation: false,
    base_rattachee: true,
    derniere_nuit: null,
};
const VERIF = { numero: true, question: true, code_sms: false, champs_controle: ["nom"], lisibles: { demandes: { facteurs_requis: 1, champs: ["reference"] } }, logiciel: null };
const LEXIQUE = {
    termes: [
        { terme: "Jøtul", variantes: ["Yotul"], prononciation: "yotoul", type: "nom", categorie: "Marque", a_ecouter: true, propose: false },
        { terme: "poêle", variantes: [], prononciation: null, type: "mot", categorie: null, a_ecouter: false, propose: true },
    ],
};

const rendre = (noeud: React.ReactNode) => render(<FournisseurLangue><FormeMaquette>{noeud}</FormeMaquette></FournisseurLangue>);
const reinitialiser = () => {
    m.base.mockReset().mockImplementation(() => Promise.resolve({ data: structuredClone(BASE) }));
    m.rattacher.mockReset().mockImplementation(({ body }: { body: { nom_base: string } }) => Promise.resolve({ data: { ...BASE, nom_base: body.nom_base } }));
    m.creer.mockReset().mockImplementation(({ body }: { body: { nom_base: string } }) => Promise.resolve({ data: { ...BASE, nom_base: body.nom_base } }));
    m.conservation.mockReset().mockImplementation(({ body }: { body: unknown }) => Promise.resolve({ data: { ...BASE, conservation: body } }));
    m.appels.mockReset().mockImplementation(() => Promise.resolve({ data: { reglages: { ...DEFAUTS }, audio_autorise_par_l_installation: true, dernier_passage: null } }));
    m.ecrireAppels.mockReset().mockImplementation(({ body }: { body: unknown }) => Promise.resolve({ data: { reglages: body, audio_autorise_par_l_installation: true, dernier_passage: null } }));
    m.listes.mockReset().mockImplementation(() => Promise.resolve({ data: structuredClone(LISTES) }));
    m.ecrireListes.mockReset().mockImplementation(() => Promise.resolve({ data: structuredClone(LISTES) }));
    m.apres.mockReset().mockImplementation(() => Promise.resolve({ data: structuredClone(APRES) }));
    m.ecrireApres.mockReset().mockImplementation(({ body }: { body: unknown }) => Promise.resolve({ data: { ...structuredClone(APRES), reglages: body } }));
    m.verif.mockReset().mockImplementation(() => Promise.resolve({ data: structuredClone(VERIF) }));
    m.ecrireVerif.mockReset().mockImplementation(({ body }: { body: unknown }) => Promise.resolve({ data: body }));
    m.lexique.mockReset().mockImplementation(() => Promise.resolve({ data: structuredClone(LEXIQUE) }));
    m.ecrireLexique.mockReset().mockImplementation(({ body }: { body: unknown }) => Promise.resolve({ data: body }));
};
reinitialiser();
afterEach(() => {
    cleanup();
    reinitialiser();
});

const Donnees = () => {
    const base = useBaseClient();
    return <ThemeDonneesClient ouvert onBasculer={() => {}} ouvrir={() => {}} signaler={vi.fn()} base={base} plat sansTitre />;
};
const Apres = () => {
    const apresAppel = useApresAppel();
    return <ThemeApresAppel ouvert onBasculer={() => {}} ouvrir={() => {}} signaler={vi.fn()} apresAppel={apresAppel} plat sansTitre />;
};

describe("[.mark] K4b : Base et automatisations", () => {
    it("lit la base en lignes, avec « Valeurs refusées : aucune » et un « ! », et la conservation en tableau nu", async () => {
        rendre(<Donnees />);
        const etat = await screen.findByTestId("etat-base-client");
        expect(etat.textContent).toContain("client_essai");
        expect(etat.textContent).toContain("21 / 21");
        expect(etat.textContent).toContain("Valeurs refusées");
        expect(etat.textContent).toContain("aucune");
        const tableau = (await screen.findByLabelText("Appels")).closest("table")!;
        expect(within(tableau).getAllByRole("row")).toHaveLength(3);
        expect(screen.queryByText(/Combien de temps chaque donnée/)).toBeNull();
    });

    it("n'enregistre la conservation que changée, et envoie les durées à l'écran", async () => {
        rendre(<Donnees />);
        const bouton = await screen.findByTestId("enregistrer-conservation");
        expect((bouton as HTMLButtonElement).disabled).toBe(true);
        fireEvent.change(screen.getByLabelText("Appels"), { target: { value: "400" } });
        expect((bouton as HTMLButtonElement).disabled).toBe(false);
        fireEvent.click(bouton);
        await waitFor(() => expect(m.conservation).toHaveBeenCalled());
        expect(m.conservation.mock.calls[0][0].body[0]).toMatchObject({ table_nom: "appel", duree_jours: 400 });
        fireEvent.change(screen.getByLabelText("Demandes"), { target: { value: "0" } });
        expect((screen.getByTestId("enregistrer-conservation") as HTMLButtonElement).disabled).toBe(true);
    });

    it("la conservation des appels : quatre lignes, la fenêtre enregistre ce qui est saisi, « Annuler » le défait", async () => {
        rendre(<Donnees />);
        const bloc = await waitFor(() => {
            const b = document.getElementById("donnees-conservation-appels");
            expect(b).not.toBeNull();
            return b as HTMLElement;
        });
        expect(bloc.textContent).toContain("Vider les copies des anciens appels");
        expect(bloc.textContent).toContain("6 mois");
        expect(bloc.textContent).toContain("Aucun passage");
        fireEvent.click(within(bloc).getByRole("button", { name: "Modifier" }));
        const duree = (await screen.findByLabelText(/Mois de conservation : verbatim/)) as HTMLInputElement;
        fireEvent.change(duree, { target: { value: "9" } });
        fireEvent.click(screen.getByRole("button", { name: "Annuler" }));
        expect(m.ecrireAppels).not.toHaveBeenCalled();
        fireEvent.click(within(bloc).getByRole("button", { name: "Modifier" }));
        expect(((await screen.findByLabelText(/Mois de conservation : verbatim/)) as HTMLInputElement).value).toBe("6");
        fireEvent.change(screen.getByLabelText(/Mois de conservation : verbatim/), { target: { value: "9" } });
        fireEvent.click(screen.getByRole("button", { name: "Enregistrer la conservation des appels" }));
        await waitFor(() => expect(m.ecrireAppels).toHaveBeenCalled());
        expect(m.ecrireAppels.mock.calls[0][0].body.duree_mois).toBe(9);
    });

    it("les cases des listes : un tableau par liste, un interrupteur par case, seules les cases changées partent", async () => {
        rendre(<Donnees />);
        const interrupteur = await screen.findByRole("switch", { name: /Autre : Compte comme réglé seul/ });
        const bouton = screen.getByTestId("enregistrer-listes-valeurs") as HTMLButtonElement;
        expect(bouton.disabled).toBe(true);
        fireEvent.click(interrupteur);
        expect(bouton.disabled).toBe(false);
        fireEvent.click(bouton);
        await waitFor(() => expect(m.ecrireListes).toHaveBeenCalled());
        expect(m.ecrireListes.mock.calls[0][0].body.valeurs).toEqual([{ liste: "issue_appel", code: "autre", regle_seul: true }]);
    });

    it("« Changer de base » ouvre la fenêtre : un geste (créer ou rattacher), un seul « Enregistrer » ; détacher envoie null", async () => {
        rendre(<Donnees />);
        fireEvent.click(await screen.findByTestId("changer-de-base"));
        const geste = await screen.findByTestId("geste-base-client");
        // Comme la maquette : « Créer une base » d'abord, même quand une base est déjà rattachée.
        expect(within(geste).getByRole("button", { name: "Créer une base" }).getAttribute("aria-pressed")).toBe("true");
        fireEvent.change(await screen.findByLabelText("Nom de la base"), { target: { value: "client_neuf" } });
        fireEvent.click(screen.getByTestId("enregistrer-base-client"));
        // L-4 : une base est déjà rattachée, créer la détache : un second clic le confirme (l'ancienne reste sur le serveur).
        expect((await screen.findByTestId("confirmer-changement-de-base")).textContent).toMatch(/reste sur le serveur/);
        expect(m.creer).not.toHaveBeenCalled();
        fireEvent.click(screen.getByTestId("enregistrer-base-client"));
        await waitFor(() => expect(m.creer).toHaveBeenCalledWith({ body: { nom_base: "client_neuf" } }));
        expect(m.rattacher).not.toHaveBeenCalled();
        fireEvent.click(await screen.findByTestId("changer-de-base"));
        fireEvent.click(within(await screen.findByTestId("geste-base-client")).getByRole("button", { name: "Rattacher une base existante" }));
        fireEvent.change(await screen.findByLabelText("Nom de la base"), { target: { value: "client_b" } });
        fireEvent.click(screen.getByTestId("enregistrer-base-client"));
        await waitFor(() => expect(m.rattacher).toHaveBeenCalledWith({ body: { nom_base: "client_b" } }));
        fireEvent.click(await screen.findByTestId("changer-de-base"));
        fireEvent.click(await screen.findByTestId("detacher-base-client"));
        await waitFor(() => expect(m.rattacher).toHaveBeenLastCalledWith({ body: { nom_base: null } }));
    });

    it("L-4 : changer le nom après la question la repose ; sans base rattachée, créer part tout de suite (rien à détacher)", async () => {
        rendre(<Donnees />);
        fireEvent.click(await screen.findByTestId("changer-de-base"));
        fireEvent.change(await screen.findByLabelText("Nom de la base"), { target: { value: "client_neuf" } });
        fireEvent.click(screen.getByTestId("enregistrer-base-client"));
        await screen.findByTestId("confirmer-changement-de-base");
        fireEvent.change(screen.getByLabelText("Nom de la base"), { target: { value: "client_autre" } });
        expect(screen.queryByTestId("confirmer-changement-de-base")).toBeNull();
        expect(m.creer).not.toHaveBeenCalled();
        cleanup();
        m.base.mockImplementation(() => Promise.resolve({ data: { ...BASE, nom_base: null, joignable: false, version: null, conservation: [] } }));
        rendre(<Donnees />);
        fireEvent.click(await screen.findByTestId("changer-de-base"));
        fireEvent.change(await screen.findByLabelText("Nom de la base"), { target: { value: "client_premier" } });
        fireEvent.click(screen.getByTestId("enregistrer-base-client"));
        await waitFor(() => expect(m.creer).toHaveBeenCalledWith({ body: { nom_base: "client_premier" } }));
        expect(screen.queryByTestId("confirmer-changement-de-base")).toBeNull();
    });

    it("sans base : l'état vide « Aucune base rattachée » et un seul geste", async () => {
        m.base.mockImplementation(() => Promise.resolve({ data: { ...BASE, nom_base: null, joignable: false, version: null, conservation: [] } }));
        rendre(<Donnees />);
        expect(await screen.findByText("Aucune base rattachée")).toBeTruthy();
        expect(screen.queryByTestId("enregistrer-conservation")).toBeNull();
        expect(screen.getByTestId("changer-de-base").textContent).toContain("Créer ou rattacher");
    });
});

describe("[.mark] K4b : Après l'appel", () => {
    it("lit chaque bloc en lignes ; la fenêtre de la synthèse enregistre le modèle saisi", async () => {
        rendre(<Apres />);
        const bloc = await waitFor(() => {
            const b = document.getElementById("apres-appel-synthese");
            expect(b).not.toBeNull();
            return b as HTMLElement;
        });
        expect(bloc.textContent).toContain("mistral-small-latest");
        expect(document.getElementById("apres-appel-smtp")!.textContent).toContain("smtp.example.org · 587 · STARTTLS");
        expect(document.getElementById("apres-appel-recapitulatif")!.textContent).toContain("éteint");
        fireEvent.click(within(bloc).getByRole("button", { name: "Modifier" }));
        fireEvent.change(await screen.findByLabelText(/^Modèle/), { target: { value: "mistral-small-2603" } });
        fireEvent.click(screen.getByRole("button", { name: "Enregistrer" }));
        await waitFor(() => expect(m.ecrireApres).toHaveBeenCalled());
        expect(m.ecrireApres.mock.calls[0][0].body.synthese.modele).toBe("mistral-small-2603");
    });

    it("« Annuler » défait la saisie : rien n'est envoyé et la ligne garde sa valeur", async () => {
        rendre(<Apres />);
        const bloc = await waitFor(() => {
            const b = document.getElementById("apres-appel-synthese");
            expect(b).not.toBeNull();
            return b as HTMLElement;
        });
        fireEvent.click(within(bloc).getByRole("button", { name: "Modifier" }));
        fireEvent.change(await screen.findByLabelText(/^Modèle/), { target: { value: "autre" } });
        fireEvent.click(screen.getByRole("button", { name: "Annuler" }));
        expect(m.ecrireApres).not.toHaveBeenCalled();
        expect(bloc.textContent).toContain("mistral-small-latest");
    });

    it("des heures qui n'en sont pas gardent la fenêtre ouverte et n'envoient rien", async () => {
        rendre(<Apres />);
        const bloc = await waitFor(() => {
            const b = document.getElementById("apres-appel-recapitulatif");
            expect(b).not.toBeNull();
            return b as HTMLElement;
        });
        fireEvent.click(within(bloc).getByRole("button", { name: "Modifier" }));
        fireEvent.click(await screen.findByRole("switch"));
        fireEvent.change(await screen.findByLabelText(/^Heures/), { target: { value: "25" } });
        fireEvent.click(screen.getByRole("button", { name: "Enregistrer" }));
        expect(m.ecrireApres).not.toHaveBeenCalled();
        expect(screen.getByLabelText(/^Heures/)).toBeTruthy();
    });
});

describe("[.mark] K4b : Vérification de l'appelant", () => {
    const Verif = () => <ThemeVerification ouvert onBasculer={() => {}} ouvrir={() => {}} signaler={vi.fn()} plat />;

    it("les champs sont des puces (pressées = cochées) et « Enregistrer » envoie ce qui est à l'écran", async () => {
        rendre(<Verif />);
        const champs = await screen.findByTestId("verif-champs-controle");
        expect(document.querySelector('input[type="checkbox"]')).toBeNull();
        const nom = within(champs).getByRole("button", { name: "Nom" });
        expect(nom.getAttribute("aria-pressed")).toBe("true");
        const bouton = screen.getByTestId("enregistrer-verification") as HTMLButtonElement;
        expect(bouton.disabled).toBe(true);
        fireEvent.click(within(champs).getByRole("button", { name: "Code postal" }));
        fireEvent.click(screen.getByTestId("verif-lisible-demandes-statut"));
        fireEvent.click(bouton);
        await waitFor(() => expect(m.ecrireVerif).toHaveBeenCalled());
        const corps = m.ecrireVerif.mock.calls[0][0].body;
        expect(corps.champs_controle.sort()).toEqual(["code_postal", "nom"]);
        expect(corps.lisibles.demandes.champs.sort()).toEqual(["reference", "statut"]);
    });

    it("plus de facteurs exigés qu'allumés : dit et bloque l'enregistrement", async () => {
        rendre(<Verif />);
        await screen.findByTestId("verif-champs-controle");
        fireEvent.change(screen.getAllByLabelText("Facteurs exigés")[0], { target: { value: "3" } });
        expect(screen.getByTestId("verif-inaccessible-demandes")).toBeTruthy();
        expect((screen.getByTestId("enregistrer-verification") as HTMLButtonElement).disabled).toBe(true);
    });
});

describe("[.mark] K4b : le lexique métier", () => {
    it("un tableau nu, un clic ouvre la fenêtre du terme, et l'écriture renvoie le lexique entier", async () => {
        rendre(<SectionLexiqueMetier />);
        const tableau = (await screen.findByText("Jøtul")).closest("table")!;
        expect(within(tableau).getAllByRole("row")).toHaveLength(3);
        expect(tableau.textContent).toContain("yotoul");
        fireEvent.click(screen.getByText("poêle"));
        const champ = (await screen.findAllByLabelText("Catégorie")).pop() as HTMLInputElement;
        fireEvent.change(champ, { target: { value: "Appareil" } });
        fireEvent.click(screen.getByRole("button", { name: "Enregistrer" }));
        await waitFor(() => expect(m.ecrireLexique).toHaveBeenCalled());
        const termes = m.ecrireLexique.mock.calls[0][0].body.termes;
        expect(termes).toHaveLength(2);
        expect(termes[0].terme).toBe("Jøtul");
        expect(termes[1]).toMatchObject({ terme: "poêle", categorie: "Appareil", type: "mot", propose: true });
    });

    it("V4 : la nature d'un terme a les trois valeurs de la maquette et fixe le type que le serveur lit", async () => {
        rendre(<SectionLexiqueMetier />);
        // Un terme d'avant le champ : « poêle » (mot) se lit « Mot du métier », « Jøtul » (nom) se lit « Marque ».
        const tableau = (await screen.findByText("Jøtul")).closest("table")!;
        expect(tableau.textContent).toContain("Marque");
        expect(tableau.textContent).toContain("Mot du métier");
        fireEvent.click(screen.getByText("poêle"));
        const fenetre = (await screen.findAllByLabelText("Catégorie")).pop()!.closest("[role=dialog]") as HTMLElement;
        for (const nature of ["Marque", "Nom propre", "Mot du métier"]) expect(within(fenetre).getByRole("button", { name: nature })).toBeTruthy();
        expect(within(fenetre).getByRole("button", { name: "Mot du métier" }).getAttribute("aria-pressed")).toBe("true");
        fireEvent.click(within(fenetre).getByRole("button", { name: "Nom propre" }));
        fireEvent.click(screen.getByRole("button", { name: "Enregistrer" }));
        await waitFor(() => expect(m.ecrireLexique).toHaveBeenCalled());
        expect(m.ecrireLexique.mock.calls[0][0].body.termes[1]).toMatchObject({ terme: "poêle", nature: "nom_propre", type: "nom" });
    });

    it("« + Terme » ouvre une fenêtre neuve : sans nom, rien ne part", async () => {
        rendre(<SectionLexiqueMetier />);
        await screen.findByText("Jøtul");
        fireEvent.click(screen.getByRole("button", { name: /Terme/ }));
        fireEvent.click(await screen.findByRole("button", { name: "Enregistrer" }));
        expect(m.ecrireLexique).not.toHaveBeenCalled();
        fireEvent.change(screen.getAllByLabelText("Terme").pop() as HTMLInputElement, { target: { value: "Godin" } });
        fireEvent.click(screen.getByRole("button", { name: "Enregistrer" }));
        await waitFor(() => expect(m.ecrireLexique).toHaveBeenCalled());
        expect(m.ecrireLexique.mock.calls[0][0].body.termes).toHaveLength(3);
    });
});
