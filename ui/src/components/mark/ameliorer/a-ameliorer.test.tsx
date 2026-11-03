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
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { FournisseurLangue } from "../langue/langue";
import { OngletIndicateurs } from "../qualite/OngletIndicateurs";
import { DetailProbleme } from "./DetailProbleme";
import { demandeAuBuilder, texteDeFrequence, titreLisible } from "./libelles";
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
}));

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
    lireLesSourcesApiV1BuilderSourcesGet: () => m.sources(),
    lireLeMiroirApiV1BuilderMiroirReglageGet: vi.fn(),
    reglerLeMiroirApiV1BuilderMiroirReglagePut: vi.fn(),
    reglerUneSourceApiV1BuilderSourcesBriquePut: vi.fn(),
}));
// Un objet stable : le vrai `useAuth` ne rend pas un nouvel utilisateur à chaque rendu (les effets en dépendent).
const SESSION = vi.hoisted(() => ({ user: { id: "u-1" }, loading: false }));
vi.mock("@/lib/auth", () => ({ useAuth: () => SESSION }));
vi.mock("next/navigation", () => ({ useRouter: () => ({ push: m.push }), usePathname: () => "/labo/a-ameliorer" }));

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
});

describe("Le détail d'un problème", () => {
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
