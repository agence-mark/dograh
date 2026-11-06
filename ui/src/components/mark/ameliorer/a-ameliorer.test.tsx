/**
 * [.mark] U8 : « À améliorer » (la boucle) et les indicateurs de « Qualité ».
 *
 * Ce que ce fichier prouve :
 *
 *     La liste montre une ligne par problème (gravité, titre, fréquence « N appels sur M », relevé par, cause) et les compteurs de chaque boîte ?
 *     Un état vide (« Rien à améliorer ») prend la place d'une liste vide, un chargement ou une erreur ne montrent jamais un tableau vide ?
 *     Le détail dit d'où vient le problème, ses cas regroupés, la réplique fautive, la cause et l'avancement ; « Ignorer » ne part qu'à la demande ?
 *     « Créer un test » et « Rejouer la suite » appellent les routes réelles ?
 *     Les indicateurs de Qualité viennent de la route ; sans appel, un état vide ?
 */
import { cleanup, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { FournisseurLangue } from "../langue/langue";
import { OngletIndicateurs } from "../qualite/OngletIndicateurs";
import { DetailProbleme } from "./DetailProbleme";
import { demandeAuBuilder, ORIGINES, texteDeFrequence, titreLisible } from "./libelles";
import { PageAAmeliorer } from "./PageAAmeliorer";

const m = vi.hoisted(() => ({
    liste: vi.fn(),
    detail: vi.fn(),
    changer: vi.fn(),
    test: vi.fn(),
    rejouer: vi.fn(),
    alertes: vi.fn(),
    aJuger: vi.fn(),
    personnes: vi.fn(),
    fil: vi.fn(),
    qualite: vi.fn(),
    sources: vi.fn(),
    push: vi.fn(),
    tous: vi.fn(),
    tousQualite: vi.fn(),
    lieu: { chemin: "/clients/12/a-ameliorer" },
}));

vi.mock("@/components/mark/studio/liste-deroulante", async () => await import("@/components/mark/studio/liste-deroulante-natif-test"));
vi.mock("@/client", () => ({
    lireLesAmeliorationsApiV1AmeliorationsGet: (o: unknown) => m.liste(o),
    lireUneAmeliorationApiV1AmeliorationsAmeliorationIdGet: (o: unknown) => m.detail(o),
    changerUneAmeliorationApiV1AmeliorationsAmeliorationIdPut: (o: unknown) => m.changer(o),
    creerUnTestDepuisLaRepliqueApiV1AmeliorationsAmeliorationIdTestPost: (o: unknown) => m.test(o),
    rejouerLaSuiteDeLAgentApiV1AmeliorationsAmeliorationIdRejouerPost: (o: unknown) => m.rejouer(o),
    lireLesAlertesApiV1AlertesGet: () => m.alertes(),
    lireLaFileAJugerApiV1AmeliorationsAJugerGet: () => m.aJuger(),
    lireLesPersonnesAssignablesApiV1TriPersonnesGet: () => m.personnes(),
    ouvrirUnFilApiV1BuilderFilsPost: (o: unknown) => m.fil(o),
    lireLaQualiteApiV1QualiteGet: (o: unknown) => m.qualite(o),
    ameliorationsDeTousLesClientsApiV1VuesEquipeAmeliorationsGet: (o: unknown) => m.tous(o),
    qualiteDeTousLesClientsApiV1VuesEquipeQualiteGet: (o: unknown) => m.tousQualite(o),
    lireLesSourcesApiV1BuilderSourcesGet: () => m.sources(),
    lireLeMiroirApiV1BuilderMiroirReglageGet: vi.fn(),
    reglerLeMiroirApiV1BuilderMiroirReglagePut: vi.fn(),
    reglerUneSourceApiV1BuilderSourcesBriquePut: vi.fn(),
}));
// Un objet stable : le vrai `useAuth` ne rend pas un nouvel utilisateur à chaque rendu (les effets en dépendent).
const SESSION = vi.hoisted(() => ({ user: { id: "u-1" }, loading: false }));
vi.mock("@/lib/auth", () => ({ useAuth: () => SESSION }));
vi.mock("next/navigation", () => ({ useRouter: () => ({ push: m.push }), usePathname: () => m.lieu.chemin }));

const LIGNE = {
    id: 7, workflow_id: 3, workflow_nom: "Accueil", titre: "Suit le parcours sans erreur", critere: "Suit le parcours sans erreur", etape: null,
    gravite: 3, frequence: { n: 4, sur: 112, genre: "appels" }, releve_par: "juge", cause: "prompt", etat: "a_trier", origine: null,
    origine_suggeree: "recette", assigne: null, version: 4, derniere_le: "2026-11-03T09:00:00+00:00",
};
const COMPTEURS = { a_trier: 1, en_cours: 2, testee: 0, publiee: 0 };
const DETAIL = {
    ...LIGNE, replique: "C'est noté pour jeudi", confiance: 0.9, correction: null,
    cas: [{ run_id: 1563, tour: 3, rang: 2, le: "2026-11-03T09:02:00+00:00", citation: "C'est noté" }], nb_cas: 1,
    avancement: [
        { temps: "test_cree", fait: false }, { temps: "brouillon", fait: false }, { temps: "rejoue", fait: false }, { temps: "publie", fait: false },
    ],
    recettes: [{ famille: "moules-etape", slug: "qualifier", version: 2 }],
};

const monter = (ui: React.ReactElement) => render(<FournisseurLangue>{ui}</FournisseurLangue>);

beforeEach(() => {
    m.liste.mockResolvedValue({ data: { lignes: [LIGNE], page: 0, a_une_suite: false, compteurs: COMPTEURS } });
    m.detail.mockResolvedValue({ data: DETAIL });
    m.changer.mockResolvedValue({ data: { ...DETAIL, etat: "ignoree" } });
    m.test.mockResolvedValue({ data: { ok: true } });
    m.rejouer.mockResolvedValue({ data: { ok: true, reussis: 2, total: 2, suite_complete: true, etat: "testee" } });
    m.alertes.mockResolvedValue({ data: { lignes: [], page: 0, a_une_suite: false } });
    m.aJuger.mockResolvedValue({ data: [] });
    m.personnes.mockResolvedValue({ data: [{ id: 5, nom: "equipe@exemple.test" }] });
    m.fil.mockResolvedValue({ data: { id: 99 } });
    m.qualite.mockResolvedValue({ data: QUALITE });
    m.sources.mockResolvedValue({ data: { sources: { juge_appels: "cle_api" } } });
});
afterEach(() => {
    cleanup();
    vi.clearAllMocks();
    window.history.replaceState(null, "", "/");
    m.lieu.chemin = "/clients/12/a-ameliorer";
});

describe("La liste de « À améliorer »", () => {
    it("montre une ligne par problème avec sa gravité, sa fréquence, qui l'a relevé et la cause", async () => {
        monter(<PageAAmeliorer />);
        const titre = await screen.findByText("Suit le parcours sans erreur");
        const ligne = titre.closest("tr")!;
        expect(ligne.textContent).toContain("4 appels sur 112");
        expect(ligne.textContent).toContain("Juge");
        expect(ligne.textContent).toContain("Prompt");
        expect(ligne.textContent).toContain("Accueil · v4");
        expect(ligne.querySelector("[data-gravite='3']")).not.toBeNull();
        expect(m.liste).toHaveBeenCalledWith({ query: { etat: "a_trier" } });
    });

    it("compte chaque boîte dans son onglet", async () => {
        monter(<PageAAmeliorer />);
        await screen.findByText("Suit le parcours sans erreur");
        const onglet = (nom: string) => screen.getAllByRole("tab").find((o) => o.textContent?.startsWith(nom))!;
        expect(onglet("À trier").textContent).toContain("1");
        expect(onglet("En cours").textContent).toContain("2");
        expect(onglet("Pannes et alertes").textContent).toContain("0");
        expect(screen.queryByRole("tab", { name: /À juger/ })).toBeNull(); // rien ne l'attend : pas d'onglet
    });

    it("dit « Rien à améliorer » quand la boîte est vide, et ne montre aucun tableau vide", async () => {
        m.liste.mockResolvedValue({ data: { lignes: [], page: 0, a_une_suite: false, compteurs: { a_trier: 0, en_cours: 0, testee: 0, publiee: 0 } } });
        monter(<PageAAmeliorer />);
        expect(await screen.findByText("Rien à améliorer")).toBeTruthy();
        expect(document.querySelector("table")).toBeNull();
    });

    it("propose de réessayer quand la lecture échoue", async () => {
        m.liste.mockResolvedValueOnce({ error: { detail: "x" } });
        monter(<PageAAmeliorer />);
        const reessayer = await screen.findByRole("button", { name: /Réessayer/ });
        fireEvent.click(reessayer);
        expect(await screen.findByText("Suit le parcours sans erreur")).toBeTruthy();
    });

    it("montre l'onglet « À juger » seulement quand des appels attendent Claude Code", async () => {
        m.aJuger.mockResolvedValue({ data: [{ id: "appel-5", type: "appel", workflow_id: 3, workflow_nom: "Accueil", run_id: 5, le: "2026-11-03T08:00:00+00:00", duree: 75, motif: "Dépannage" }] });
        monter(<PageAAmeliorer />);
        const onglet = await screen.findByRole("tab", { name: /À juger/ });
        fireEvent.click(onglet);
        expect(await screen.findByText("Dépannage")).toBeTruthy();
        expect(screen.getByText("1 min 15 s")).toBeTruthy();
    });

    it("V4 : les dates de « À juger » se disent « aujourd'hui 11:03 » et « hier 17:22 », comme la maquette", async () => {
        const il_y_a = (jours: number) => {
            const d = new Date();
            d.setDate(d.getDate() - jours);
            d.setHours(11, 3, 0, 0);
            return d.toISOString();
        };
        m.aJuger.mockResolvedValue({
            data: [
                { id: "appel-8", type: "appel", workflow_id: 3, workflow_nom: "Accueil", run_id: 8, le: il_y_a(0), duree: 40, motif: "Aujourd'hui-ci" },
                { id: "appel-9", type: "appel", workflow_id: 3, workflow_nom: "Accueil", run_id: 9, le: il_y_a(1), duree: 40, motif: "Hier-la" },
            ],
        });
        monter(<PageAAmeliorer />);
        fireEvent.click(await screen.findByRole("tab", { name: /À juger/ }));
        const aujourdhui = (await screen.findByText("Aujourd'hui-ci")).closest("tr")!;
        const hier = screen.getByText("Hier-la").closest("tr")!;
        expect(aujourdhui.textContent).toMatch(/aujourd'hui 11:03/);
        expect(hier.textContent).toMatch(/hier 11:03/);
    });

    it("juge des vrais appels sur Claude Code : l'onglet « À juger » existe même vide et dit « Rien à juger »", async () => {
        m.sources.mockResolvedValue({ data: { sources: { juge_appels: "claude_code" } } });
        monter(<PageAAmeliorer />);
        const onglet = await screen.findByRole("tab", { name: /À juger/ });
        expect(onglet.textContent).toContain("0");
        fireEvent.click(onglet);
        expect(await screen.findByText("Rien à juger")).toBeTruthy();
        expect(document.querySelector("table")).toBeNull();
    });

    it("une lecture refusée (403) montre l'état « accès », pas une erreur à réessayer", async () => {
        m.liste.mockResolvedValue({ error: { detail: "x" }, response: { status: 403 } });
        monter(<PageAAmeliorer />);
        expect(await screen.findByText(/Réservé aux administrateurs/)).toBeTruthy();
        expect(screen.queryByRole("button", { name: /Réessayer/ })).toBeNull();
    });

    it("liste les pannes avec leur type et si le client a été prévenu", async () => {
        m.alertes.mockResolvedValue({
            data: { lignes: [{ run_id: 20, workflow_id: 3, workflow_nom: "Accueil", id: "alerte:0", type: "transfert_echoue", detail: "numéro injoignable", heure: "2026-11-02T19:12:00+00:00", mail: "envoye" }], page: 0, a_une_suite: false },
        });
        window.history.replaceState(null, "", "/?onglet=pannes");
        monter(<PageAAmeliorer />);
        expect(await screen.findByText(/numéro injoignable/)).toBeTruthy();
        expect(screen.getByText("mail envoyé")).toBeTruthy();
    });

    it("F-2 : l'onglet Pannes et alertes mène aux alertes de Qualité, dans le même espace", async () => {
        m.alertes.mockResolvedValue({ data: { lignes: [], page: 0, a_une_suite: false } });
        window.history.replaceState(null, "", "/?onglet=pannes");
        monter(<PageAAmeliorer />);
        const lien = await screen.findByRole("link", { name: /Voir toutes les alertes/ });
        expect(lien.getAttribute("href")).toBe("/clients/12/qualite?onglet=alertes");
    });
});

describe("Le détail d'un problème", () => {
    beforeEach(() => {
        m.lieu.chemin = "/labo/a-ameliorer";
    });

    const ouvrir = async (apres = vi.fn(), fermer = vi.fn()) => {
        monter(<DetailProbleme id={7} fermer={fermer} apres={apres} />);
        await screen.findByText("« C'est noté pour jeudi »");
        return { apres, fermer };
    };

    it("dit d'où il vient, ses cas, la réplique fautive, la cause avec sa confiance et les quatre temps", async () => {
        await ouvrir();
        expect(screen.getByText(/n° 1563/)).toBeTruthy();
        expect(screen.getByText(/Prompt/)).toBeTruthy();
        expect(screen.getByText(/confiance 0,90/)).toBeTruthy();
        for (const temps of ["Test créé depuis la réplique", "Correction posée dans le brouillon", "Suite de tests rejouée (N × 3)", "Publication par une personne"]) {
            expect(screen.getByText(temps)).toBeTruthy();
        }
        expect(screen.getByText("moules-etape · qualifier")).toBeTruthy(); // origine « recette » suggérée : les recettes de l'agent
        expect(screen.queryByText("Correction proposée par le builder")).toBeNull(); // rien d'inventé : aucune correction posée
    });

    it("montre la correction proposée seulement quand le builder en a posé une", async () => {
        m.detail.mockResolvedValue({ data: { ...DETAIL, correction: { avant: "Confirme le créneau.", apres: "Appelle reserver_creneau.", etape: "Dépannage" } } });
        await ouvrir();
        expect(screen.getByText("- Confirme le créneau.")).toBeTruthy();
        expect(screen.getByText("+ Appelle reserver_creneau.")).toBeTruthy();
    });

    it("crée le test depuis la réplique et recharge l'avancement", async () => {
        await ouvrir();
        fireEvent.click(screen.getByRole("button", { name: "Créer un test depuis la réplique" }));
        await waitFor(() => expect(m.test).toHaveBeenCalledWith({ path: { amelioration_id: 7 }, body: {} }));
        await waitFor(() => expect(m.detail).toHaveBeenCalledTimes(2));
    });

    it("rejoue toute la suite, recharge et prévient la liste", async () => {
        const { apres } = await ouvrir();
        fireEvent.click(screen.getByRole("button", { name: "Rejouer la suite" }));
        await waitFor(() => expect(m.rejouer).toHaveBeenCalledWith({ path: { amelioration_id: 7 } }));
        await waitFor(() => expect(apres).toHaveBeenCalled());
    });

    it("ouvre une conversation avec le builder, avec les données du problème seulement", async () => {
        await ouvrir();
        fireEvent.click(screen.getByRole("button", { name: "Discuter avec le builder" }));
        await waitFor(() => expect(m.push).toHaveBeenCalledWith("/labo/builder/99"));
        const message = m.fil.mock.calls[0][0].body.message as string;
        expect(message).toContain("Accueil");
        expect(message).toContain("C'est noté pour jeudi");
        expect(message).toContain("4 sur 112");
    });

    it("SE-16 : plafond du mois atteint (402), la fenêtre propose « Continuer quand même », qui renvoie la demande avec le dépassement", async () => {
        m.fil.mockResolvedValueOnce({ error: { detail: "x" }, response: { status: 402 } });
        await ouvrir();
        fireEvent.click(screen.getByRole("button", { name: "Discuter avec le builder" }));
        const fenetre = await screen.findByRole("dialog", { name: "Budget du mois atteint" });
        expect(m.push).not.toHaveBeenCalled();
        expect(m.fil.mock.calls[0][0].body.depasser_le_plafond).toBeUndefined();
        fireEvent.click(within(fenetre).getByRole("button", { name: "Continuer quand même" }));
        await waitFor(() => expect(m.push).toHaveBeenCalledWith("/labo/builder/99"));
        expect(m.fil.mock.calls[1][0].body).toEqual(expect.objectContaining({ depasser_le_plafond: true, workflow_id: 3 }));
        expect(m.fil.mock.calls[1][0].body.message).toBe(m.fil.mock.calls[0][0].body.message);
    });

    it("SE-16 : « Annuler » dans la fenêtre du plafond n'envoie rien de plus, et une personne hors équipe (403) voit la phrase de réserve", async () => {
        m.fil.mockResolvedValueOnce({ error: { detail: "x" }, response: { status: 402 } });
        await ouvrir();
        fireEvent.click(screen.getByRole("button", { name: "Discuter avec le builder" }));
        fireEvent.click(within(await screen.findByRole("dialog", { name: "Budget du mois atteint" })).getByRole("button", { name: "Annuler" }));
        await waitFor(() => expect(screen.queryByRole("dialog", { name: "Budget du mois atteint" })).toBeNull());
        expect(m.fil).toHaveBeenCalledTimes(1);
        m.fil.mockResolvedValueOnce({ error: { detail: "x" }, response: { status: 402 } });
        m.fil.mockResolvedValueOnce({ error: { detail: "x" }, response: { status: 403 } });
        fireEvent.click(screen.getByRole("button", { name: "Discuter avec le builder" }));
        fireEvent.click(within(await screen.findByRole("dialog", { name: "Budget du mois atteint" })).getByRole("button", { name: "Continuer quand même" }));
        await waitFor(() => expect(m.fil).toHaveBeenCalledTimes(3));
        expect(m.push).not.toHaveBeenCalled();
    });

    it("n'ignore rien sans clic, puis ignore et ferme", async () => {
        const { fermer } = await ouvrir();
        expect(m.changer).not.toHaveBeenCalled();
        fireEvent.click(screen.getByRole("button", { name: "Ignorer" }));
        await waitFor(() => expect(m.changer).toHaveBeenCalledWith({ path: { amelioration_id: 7 }, body: { etat: "ignoree" } }));
        await waitFor(() => expect(fermer).toHaveBeenCalled());
    });

    it("change l'origine et la personne chargée par la route", async () => {
        await ouvrir();
        fireEvent.change(screen.getByLabelText("Origine"), { target: { value: "client" } });
        await waitFor(() => expect(m.changer).toHaveBeenCalledWith({ path: { amelioration_id: 7 }, body: { origine: "client" } }));
        fireEvent.change(screen.getByLabelText("Assigné à"), { target: { value: "5" } });
        await waitFor(() => expect(m.changer).toHaveBeenCalledWith({ path: { amelioration_id: 7 }, body: { assigne: 5 } }));
    });
});

describe("Les mots de l'écran", () => {
    const t = (x: { en: string; fr: string }) => x.fr;

    it("dit « N appels sur M » et, pour un test, les essais ratés ou « réussi, à revoir »", () => {
        expect(texteDeFrequence({ frequence: { n: 4, sur: 112, genre: "appels" } }, t)).toBe("4 appels sur 112");
        expect(texteDeFrequence({ frequence: { n: 1, sur: 3, genre: "essais" } }, t)).toBe("2 essais sur 3");
        expect(texteDeFrequence({ frequence: { n: 1, sur: 2, genre: "appels" } }, t)).toBe("1 appel sur 2");
        expect(texteDeFrequence({ frequence: { n: 2, sur: 3, genre: "essais" } }, t)).toBe("1 essai sur 3");
        expect(texteDeFrequence({ frequence: { n: 3, sur: 3, genre: "essais" } }, t)).toBe("réussi, à revoir");
    });

    it("traduit le titre d'une trace du code connue et garde celui du serveur sinon", () => {
        expect(titreLisible({ releve_par: "code", critere: "impasse", titre: "x" })).toEqual({ en: "Conversation going in circles", fr: "Conversation qui tourne en rond" });
        expect(titreLisible({ releve_par: "juge", critere: "impasse", titre: "Critère du juge" })).toBe("Critère du juge");
    });

    it("n'écrit dans la demande au builder que les données du problème", () => {
        const demande = demandeAuBuilder({ titre: "Numéro mal relu", workflow_nom: "Accueil", etape: "Prise", replique: null, frequence: { n: 2, sur: 10 } });
        expect(demande).toContain("Étape : Prise.");
        expect(demande).not.toContain("Réplique fautive");
    });

    it("F-1 : la demande donne le numéro du problème, pour que la correction soit écrite dans sa fiche", () => {
        const demande = demandeAuBuilder({ id: 12, titre: "Numéro mal relu", workflow_nom: "Accueil", frequence: { n: 2, sur: 10 } });
        expect(demande).toContain("Problème n° 12");
        expect(demande).toContain("amelioration_id");
        expect(demandeAuBuilder({ titre: "x", workflow_nom: "A", frequence: { n: 1, sur: 1 } })).not.toContain("amelioration_id");
    });
});

const RESUME = {
    appels: 4, appels_mesures: 4, juges: 2, note: 3.75, issues: 3, part_issue: 0.75, transferts: 1, part_transferts: 0.25, raccroches: 1,
    part_raccroches: 0.25, part_impasse: 0, reponse_mediane: 0.9, cout: 0.4,
};
const QUALITE = {
    jours: 7, global: RESUME,
    motifs: [{ motif: "Dépannage", appels: 31, part_resolu: 0.84 }, { motif: "Tarif", appels: 14, part_resolu: 0.57 }],
    agents: [{ workflow_id: 3, workflow_nom: "Accueil", version: 4, ...RESUME }],
    versions: [{ workflow_id: 3, workflow_nom: "Accueil", version: 4, ...RESUME }, { workflow_id: 3, workflow_nom: "Accueil", version: 3, ...RESUME, part_issue: 0.5 }],
};

describe("Les indicateurs de Qualité", () => {
    it("montre la bande de cinq chiffres, les motifs, les versions et les agents", async () => {
        monter(<OngletIndicateurs />);
        expect(await screen.findByText("Note du juge")).toBeTruthy();
        expect(screen.getByText("3,8")).toBeTruthy();
        expect(screen.getAllByText("75 %").length).toBeGreaterThan(0);
        expect(screen.getAllByText("0,9 s").length).toBeGreaterThan(0);
        expect(screen.getByText("Dépannage")).toBeTruthy();
        expect(screen.getByText("84 %")).toBeTruthy();
        expect(screen.getByText("Avant et après une publication")).toBeTruthy();
        expect(screen.getByText("v3")).toBeTruthy();
        expect(m.qualite).toHaveBeenCalledWith({ query: { jours: 7 } });
    });

    it("relit sur 30 jours à la demande", async () => {
        monter(<OngletIndicateurs />);
        await screen.findByText("Note du juge");
        fireEvent.click(screen.getByRole("button", { name: "30 jours" }));
        await waitFor(() => expect(m.qualite).toHaveBeenLastCalledWith({ query: { jours: 30 } }));
    });

    it("dit « Aucun appel encore » sans appel, jamais un tableau vide", async () => {
        m.qualite.mockResolvedValue({ data: { ...QUALITE, global: { ...RESUME, appels: 0 }, motifs: [], agents: [], versions: [] } });
        monter(<OngletIndicateurs />);
        expect(await screen.findByText("Aucun appel encore")).toBeTruthy();
        expect(document.querySelector("table")).toBeNull();
    });

    it("propose de réessayer quand la lecture échoue", async () => {
        m.qualite.mockResolvedValueOnce({ error: { detail: "x" } });
        monter(<OngletIndicateurs />);
        fireEvent.click(await screen.findByRole("button", { name: /Réessayer/ }));
        expect(await screen.findByText("Note du juge")).toBeTruthy();
    });
});

describe("La page des deux espaces", () => {
    it("monte la même page pour le Labo et pour un client", async () => {
        const labo = await import("@/app/labo/a-ameliorer/page");
        const client = await import("@/app/clients/[org]/a-ameliorer/page");
        expect(labo.default).toBe(PageAAmeliorer);
        expect(client.default).toBe(PageAAmeliorer);
    });
});

describe("Point d'origine « Attaque » (partie 3, sous-lot 4)", () => {
    it("une attaque qui a cédé a son libellé d'origine, à côté des autres", () => {
        expect(ORIGINES.attaque).toEqual({ en: "An attack that got through", fr: "Une attaque qui a cédé" });
        expect(Object.keys(ORIGINES)).toEqual(expect.arrayContaining(["client", "recette", "code", "deploiement", "attaque"]));
    });
});

describe("Sous-lot 10 : la vue « tous clients » du Labo (lecture seule)", () => {
    const LIGNE_EQUIPE = { ...LIGNE, organization_id: 41, organization_nom: "Plomberie Garnier" };
    beforeEach(() => {
        m.lieu.chemin = "/labo/a-ameliorer";
        m.tous.mockResolvedValue({ data: { lignes: [LIGNE_EQUIPE], page: 0, a_une_suite: false, compteurs: COMPTEURS } });
        m.tousQualite.mockResolvedValue({
            data: {
                jours: 7, mondial: RESUME, motifs: QUALITE.motifs, par_client: [], total_agents: 1, limit: 50, offset: 0,
                agents: [{ workflow_id: 3, workflow_nom: "Accueil", version: 4, organization_id: 41, organization_nom: "Plomberie Garnier", ...RESUME }],
            },
        });
    });

    it("À améliorer : dans le Labo la liste vient de la route d'équipe, avec le client, et la ligne mène chez lui", async () => {
        monter(<PageAAmeliorer />);
        const titre = await screen.findByText("Suit le parcours sans erreur");
        expect(m.tous).toHaveBeenCalledWith({ query: { etat: "a_trier" } });
        expect(m.liste).not.toHaveBeenCalled();
        const ligne = titre.closest("tr")!;
        expect(ligne.textContent).toContain("Plomberie Garnier · Accueil · v4");
        fireEvent.click(ligne);
        expect(m.push).toHaveBeenCalledWith("/clients/41/a-ameliorer?probleme=7");
    });

    it("À améliorer : chez un client, la route de l'espace reste la seule lue", async () => {
        m.lieu.chemin = "/clients/41/a-ameliorer";
        monter(<PageAAmeliorer />);
        await screen.findByText("Suit le parcours sans erreur");
        expect(m.tous).not.toHaveBeenCalled();
        expect(m.liste).toHaveBeenCalled();
    });

    it("À améliorer : le lien d'une ligne du Labo ouvre le détail du problème chez le client", async () => {
        m.lieu.chemin = "/clients/41/a-ameliorer";
        window.history.replaceState(null, "", "/?probleme=7");
        monter(<PageAAmeliorer />);
        await waitFor(() => expect(m.detail).toHaveBeenCalled());
    });

    it("Qualité : dans le Labo, tous les clients avec une colonne Client", async () => {
        m.lieu.chemin = "/labo/qualite";
        monter(<OngletIndicateurs />);
        expect(await screen.findByText("Note du juge")).toBeTruthy();
        expect(m.tousQualite).toHaveBeenCalledWith({ query: { jours: 7 } });
        expect(m.qualite).not.toHaveBeenCalled();
        expect(screen.getByRole("columnheader", { name: "Client" })).toBeTruthy();
        expect(screen.getByText("Plomberie Garnier")).toBeTruthy();
    });
});
