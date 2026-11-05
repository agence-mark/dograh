/**
 * [.mark] Partie 3, L5b : la page de pilotage d'un client (décision 16 de l'audit).
 *
 * Questions de ce fichier :
 *
 *     La page affiche ce que la route de pilotage rend (chiffres, motifs, agents, à faire, relation, activité), sans rien recompter ?
 *     La période est 7 jours par défaut et un clic relit la route avec la nouvelle période ?
 *     Un chiffre indisponible dit comment l'activer ? Un client en installation montre sa liste à la place des chiffres ?
 *     Les branchements sont repliés quand tout va bien, listés avec « Régler » sinon ? Une lecture qui échoue se dit « illisible » ?
 *     « Rien à faire » n'est jamais affiché quand une lecture a échoué ? Les liens restent dans l'espace du client ?
 */
import { cleanup, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import AccueilClient from "./AccueilClient";
import { construireAFaire } from "./pilotage/a-faire";
import { lienDesAppelsDuMotif } from "./pilotage/Blocs";
import { valeurAffichee } from "./pilotage/format";
import type { ChiffrePilotage, PilotageClient } from "./pilotage/types";

const m = vi.hoisted(() => ({
    pilotage: vi.fn(),
    base: vi.fn(),
    apres: vi.fn(),
    connexions: vi.fn(),
    telephonie: vi.fn(),
    cles: vi.fn(),
    reprise: vi.fn(),
}));
vi.mock("next/navigation", () => ({ useParams: () => ({ org: "7" }), useRouter: () => ({ push: vi.fn() }) }));
vi.mock("next/link", () => ({ default: ({ children, href, ...r }: { children: React.ReactNode; href: string }) => <a href={href} {...r}>{children}</a> }));
vi.mock("@/lib/auth", () => ({ useAuth: () => ({ user: { id: "u" }, loading: false }) }));
vi.mock("@/components/mark/studio/nom-espace", () => ({ useNomEspace: () => "Chauffage Durand" }));
vi.mock("@/components/mark/studio/selecteur-espace", () => ({
    NouveauClient: ({ ouvert, organisationAReprendre }: { ouvert: boolean; organisationAReprendre?: number | null }) => {
        if (ouvert) m.reprise(organisationAReprendre);
        return ouvert ? <div data-testid="fenetre-installation">reprise {organisationAReprendre}</div> : null;
    },
}));
vi.mock("@/client/sdk.gen", () => ({
    pilotageDUnClientApiV1VuesEquipePilotageOrganizationIdGet: m.pilotage,
    getBaseClientApiV1OrganizationsBaseClientGet: m.base,
    getApresAppelApiV1OrganizationsApresAppelGet: m.apres,
    getConnexionsApiV1ConnecteursConnexionsGet: m.connexions,
    listTelephonyConfigurationsApiV1OrganizationsTelephonyConfigsGet: m.telephonie,
    listerLesClesApiV1ClesGet: m.cles,
}));

const chiffre = (id: ChiffrePilotage["id"], valeur: number | null, tendance: number | null, plus: Partial<ChiffrePilotage> = {}): ChiffrePilotage => ({
    id,
    valeur,
    precedente: null,
    tendance,
    disponible: valeur !== null,
    raison: null,
    ...plus,
});

const PILOTAGE: PilotageClient = {
    periode: "7j",
    jours: 7,
    en_service: true,
    chiffres: [
        chiffre("appels", 112, 12),
        chiffre("resolus", 76, 4),
        chiffre("transferes", 19, -9),
        chiffre("note", 4.3, 2),
        chiffre("cout", null, null, { raison: "prix" }),
        chiffre("duree", 172, 3),
    ],
    tronque: false,
    motifs: [
        { motif: "Dépannage", appels: 38, part_resolu: 0.71, part_transferts: 0.24, note: 4.1 },
        { motif: "Devis", appels: 11, part_resolu: 0.64, part_transferts: 0.18, note: null },
    ],
    agents: [
        { id: 3, nom: "Standard Chauffage Durand", version: 3, publie: true, part: 90, autres: [{ nom: "Accueil court", part: 10, version: 1 }], appels: 100, note: 4.3, pret: { etat: "pret", n: 0 } },
        { id: 4, nom: "Devis", version: null, publie: false, part: 100, autres: [], appels: 0, note: null, pret: { etat: "bloque", n: 2 } },
    ],
    alertes: { total: 1, liste: [{ id: "a1", type: "hausse_rates", workflow_id: 3, workflow_nom: "Standard", resume: "les appels ratés montent", levee_le: "2026-11-04T10:00:00+00:00" }] },
    problemes_graves: 2,
    installation: null,
    relation: {
        ouverts: 1,
        non_lus: 2,
        demandes_nouvelles: 0,
        dernier: { fil_id: 1, sujet: "Week-end", texte: "L'agent ne savait pas dire si vous intervenez le week-end.", auteur: "Paul Durand", cree_le: "2026-11-05T08:40:00+00:00" },
    },
    activite: [
        { id: 1, action: "agents.publier", qui: "Evan", par_builder: false, quand: "2026-11-04T17:20:00+00:00" },
        { id: 2, action: "agents.branche_creee", qui: "Pierre", par_builder: true, quand: "2026-11-04T16:48:00+00:00" },
    ],
    illisibles: [],
};

beforeEach(() => {
    m.pilotage.mockResolvedValue({ data: PILOTAGE });
    m.base.mockResolvedValue({ data: { nom_base: "client_durand", joignable: true } });
    m.apres.mockResolvedValue({ data: { base_rattachee: true } });
    m.connexions.mockResolvedValue({ data: { nango_configure: true, connexions: [{ integration: "google-calendar", connecteur: "Google Agenda", erreurs: 1 }, { integration: "hubspot", erreurs: 0 }] } });
    m.telephonie.mockResolvedValue({ data: { configurations: [{}] } });
    m.cles.mockResolvedValue({ data: [{}, {}] });
});
afterEach(() => {
    cleanup();
    Object.values(m).forEach((f) => f.mockReset());
});

const rendre = async () => {
    render(<AccueilClient />);
    await screen.findByText("Standard Chauffage Durand");
    await waitFor(() => expect(document.querySelector('[data-pilotage="branchements-a-regler"], [data-pilotage="branchements-ok"]')).toBeTruthy());
};

describe("la page de pilotage d'un client", () => {
    it("lit la route de pilotage du client de l'adresse, 7 jours par défaut, avec toutes les autres lectures en parallèle", async () => {
        await rendre();
        expect(m.pilotage).toHaveBeenCalledTimes(1);
        expect(m.pilotage).toHaveBeenCalledWith({ path: { organization_id: 7 }, query: { periode: "7j" } });
        expect(screen.getByRole("button", { name: "7 j" }).getAttribute("aria-pressed")).toBe("true");
        for (const f of [m.base, m.apres, m.connexions, m.telephonie, m.cles]) expect(f).toHaveBeenCalledTimes(1);
    });

    it("« À faire maintenant » : alerte, intégration à reconnecter, problèmes graves, avec « Régler » ou « Ouvrir » vers le client", async () => {
        await rendre();
        const alerte = document.querySelector('[data-a-faire="alerte-a1"]') as HTMLElement;
        expect(alerte.textContent).toContain("les appels ratés montent");
        expect(within(alerte).getByRole("link", { name: "Open" }).getAttribute("href")).toBe("/clients/7/qualite?onglet=alertes");
        const connexion = document.querySelector('[data-a-faire="connexion-google-calendar"]') as HTMLElement;
        expect(connexion.textContent).toContain("Google Agenda to reconnect");
        expect(within(connexion).getByRole("link", { name: "Fix" }).getAttribute("href")).toBe("/clients/7/integrations");
        const graves = document.querySelector('[data-a-faire="problemes-graves"]') as HTMLElement;
        expect(graves.textContent).toContain("2 serious problems wait to be sorted");
        expect(within(graves).getByRole("link", { name: "Open" }).getAttribute("href")).toBe("/clients/7/a-ameliorer");
        expect(document.querySelector('[data-pilotage="rien-a-faire"]')).toBeNull();
    });

    it("les chiffres de la période : valeur, tendance contre la période d'avant ; l'indisponible dit comment l'activer", async () => {
        await rendre();
        const chiffres = document.querySelector('[data-pilotage="chiffres"]') as HTMLElement;
        const texte = chiffres.textContent ?? "";
        expect(texte).toContain("112");
        expect(texte).toContain("76%");
        expect(texte).toContain("4.3");
        expect(texte).toContain("2 min 52");
        expect(texte).toContain("▲ +12 %");
        expect(texte).toContain("against the previous 7 j");
        expect(texte).toContain("▼ 9 %"); // les transferts baissent : bonne nouvelle, mais la flèche dit le sens
        expect(texte).toContain("The cost of the calls is not recorded");
        expect(within(chiffres).getByRole("link", { name: "Fill in the prices" }).getAttribute("href")).toBe("/clients/7/modeles");
    });

    it("un clic sur une période relit la route avec cette période", async () => {
        await rendre();
        fireEvent.click(screen.getByRole("button", { name: "30 j" }));
        await waitFor(() => expect(m.pilotage).toHaveBeenLastCalledWith({ path: { organization_id: 7 }, query: { periode: "30j" } }));
        expect(screen.getByRole("button", { name: "30 j" }).getAttribute("aria-pressed")).toBe("true");
        expect(m.pilotage).toHaveBeenCalledTimes(2);
        expect(m.base).toHaveBeenCalledTimes(1); // les branchements ne sont pas relus
    });

    it("les motifs : un clic ouvre les appels filtrés sur ce motif ; les agents disent branche, part, autres, appels, note, prêt", async () => {
        await rendre();
        const motifs = document.querySelector('[data-pilotage="motifs"]') as HTMLElement;
        expect(motifs.textContent).toContain("Dépannage");
        expect(motifs.textContent).toContain("71%");
        expect(motifs.textContent).toContain("24%");
        const agents = document.querySelector('[data-pilotage="agents"]') as HTMLElement;
        expect(agents.textContent).toContain("Main · v3");
        expect(agents.textContent).toContain("90 %");
        expect(agents.textContent).toContain("Accueil court 10 %");
        expect(agents.textContent).toContain("Ready");
        expect(agents.textContent).toContain("2 blocking");
        expect(agents.textContent).toContain("Draft");
        expect(within(agents).getByText("Standard Chauffage Durand").closest("tr")).toBeTruthy();
    });

    it("la colonne de droite : branchements listés avec « Régler » quand un va mal, relation compacte, activité", async () => {
        await rendre();
        const liste = document.querySelector('[data-pilotage="branchements-a-regler"]') as HTMLElement;
        const integrations = liste.querySelector('[data-branchement="integrations"]') as HTMLElement;
        expect(integrations.textContent).toContain("1 to reconnect");
        expect(within(integrations).getByRole("link", { name: "Fix" }).getAttribute("href")).toBe("/clients/7/integrations");
        expect(liste.querySelector('[data-branchement="base"] a')).toBeNull(); // ce qui va bien n'a pas de « Régler »
        const relation = document.querySelector('[data-pilotage="relation"]') as HTMLElement;
        expect(relation.textContent).toContain("2 unread");
        expect(relation.textContent).toContain("L'agent ne savait pas dire");
        expect(relation.textContent).toContain("Paul Durand");
        expect(relation.getAttribute("href")).toBe("/relation/clients/7");
        expect(screen.getByRole("link", { name: "Open the Hub" }).getAttribute("href")).toBe("/relation/clients");
        const activite = document.querySelector('[data-pilotage="activite"]') as HTMLElement;
        expect(activite.textContent).toContain("Evan");
        expect(activite.textContent).toContain("published an agent");
        expect(activite.textContent).toContain("Builder");
        expect(activite.textContent).toContain("created a branch");
    });

    it("quand tout va bien : « Rien à faire », branchements repliés, « Rien en attente », activité vide", async () => {
        m.pilotage.mockResolvedValue({ data: { ...PILOTAGE, alertes: { total: 0, liste: [] }, problemes_graves: 0, relation: { ouverts: 0, non_lus: 0, demandes_nouvelles: 0, dernier: null }, activite: [] } });
        m.connexions.mockResolvedValue({ data: { connexions: [{ integration: "hubspot", erreurs: 0 }] } });
        await rendre();
        expect(document.querySelector('[data-pilotage="rien-a-faire"]')).toBeTruthy();
        expect(document.querySelector('[data-pilotage="branchements-ok"]')?.textContent).toContain("All fine");
        expect(document.querySelector('[data-pilotage="relation-vide"]')?.textContent).toContain("Nothing waiting");
        expect(screen.getByText("Nothing for now")).toBeTruthy();
    });

    it("un client en installation : sa liste remplace les chiffres, « Reprendre » ouvre la fenêtre d'installation de CE client", async () => {
        const etapes = [1, 2, 3].map((numero) => ({ numero, titre: { en: `Step ${numero}`, fr: `Étape ${numero}` }, etat: numero === 1 ? "faite" : "a_faire" }));
        m.pilotage.mockResolvedValue({
            data: { ...PILOTAGE, en_service: false, chiffres: null, motifs: null, alertes: { total: 0, liste: [] }, problemes_graves: 0, installation: { etapes, prochaine: 2, faites: 1, total: 3 } },
        });
        render(<AccueilClient />);
        await screen.findByText("1 step out of 3");
        expect(document.querySelector('[data-pilotage="chiffres"]')).toBeNull();
        expect(screen.queryByRole("button", { name: "7 j" })).toBeNull(); // pas de sélecteur de période
        expect(document.querySelector('[data-etape="1"]')?.textContent).toContain("Step 1");
        const reprendre = within(document.querySelector('[data-etape="2"]') as HTMLElement).getByRole("button", { name: "Resume" });
        fireEvent.click(reprendre);
        expect((await screen.findByTestId("fenetre-installation")).textContent).toBe("reprise 7");
        // L'étape suivante est aussi dans « À faire maintenant ».
        expect(document.querySelector('[data-a-faire="installation"]')?.textContent).toContain("Installation: next step, Step 2");
    });

    it("une lecture qui échoue se dit « illisible » : jamais « Rien à faire », jamais un chiffre inventé", async () => {
        m.pilotage.mockResolvedValue({ data: { ...PILOTAGE, chiffres: null, motifs: null, alertes: null, problemes_graves: 0, relation: null, activite: null, illisibles: ["alertes", "chiffres", "relation", "activite"] } });
        m.base.mockResolvedValue({ error: { detail: "boom" } });
        m.connexions.mockResolvedValue({ data: { connexions: [] } });
        await rendre();
        expect(document.querySelector('[data-pilotage="rien-a-faire"]')).toBeNull();
        expect(document.querySelector('[data-pilotage="illisible"]')?.textContent).toContain("alerts");
        expect(document.querySelector('[data-pilotage="chiffres-illisibles"]')).toBeTruthy();
        expect(document.querySelector('[data-pilotage="relation-illisible"]')).toBeTruthy();
        expect(document.querySelector('[data-pilotage="activite-illisible"]')).toBeTruthy();
        expect(document.querySelector('[data-branchement="base"]')?.textContent).toContain("unreadable");
        expect(screen.queryByText(/boom/)).toBeNull();
    });

    it("la route refusée (403, 404) : état d'erreur avec « Réessayer », jamais le texte du serveur", async () => {
        m.pilotage.mockResolvedValue({ error: { detail: "Reserved to the .mark team" } });
        render(<AccueilClient />);
        await screen.findByRole("button", { name: /Try again|Réessayer/ });
        expect(screen.queryByText(/Reserved to/)).toBeNull();
    });

    it("« Ouvrir son portail » reste grisé avec sa raison", async () => {
        await rendre();
        const bouton = screen.getByRole("button", { name: /Open its portal/ }) as HTMLButtonElement;
        expect(bouton.disabled).toBe(true);
        expect(bouton.getAttribute("title")).toBe("The portal does not exist yet.");
    });
});

describe("les fonctions de la page", () => {
    it("l'ordre de « À faire » : alertes, intégrations, problèmes graves, installation", () => {
        const items = construireAFaire(
            { ...PILOTAGE, installation: { etapes: [{ numero: 2, titre: { en: "Team", fr: "Équipe" }, etat: "a_faire" }], prochaine: 2, faites: 0, total: 1 } },
            [{ integration: "x", erreurs: 2 }],
        );
        expect(items.map((i) => i.id)).toEqual(["alerte-a1", "connexion-x", "problemes-graves", "installation"]);
        expect(items.map((i) => i.gravite)).toEqual(["grave", "grave", "normal", "normal"]);
        expect(construireAFaire(null, null)).toEqual([]);
    });

    it("le lien d'un motif porte le filtre de motif et la période (jusqu'à 30 jours, la plage du filtre de date)", () => {
        const maintenant = new Date("2026-11-05T12:00:00Z");
        const court = JSON.parse(decodeURIComponent(lienDesAppelsDuMotif("/clients/7", "Dépannage & co", 7, maintenant).split("filters=")[1]));
        expect(court).toEqual([
            { id: "callReason", value: { value: "Dépannage & co" } },
            { id: "dateRange", value: { from: "2026-10-29T12:00:00.000Z", to: "2026-11-05T12:00:00.000Z" } },
        ]);
        const long = JSON.parse(decodeURIComponent(lienDesAppelsDuMotif("/clients/7", "Devis", 90, maintenant).split("filters=")[1]));
        expect(long).toEqual([{ id: "callReason", value: { value: "Devis" } }]);
    });

    it("la mise en forme des chiffres, en français et en anglais", () => {
        expect(valeurAffichee(chiffre("appels", 1390, null), "fr")).toBe("1 390");
        expect(valeurAffichee(chiffre("resolus", 76, null), "fr")).toBe("76 %");
        expect(valeurAffichee(chiffre("resolus", 76, null), "en")).toBe("76%");
        expect(valeurAffichee(chiffre("note", 4.25, null), "fr")).toBe("4,3");
        expect(valeurAffichee(chiffre("duree", 172, null), "fr")).toBe("2 min 52");
        expect(valeurAffichee(chiffre("duree", 45, null), "fr")).toBe("45 s");
        expect(valeurAffichee(chiffre("cout", 0.25, null), "en")).toBe("$0.25");
        expect(valeurAffichee(chiffre("cout", null, null), "fr")).toBe("–");
    });
});
