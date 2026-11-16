/**
 * [.mark] Module Restauration, lot 20 (F11, F12) : l'écran Caisse / POS et la fenêtre Caisse / POS de l'essai, sur les routes de la caisse de démo (simulées ici).
 *
 * | Test | Ce qu'il prouve |
 * |---|---|
 * | écran | le restaurant de test, ses onglets, sa carte (ruptures par la caisse, un code après l'autre) ; les zones se gardent en centimes ; un fichier se transmet ; une photo se lit, se propose, puis s'importe sur confirmation |
 * | comportements | « Refuse » pose le contrôle de la caisse ; un scénario se met en place ; rien d'écrit sans geste |
 * | fenêtre | collée à la fenêtre d'appel (data-essai-panneau), total, TVA et remise dès l'ouverture, le panier en direct, ce que la caisse a reçu ; la rupture et le prix sont des gestes de la caisse |
 * | menu « + » | absent hors du Labo ; au Labo il pose la fenêtre |
 */
import { act, cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { FournisseurLangue } from "../langue/langue";

const m = vi.hoisted(() => ({
    etat: vi.fn(), liste: vi.fn(), detail: vi.fn(), regler: vi.fn(), geste: vi.fn(), importer: vi.fn(), photo: vi.fn(), scan: vi.fn(), poserScan: vi.fn(),
    scenario: vi.fn(), brancher: vi.fn(), panier: vi.fn(), creer: vi.fn(), dupliquer: vi.fn(), supprimer: vi.fn(), enregistrerScenario: vi.fn(), supprimerScenario: vi.fn(),
}));

vi.mock("./simulation-donnees", async (importOriginal) => ({
    ...(await importOriginal<typeof import("./simulation-donnees")>()),
    lireLEtat: m.etat, lireLesRestos: m.liste, lireUnResto: m.detail, reglerUnResto: m.regler, faireUnGeste: m.geste, importerUneCarte: m.importer, lireUnePhoto: m.photo,
    lireLeReglageDuScan: m.scan, poserLeReglageDuScan: m.poserScan, mettreUnScenarioEnPlace: m.scenario, brancherUnResto: m.brancher, lireLePanier: m.panier,
    creerUnResto: m.creer, dupliquerUnResto: m.dupliquer, supprimerUnResto: m.supprimer, enregistrerUnScenario: m.enregistrerScenario, supprimerUnScenario: m.supprimerScenario,
}));
vi.mock("@/lib/auth", () => {
    const auth = { isAuthenticated: true, loading: false, user: { id: "u-1" }, getAccessToken: async () => "jeton" };
    return { useAuth: () => auth };
});
vi.mock("sonner", () => ({ toast: { error: vi.fn(), success: vi.fn() } }));
vi.mock("../studio/liste", () => ({
    Liste: ({ valeur, changer, options, libelle }: { valeur: string; changer: (v: string) => void; options: ({ valeur: string; libelle: string } | string)[]; libelle?: string }) => (
        <select aria-label={libelle ?? "liste"} value={valeur} onChange={(e) => changer(e.target.value)}>
            {options.map((o) => typeof o === "string" ? <option key={o} value={o}>{o}</option> : <option key={o.valeur} value={o.valeur}>{o.libelle}</option>)}
        </select>),
}));

import { FenetreCaisse, MenuSimulateurs, useCaisseEssai } from "./fenetre-caisse";
import { EcranCaissePos } from "./simulation";

const CARTE = {
    format: "mark-carte-commune/1", categories: [{ id: "PIZ", nom: "Pizzas" }], groupes: [], formules: [],
    produits: [{ id: "REINE", nom: "Reine", description: null, categorie_id: "PIZ", declinaisons: [{ id: "REINE-S", nom: "Senior", code_caisse: "REINE-S", prix: 1250 }, { id: "REINE-J", nom: "Junior", code_caisse: "REINE-J", prix: 1050 }] }],
};
const RESTO = (plus = {}) => ({
    id: 5, nom: "Pizzeria de test", point_de_vente: "t1-0", etat: "ouvert", minutes_en_plus: 0, scenario: null, etablissement_cle: "un", branche: true, comportement: {},
    reglages: { delai: 20, types_de_commande: ["emporter", "livraison"], paiements: ["carte"], zones: [] }, carte: CARTE, stocks: [], clients: [], commandes: [], messages: [], ...plus,
});
const LISTE = { restaurants: [RESTO()], scenarios: [{ cle: "tout-va-bien", nom: "Tout va bien", etat: "ouvert", minutes_en_plus: 0, comportement: { reponse: "accepte" } }, { cle: "caisse-muette", nom: "Caisse muette", etat: "ouvert", minutes_en_plus: 0, comportement: { reponse: "silence" } }], etablissements: [{ id: 9, cle: "un", nom: "Casa" }] };

const ok = (data: unknown) => Promise.resolve({ data });
beforeEach(() => {
    window.localStorage.setItem("mark.langue", "fr");
    m.etat.mockReturnValue(ok({ active: true }));
    m.liste.mockReturnValue(ok(LISTE));
    m.detail.mockImplementation(() => ok(RESTO()));
    for (const f of [m.regler, m.geste, m.importer, m.scenario, m.brancher, m.poserScan, m.enregistrerScenario]) f.mockReturnValue(ok({ ok: true, produits: 1, categories: 1, cle: "x" }));
    m.regler.mockImplementation(() => ok(RESTO()));
    m.scan.mockReturnValue(ok({ actif: true }));
    m.panier.mockReturnValue(ok(null));
    useCaisseEssai.setState({ ouverte: false, runId: null });
});
afterEach(() => { cleanup(); vi.clearAllMocks(); document.body.innerHTML = ""; });

const monter = (ui: React.ReactNode) => render(<FournisseurLangue>{ui}</FournisseurLangue>);

describe("[.mark] l'écran Caisse / POS (F11)", () => {
    it("montre le restaurant de test, sa carte, et pose une rupture PAR LA CAISSE, un code après l'autre", async () => {
        monter(<EcranCaissePos />);
        expect(await screen.findByText("Reine")).toBeTruthy();
        expect(screen.getByText(/Tout est disponible/)).toBeTruthy();
        fireEvent.click(screen.getByRole("switch", { name: /Reine disponible/ }));
        await waitFor(() => expect(m.geste).toHaveBeenCalledTimes(2));
        expect(m.geste.mock.calls.map((c) => c[1])).toEqual([
            { geste: "rupture", code: "REINE-S", disponible: false }, { geste: "rupture", code: "REINE-J", disponible: false },
        ]);
    });

    it("pose les horaires dans la forme publique de HubRise (jours en anglais, créneaux from et to) et refuse un texte qui n'en est pas", async () => {
        monter(<EcranCaissePos />);
        await screen.findByText("Reine");
        fireEvent.click(screen.getByRole("button", { name: "Restaurant" }));
        const lundi = screen.getByRole("textbox", { name: "Lundi" });
        fireEvent.change(lundi, { target: { value: "11:30-14:30, 18:00-01:00" } });
        fireEvent.blur(lundi);
        await waitFor(() => expect(m.regler).toHaveBeenCalledTimes(1));
        expect(m.regler.mock.calls[0][1]).toEqual({ reglages: { horaires: { monday: [{ from: "11:30", to: "14:30" }, { from: "18:00", to: "01:00" }] } } });
        const mardi = screen.getByRole("textbox", { name: "Mardi" });
        fireEvent.change(mardi, { target: { value: "midi" } });
        fireEvent.blur(mardi);
        expect(await screen.findByText(/Écris 11:30-14:30/)).toBeTruthy();
        expect(m.regler).toHaveBeenCalledTimes(1); // rien d'envoyé pour un texte illisible
    });

    it("enregistre les zones de livraison en centimes, jamais en euros flottants", async () => {
        monter(<EcranCaissePos />);
        fireEvent.click(await screen.findByRole("button", { name: /^Livraison/ }));
        fireEvent.click(screen.getByRole("button", { name: /Ajouter une zone/ }));
        fireEvent.change(screen.getByRole("textbox", { name: "Communes" }), { target: { value: "Beauvais, Allonne" } });
        fireEvent.change(screen.getByRole("textbox", { name: "Frais" }), { target: { value: "2,5" } });
        fireEvent.change(screen.getByRole("textbox", { name: "Minimum" }), { target: { value: "15" } });
        fireEvent.click(screen.getByRole("button", { name: /Enregistrer les zones/ }));
        await waitFor(() => expect(m.regler).toHaveBeenCalled());
        expect(m.regler.mock.calls[0][1]).toEqual({ reglages: { zones: [{ nom: "Zone 1", communes: "Beauvais, Allonne", frais: 250, minimum: 1500, delai: 30 }] } });
    });

    it("transmet un fichier de carte, et lit une photo : la proposition ne s'importe qu'après confirmation", async () => {
        monter(<EcranCaissePos />);
        await screen.findByText("Reine");
        const fichier = document.querySelector<HTMLInputElement>("input[type=file][accept*=json]")!;
        fireEvent.change(fichier, { target: { files: [new File([JSON.stringify(CARTE)], "carte.json", { type: "application/json" })] } });
        await waitFor(() => expect(m.importer).toHaveBeenCalledTimes(1));
        expect(m.importer.mock.calls[0][1]).toEqual(CARTE);
        m.photo.mockReturnValue(ok({ carte: CARTE, lus: 1, ecartes: 2 }));
        const image = document.querySelector<HTMLInputElement>("input[type=file][accept*=image]")!;
        fireEvent.change(image, { target: { files: [new File([new Uint8Array([137, 80, 78, 71])], "carte.png", { type: "image/png" })] } });
        await waitFor(() => expect(m.photo).toHaveBeenCalledTimes(1));
        expect(m.photo.mock.calls[0].slice(2)).toEqual(["image/png"]);
        expect(m.importer).toHaveBeenCalledTimes(1); // rien d'importé avant la confirmation
        fireEvent.click(await screen.findByRole("button", { name: "Importer" }));
        await waitFor(() => expect(m.importer).toHaveBeenCalledTimes(2));
    });

    it("pose le contrôle de la caisse quand elle « refuse », et met un scénario en place", async () => {
        monter(<EcranCaissePos />);
        fireEvent.click(await screen.findByRole("button", { name: "Comportements" }));
        fireEvent.click(screen.getByRole("button", { name: "Refuse" }));
        await waitFor(() => expect(m.regler).toHaveBeenCalled());
        expect(m.regler.mock.calls[0][1]).toEqual({ comportement: { reponse: "controle", controles: ["produit_inconnu", "prix_different", "ferme", "remise_inconnue"] } });
        fireEvent.click(screen.getByRole("button", { name: "Scénarios" }));
        fireEvent.click((await screen.findAllByRole("button", { name: "Mettre en place" }))[1]);
        await waitFor(() => expect(m.scenario).toHaveBeenCalledWith(5, "caisse-muette"));
    });
});

describe("[.mark] la fenêtre Caisse / POS de l'essai (F12)", () => {
    it("n'existe pas tant qu'elle n'est pas ouverte ; ouverte : titre, état, total, TVA et remise dès l'ouverture", async () => {
        monter(<FenetreCaisse />);
        expect(screen.queryByRole("dialog")).toBeNull();
        act(() => useCaisseEssai.getState().ouvrir(true));
        const fenetre = await screen.findByRole("dialog", { name: /Caisse \/ POS/ });
        expect(fenetre.textContent).toContain("Pizzeria de test");
        expect(fenetre.querySelector("[data-totaux]")!.textContent).toMatch(/Remise[\s\S]*TVA[\s\S]*Total/);
        expect(fenetre.textContent).toContain("Aucun article pour l'instant");
    });

    it("se colle à la gauche de la fenêtre d'appel, de la même hauteur", async () => {
        const appel = document.createElement("div");
        appel.setAttribute("data-essai-panneau", "");
        appel.getBoundingClientRect = () => ({ top: 56, left: 1000, height: 700, width: 420, right: 1420, bottom: 756, x: 1000, y: 56, toJSON: () => ({}) });
        document.body.appendChild(appel);
        monter(<FenetreCaisse />);
        act(() => useCaisseEssai.getState().ouvrir(true));
        const fenetre = await screen.findByRole("dialog");
        await waitFor(() => expect(fenetre.style.height).toBe("700px"));
        expect(fenetre.style.top).toBe("56px");
        expect(fenetre.style.right).toBe(`${window.innerWidth - 1000 + 8}px`);
    });

    it("montre le panier en direct de l'appel, puis ce que la caisse a reçu et répondu", async () => {
        m.panier.mockReturnValue(ok({ version: 2, mode: "emporter", lignes: [{ nom: "Reine", quantite: 2 }] }));
        monter(<FenetreCaisse />);
        act(() => { useCaisseEssai.getState().poserRun(77); useCaisseEssai.getState().ouvrir(true); });
        expect(await screen.findByText(/2 × Reine/)).toBeTruthy();
        expect(m.panier).toHaveBeenCalledWith(9, 77);
        m.detail.mockImplementation(() => ok(RESTO({ commandes: [{ ref: "ab12", numero: "7f3c2a10-aaaa", statut: "accepted", mode: "collection", total: "14.00 EUR", heure_confirmee: null, creee_le: "x", remises: [], paiements: [], lignes: [{ nom: "Reine", taille: "Senior", quantite: "2.0", prix: "25.00 EUR", options: [] }] }], messages: [{ id: "m", type: "order.update", statut: "envoye", tentatives: 1 }] })));
        expect(await screen.findByText(/Commande acceptée par la caisse · n° ab12/, {}, { timeout: 4000 })).toBeTruthy();
        expect(screen.getByText(/order\.update \(envoye\)/)).toBeTruthy();
        expect(screen.getByText("14,00 €")).toBeTruthy(); // le total de la commande reçue
    });

    it("la rupture et le prix changés en plein appel sont des gestes de la caisse", async () => {
        monter(<FenetreCaisse />);
        act(() => useCaisseEssai.getState().ouvrir(true));
        const produit = await screen.findByRole("combobox", { name: "Produit" });
        fireEvent.change(produit, { target: { value: "REINE-S" } });
        fireEvent.click(screen.getByRole("button", { name: "Rupture" }));
        await waitFor(() => expect(m.geste).toHaveBeenCalledWith(5, { geste: "rupture", code: "REINE-S", disponible: false }));
        fireEvent.change(screen.getByRole("textbox", { name: /Nouveau prix/ }), { target: { value: "13,5" } });
        fireEvent.click(screen.getByRole("button", { name: /Changer le prix/ }));
        await waitFor(() => expect(m.geste).toHaveBeenCalledWith(5, { geste: "prix", code: "REINE-S", prix: 1350 }));
    });

    it("le menu « + » n'existe pas hors du Labo ; au Labo il pose la fenêtre", async () => {
        m.etat.mockReturnValue(ok({ active: false }));
        const { unmount } = monter(<MenuSimulateurs />);
        await waitFor(() => expect(m.etat).toHaveBeenCalled());
        expect(screen.queryByRole("button", { name: /Ajouter un simulateur/ })).toBeNull();
        unmount();
        m.etat.mockReturnValue(ok({ active: true }));
        monter(<MenuSimulateurs />);
        const plus = await screen.findByRole("button", { name: /Ajouter un simulateur/ });
        fireEvent.pointerDown(plus, { button: 0, ctrlKey: false });
        fireEvent.click(plus);
        const choix = await screen.findByRole("menuitemcheckbox", { name: /Caisse \/ POS/ });
        fireEvent.click(choix);
        await waitFor(() => expect(useCaisseEssai.getState().ouverte).toBe(true));
    });
});
