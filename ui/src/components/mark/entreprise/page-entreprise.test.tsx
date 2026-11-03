/**
 * [.mark] U2 bis (E56) et U2 (E52), l'écran Entreprise, l'écran Base et automatisations et les réglages réduits (D8).
 *
 *   - Entreprise : six sous-onglets, chacun porte son thème, rien n'est perdu en changeant d'onglet ;
 *   - chaque fiche dit qui l'a modifiée en dernier et d'où (portail ou Dograh), lu dans le journal ;
 *   - Base et automatisations : la base et l'après-appel ;
 *   - les dix thèmes d'avant ont CHACUN une place : aucune fonction en moins ;
 *   - « Réglages de l'organisation » ne garde que trois thèmes, les anciennes ancres mènent à la nouvelle place ;
 *   - Écoute et sons : les enregistrements et le cache de la voix sont montés, l'envoi s'ouvre.
 */
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import type { ReactNode } from "react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { FournisseurLangue } from "../langue/langue";

const m = vi.hoisted(() => ({ modifications: vi.fn(), etablissements: vi.fn() }));

vi.mock("@/client/sdk.gen", async (importOriginal) => (await import("../sdk-factice")).sdkFactice(await importOriginal(), {
    getEtablissementsApiV1OrganizationsEtablissementsGet: m.etablissements,
    getDernieresModificationsApiV1OrganizationsEtablissementsDernieresModificationsGet: m.modifications,
    getNumerosApiV1OrganizationsEtablissementsNumerosGet: () => Promise.resolve({ data: [] }),
    getBaseClientApiV1OrganizationsBaseClientGet: () =>
        Promise.resolve({ data: { serveur_configure: true, version_attendue: 3, nom_base: null, joignable: false, refus: [], conservation: [] } }),
}));
vi.mock("sonner", () => ({ toast: { success: vi.fn(), error: vi.fn() } }));
// La fenêtre de « Toute l'entreprise » pose une liste du design system (Radix) : jsdom n'a ni observateur de taille ni capture de pointeur.
vi.stubGlobal("ResizeObserver", class { observe() {} unobserve() {} disconnect() {} });
Element.prototype.hasPointerCapture = vi.fn(() => false);
Element.prototype.scrollIntoView = vi.fn();
vi.mock("@/lib/auth", () => ({ useAuth: () => ({ user: { id: 1 }, loading: false }) }));
vi.mock("@/context/UserConfigContext", () => ({ useUserConfig: () => ({ refreshConfig: () => Promise.resolve() }) }));
vi.mock("react-timezone-select", () => ({ default: () => null }));
vi.mock("@/components/DispositionMappingDialog", () => ({ DispositionMappingDialog: () => null }));
vi.mock("@/components/MCPSection", () => ({ MCPSection: () => null }));
vi.mock("@/components/TelemetrySection", () => ({ TelemetrySection: () => null }));
vi.mock("@/app/recordings/RecordingsList", () => ({ default: () => <div data-testid="liste-enregistrements" /> }));
vi.mock("@/app/recordings/TtsCacheList", () => ({ default: () => <div data-testid="cache-voix" /> }));
vi.mock("@/app/recordings/RecordingsUploadDialog", () => ({
    RecordingsUploadDialog: ({ open }: { open: boolean }) => (open ? <div data-testid="fenetre-envoi" /> : null),
}));
vi.stubGlobal("ResizeObserver", class { observe() {} unobserve() {} disconnect() {} });

const { PageEntreprise, ONGLETS_ENTREPRISE } = await import("./PageEntreprise");
const { PageBase } = await import("./PageBase");
const { PageParametresOrganisation, THEMES_RESTANTS } = await import("../parametres-organisation/PageParametresOrganisation");
const { THEMES_ORGANISATION } = await import("../parametres-organisation/ThemesOrganisation");
const { destinationDeLAncre } = await import("./anciennes-ancres");
const { SonsEtCacheVoix } = await import("./SonsEtCacheVoix");

const FICHES = {
    format: "etablissements-mark",
    version: 1,
    etablissements: [
        { id: "nord", nom: "Nord", horaires_ouverture: "lun-ven 9h-18h" },
        { id: "sud", nom: "Sud" },
        { id: "est", nom: "Est" },
    ],
};

const reinitialiser = () => {
    m.etablissements.mockReset().mockImplementation(() => Promise.resolve({ data: structuredClone(FICHES) }));
    m.modifications.mockReset().mockImplementation(() =>
        Promise.resolve({
            data: [
                { id: "nord", origine: "portail", auteur: "Camille Dupont", le: "2026-11-02T10:00:00Z" },
                { id: "sud", origine: "dograh", auteur: null, le: "2026-11-01T09:00:00Z" },
            ],
        }),
    );
};
reinitialiser();
afterEach(() => {
    cleanup();
    reinitialiser();
    window.history.replaceState(null, "", "/");
});

const rendre = (noeud: ReactNode) => render(<FournisseurLangue>{noeud}</FournisseurLangue>);
const onglet = (id: string) => document.querySelector(`[data-onglet="${id}"]`) as HTMLElement;
const volet = (id: string) => document.getElementById(`volet-${id}`) as HTMLElement;

describe("[.mark] l'écran Entreprise (U2 bis, E56)", () => {
    it("a six sous-onglets, dans l'ordre de la décision, et ouvre sur Établissements", () => {
        rendre(<PageEntreprise />);
        expect([...document.querySelectorAll("[role='tab']")].map((o) => o.getAttribute("data-onglet"))).toEqual([...ONGLETS_ENTREPRISE]);
        expect([...document.querySelectorAll("[role='tab']")].map((o) => o.textContent?.replace(/\s+/g, " ").trim())).toEqual([
            "Établissements",
            "Équipe et routage",
            "Rendez-vous",
            "Variables",
            "Vérification de l'appelant",
            "Écoute et sons",
        ]);
        expect(onglet("etablissements").getAttribute("aria-selected")).toBe("true");
        expect(volet("etablissements").hidden).toBe(false);
        expect(volet("equipe").hidden).toBe(true);
    });

    it("chaque sous-onglet a la forme de la maquette : lignes + tableaux, ou le thème à plat (jamais carte ni repli)", () => {
        rendre(<PageEntreprise />);
        // K4 : Établissements = « Toute l'entreprise » en lignes (+ Modifier) ; Équipe et Rendez-vous = tableaux (ou la
        // phrase « base à rattacher ») ; Variables = tableau ; Vérification et Écoute restent des thèmes à plat.
        const attendus: Record<string, string> = {
            etablissements: '[data-theme="etablissement"][data-lignes]',
            equipe: "*",
            "rendez-vous": "*",
            objets: "#etablissement-objets",
            verification: '[data-theme="verification"][data-plat]',
            ecoute: '[data-theme="ecoute"][data-plat]',
        };
        for (const [id, marque] of Object.entries(attendus)) {
            fireEvent.click(onglet(id));
            expect(volet(id).querySelector(marque), id).not.toBeNull();
            expect(volet(id).hidden, id).toBe(false);
            // « Modifier » (lignes) ouvre une fenêtre : seul un thème REPLIABLE a un bouton qui déplie en place.
            expect(volet(id).querySelector("button[aria-expanded]:not([aria-haspopup])"), `${id} ne se replie pas`).toBeNull();
        }
    });

    it("l'onglet se lit dans l'adresse et s'y réécrit", async () => {
        window.history.replaceState(null, "", "/labo/entreprise?onglet=verification");
        rendre(<PageEntreprise />);
        await waitFor(() => expect(onglet("verification").getAttribute("aria-selected")).toBe("true"));
        fireEvent.click(onglet("rendez-vous"));
        expect(window.location.search).toBe("?onglet=rendez-vous");
        expect(volet("rendez-vous").hidden).toBe(false);
    });

    it("un onglet inconnu retombe sur le premier", async () => {
        window.history.replaceState(null, "", "/labo/entreprise?onglet=nimportequoi");
        rendre(<PageEntreprise />);
        await waitFor(() => expect(volet("etablissements").hidden).toBe(false));
    });

    it("changer d'onglet ne perd pas ce qui est tapé, et l'onglet montre la pastille", async () => {
        rendre(<PageEntreprise />);
        // L'annonce se tape dans la fenêtre de « Toute l'entreprise » : « Modifier » l'ouvre.
        fireEvent.click(await waitFor(() => {
            const b = document.querySelector('[data-theme="etablissement"] button[aria-haspopup="dialog"]');
            if (!b) throw new Error("bouton Modifier pas encore dessiné");
            return b as HTMLElement;
        }));
        const champ = await waitFor(() => {
            const c = document.getElementById("annonce_fermeture");
            if (!c) throw new Error("annonce pas encore dessinée");
            return c as HTMLTextAreaElement;
        });
        fireEvent.change(champ, { target: { value: "Fermé pour travaux" } });
        await waitFor(() => expect(onglet("etablissements").querySelector('[data-pastille="modifie"]')).not.toBeNull());
        fireEvent.click(onglet("equipe"));
        fireEvent.click(onglet("etablissements"));
        expect((document.getElementById("annonce_fermeture") as HTMLTextAreaElement).value).toBe("Fermé pour travaux");
    });

    it("chaque fiche dit qui l'a modifiée en dernier et d'où", async () => {
        rendre(<PageEntreprise />);
        const nord = await waitFor(() => {
            const n = document.querySelector('[data-derniere-modification="nord"]');
            if (!n) throw new Error("pas encore lue");
            return n;
        });
        expect(nord.textContent).toContain("Modifiée en dernier par Camille Dupont depuis le portail");
        expect(nord.textContent).toContain("02/11/2026");
        const sud = document.querySelector('[data-derniere-modification="sud"]')!;
        expect(sud.textContent).toContain("depuis Dograh");
        expect(sud.textContent).not.toContain(" par ");
        // Une fiche que le journal ne connaît pas n'affiche rien (jamais inventé).
        expect(document.querySelector('[data-derniere-modification="est"]')).toBeNull();
    });

    it("les objets ne sont plus dans le thème Établissements : ils ont leur sous-onglet", () => {
        rendre(<PageEntreprise />);
        expect(volet("etablissements").querySelector("#etablissement-objets")).toBeNull();
        expect(volet("objets").querySelector("#etablissement-objets")).not.toBeNull();
    });
});

describe("[.mark] l'écran Base et automatisations (U2, E52)", () => {
    it("est UNE page (sans sous-onglets, comme la maquette) : deux intertitres, la base du client et l'après-appel, posés à plat", () => {
        rendre(<PageBase />);
        expect(document.querySelectorAll("[role='tab']").length).toBe(0);
        expect(document.querySelector('#base [data-theme="donnees"][data-plat]')).not.toBeNull();
        expect(document.querySelector('#apres-appel [data-theme="apres-appel"][data-plat]')).not.toBeNull();
        // L'intertitre porte le titre : le thème n'en répète pas un visible.
        expect(document.querySelector('#base h2.text-base')).toBeNull();
    });
});

describe("[.mark] aucune fonction en moins (D8)", () => {
    it("chacun des dix thèmes d'avant a une place, et une seule", () => {
        const places: Record<string, string> = {
            organisation: "reglages",
            etablissement: "entreprise",
            equipe: "entreprise",
            "rendez-vous": "entreprise",
            verification: "entreprise",
            ecoute: "entreprise",
            donnees: "base",
            "apres-appel": "base",
            integrations: "reglages",
            developpeurs: "reglages",
        };
        expect(THEMES_ORGANISATION.map((t) => t.id).sort()).toEqual(Object.keys(places).sort());
        expect(Object.entries(places).filter(([, p]) => p === "reglages").map(([id]) => id).sort()).toEqual([...THEMES_RESTANTS].sort());
    });

    it("« Réglages de l'organisation » ne montre que Général, Intégrations, Développeurs", () => {
        rendre(<PageParametresOrganisation />);
        expect([...document.querySelectorAll("[data-theme]")].map((s) => s.getAttribute("data-theme"))).toEqual([
            "organisation",
            "integrations",
            "developpeurs",
        ]);
        expect([...document.querySelectorAll("nav [data-navigation]")].map((a) => a.getAttribute("data-navigation"))).toEqual([
            "organisation",
            "integrations",
            "developpeurs",
        ]);
    });

    it("les anciennes ancres mènent à la nouvelle place, dans l'espace d'où l'on vient", () => {
        expect(destinationDeLAncre("etablissement", "/labo")).toBe("/labo/entreprise?onglet=etablissements");
        expect(destinationDeLAncre("etablissement-annonce", "/clients/acme")).toBe("/clients/acme/entreprise?onglet=etablissements");
        expect(destinationDeLAncre("equipe", "/labo")).toBe("/labo/entreprise?onglet=equipe");
        expect(destinationDeLAncre("rendez-vous", "/labo")).toBe("/labo/entreprise?onglet=rendez-vous");
        expect(destinationDeLAncre("verification", "/labo")).toBe("/labo/entreprise?onglet=verification");
        expect(destinationDeLAncre("ecoute", "/labo")).toBe("/labo/entreprise?onglet=ecoute");
        expect(destinationDeLAncre("donnees", "/labo")).toBe("/labo/base#base");
        expect(destinationDeLAncre("apres-appel", "/labo")).toBe("/labo/base#apres-appel");
        for (const reste of ["organisation", "integrations", "developpeurs", ""]) expect(destinationDeLAncre(reste, "/labo"), reste).toBeNull();
    });
});

describe("[.mark] Écoute et sons (E56)", () => {
    it("monte les enregistrements et le cache de la voix, et ouvre l'envoi", () => {
        rendre(<SonsEtCacheVoix />);
        expect(screen.getByTestId("liste-enregistrements")).toBeTruthy();
        expect(screen.getByTestId("cache-voix")).toBeTruthy();
        expect(screen.queryByTestId("fenetre-envoi")).toBeNull();
        fireEvent.click(screen.getByTestId("envoyer-enregistrement"));
        expect(screen.getByTestId("fenetre-envoi")).toBeTruthy();
    });

    it("est dans le sous-onglet Écoute et sons, sous le lexique métier", () => {
        rendre(<PageEntreprise />);
        fireEvent.click(onglet("ecoute"));
        expect(volet("ecoute").querySelector("#ecoute-lexique")).not.toBeNull();
        expect(volet("ecoute").querySelector("#ecoute-enregistrements")).not.toBeNull();
        expect(volet("ecoute").querySelector("#ecoute-cache-voix")).not.toBeNull();
    });
});
