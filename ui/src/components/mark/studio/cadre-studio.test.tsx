/**
 * [.mark] Le cadre du studio (U1, sous-lot 2) : menus des deux espaces (E3), barre repliable, fil d'Ariane, barre
 * d'actions, pied, compteurs sans fausse valeur, aucune entrée morte (carte de rangement).
 */
import { existsSync } from "node:fs";
import { join } from "node:path";

import { act, cleanup, fireEvent, render, screen, within } from "@testing-library/react";
import { afterEach, beforeAll, describe, expect, it, vi } from "vitest";

import { FournisseurLangue } from "../langue/langue";
import { entreeActive, espaceDe, MENU_CLIENT, MENU_LABO, toutesLesEntrees } from "./navigation-studio";
import { ShellStudio } from "./shell-studio";

let chemin = "/workflow";
let alerteTelephonie = 0;
vi.mock("next/navigation", () => ({ usePathname: () => chemin, useRouter: () => ({ push: vi.fn() }) }));
vi.mock("@/lib/auth", () => ({
    useAuth: () => ({ provider: "local", logout: vi.fn(), user: { email: "evan@exemple.fr" } }),
}));
vi.mock("@/context/TelephonyConfigWarningsContext", () => ({
    useTelephonyConfigWarnings: () => ({
        telnyxMissingWebhookPublicKeyCount: alerteTelephonie,
        vonageMissingSignatureSecretCount: 0,
    }),
}));
vi.mock("@/components/layout/SidebarOrganizationSwitcher", () => ({
    SidebarOrganizationSwitcher: () => <div data-testid="selecteur-organisation" />,
}));
vi.mock("@/components/layout/SidebarTeamSwitcher", () => ({ SidebarTeamSwitcher: () => <div /> }));
vi.mock("@/components/ThemeSwitcher", () => ({ default: () => <button type="button">thème</button> }));

beforeAll(() => {
    window.matchMedia =
        window.matchMedia ||
        ((query: string) =>
            ({ matches: false, media: query, addEventListener: () => {}, removeEventListener: () => {}, addListener: () => {}, removeListener: () => {} }) as unknown as MediaQueryList);
});
afterEach(() => {
    cleanup();
    window.localStorage.clear();
    chemin = "/workflow";
    alerteTelephonie = 0;
});

const monter = (props: Partial<React.ComponentProps<typeof ShellStudio>> = {}) =>
    render(
        <FournisseurLangue>
            <ShellStudio {...props}>
                <p>contenu de la page</p>
            </ShellStudio>
        </FournisseurLangue>,
    );

const titres = (groupes: typeof MENU_LABO) => toutesLesEntrees(groupes).map((x) => x.titre.fr);

describe("menus (E3, E31)", () => {
    it("le Labo : tous les moments du métier, dans l'ordre", () => {
        expect(MENU_LABO.map((g) => g.label?.fr ?? "")).toEqual(["", "CONSTRUIRE", "BRANCHER", "MESURER", "RÉGLER"]);
        for (const attendu of [
            "Builder IA", "Chat", "À améliorer", "Agents", "Bibliothèque", "Outils", "Connaissances", "Entreprise",
            "Campagnes", "Base et automatisations", "Intégrations", "Modèles et clés", "Téléphonie", "Qualité",
            "Conversations", "Réglages",
        ]) {
            expect(titres(MENU_LABO), attendu).toContain(attendu);
        }
    });

    it("le client : le même ensemble, sans l'atelier, avec son accueil", () => {
        expect(MENU_CLIENT.map((g) => g.label?.fr ?? "")).toEqual(["", "AGENTS", "BRANCHER", "ORGANISATION"]);
        expect(titres(MENU_CLIENT)).toEqual(expect.arrayContaining(["Accueil", "Builder IA", "Chat", "À améliorer", "Agents", "Conversations", "Réglages"]));
    });

    it("rien de mort : chaque entrée mène à un écran qui existe aujourd'hui", () => {
        const app = join(process.cwd(), "src", "app");
        for (const entree of [...toutesLesEntrees(MENU_LABO), ...toutesLesEntrees(MENU_CLIENT)]) {
            expect(existsSync(join(app, entree.actuelle, "page.tsx")), `${entree.id} -> ${entree.actuelle}`).toBe(true);
        }
    });

    it("aucune fonction en moins : tous les écrans de l'ancien menu restent atteignables", () => {
        const liens = new Set(toutesLesEntrees(MENU_LABO).map((x) => x.actuelle));
        for (const ancien of [
            "/workflow", "/campaigns", "/model-configurations", "/telephony-configurations", "/tools", "/files",
            "/recordings", "/api-keys", "/usage", "/reports", "/cles", "/bibliotheque", "/a-trier", "/alertes", "/settings",
        ]) {
            expect(liens.has(ancien), ancien).toBe(true);
        }
    });

    it("l'espace se lit dans l'adresse", () => {
        expect(espaceDe("/workflow")).toEqual({ espace: "labo", base: "/labo", org: null });
        expect(espaceDe("/clients/acme/agents")).toEqual({ espace: "client", base: "/clients/acme", org: "acme" });
    });

    it("l'entrée surlignée suit l'adresse ; un alias ne prend pas la place du propriétaire", () => {
        expect(entreeActive(MENU_LABO, "/workflow/12/runs", "/labo")?.id).toBe("agents");
        expect(entreeActive(MENU_LABO, "/settings", "/labo")?.id).toBe("reglages");
        expect(entreeActive(MENU_LABO, "/a-trier", "/labo")?.id).toBe("a-ameliorer");
        expect(entreeActive(MENU_LABO, "/labo", "/labo")?.id).toBe("builder");
        expect(entreeActive(MENU_CLIENT, "/clients/acme", "/clients/acme")?.id).toBe("accueil");
        expect(entreeActive(MENU_LABO, "/inconnu", "/labo")).toBeNull();
    });
});

describe("barre latérale", () => {
    it("montre le menu du Labo hors d'un client, en français par défaut, avec l'écran actuel pour lien", () => {
        monter();
        expect(screen.getByRole("link", { name: "Agents" }).getAttribute("href")).toBe("/workflow");
        expect(screen.getByRole("link", { name: "Conversations" }).getAttribute("href")).toBe("/usage");
        expect(screen.getByRole("link", { name: "Qualité" }).getAttribute("href")).toBe("/reports");
        expect(screen.getByRole("link", { name: "Agents" }).getAttribute("data-active")).toBe("true");
        expect(document.querySelector("[data-espace='labo']")).not.toBeNull();
    });

    it("montre le menu du client dans /clients/<org>", () => {
        chemin = "/clients/acme/agents";
        monter();
        expect(screen.getByRole("link", { name: "Accueil" })).toBeTruthy();
        expect(document.querySelector("[data-espace='client']")).not.toBeNull();
    });

    it("aucun champ de recherche (E60)", () => {
        monter();
        expect(screen.queryByRole("searchbox")).toBeNull();
        expect(screen.queryByPlaceholderText(/rechercher|search/i)).toBeNull();
    });

    it("le sélecteur d'espace s'appuie sur le sélecteur d'organisation actuel", () => {
        monter();
        expect(screen.getByTestId("selecteur-organisation")).toBeTruthy();
    });

    it("compteurs : l'emplacement existe, aucune fausse valeur tant qu'on n'en donne pas", () => {
        const { unmount } = monter();
        expect(document.querySelectorAll("[data-slot='sidebar-menu-button'] .tabular-nums, [data-urgente]")).toHaveLength(0);
        unmount();
        monter({ compteurs: { "a-ameliorer": { n: 4, urgent: true } } });
        const lien = screen.getByRole("link", { name: /À améliorer/ });
        expect(within(lien).getByText("4")).toBeTruthy();
        expect(lien.querySelector("[data-urgente]")).not.toBeNull();
    });

    it("le point d'alerte de la téléphonie reste sur l'entrée", () => {
        alerteTelephonie = 1;
        monter();
        const lien = screen.getByRole("link", { name: /Téléphonie/ });
        expect(lien.querySelector("svg[aria-label]")).not.toBeNull();
    });

    it("le pied : personne, langue, thème", () => {
        monter();
        expect(screen.getByText("evan@exemple.fr")).toBeTruthy();
        expect(screen.getByRole("group", { name: "Langue" })).toBeTruthy();
        expect(screen.getByText("thème")).toBeTruthy();
    });
});

describe("cadre", () => {
    it("fil d'Ariane déduit de l'adresse : espace puis entrée du menu", () => {
        monter();
        const fil = screen.getByRole("navigation", { name: "Fil d'Ariane" });
        expect(within(fil).getByText("Labo .mark")).toBeTruthy();
        expect(within(fil).getByText("Agents")).toBeTruthy();
    });

    it("fil d'Ariane et barre d'actions fournis par la page", () => {
        monter({ miettes: [{ libelle: "Acme", href: "/clients/acme" }, { libelle: "Standard" }], actions: <button type="button">Publier</button> });
        const fil = screen.getByRole("navigation", { name: "Fil d'Ariane" });
        expect(within(fil).getByRole("link", { name: "Acme" }).getAttribute("href")).toBe("/clients/acme");
        expect(within(fil).getByText("Standard")).toBeTruthy();
        expect(document.querySelector("[data-barre-actions]")?.textContent).toContain("Publier");
    });

    it("une page qui porte sa propre barre (l'éditeur) n'a pas l'en-tête du cadre", () => {
        monter({ sansEntete: true });
        expect(screen.queryByRole("navigation", { name: "Fil d'Ariane" })).toBeNull();
        expect(screen.getByText("contenu de la page")).toBeTruthy();
    });

    it("la barre se replie en icônes, le choix survit à une page, et l'éditeur la replie sans le changer", () => {
        const { unmount } = monter();
        const barre = () => document.querySelector("[data-slot='sidebar']") as HTMLElement;
        expect(barre().getAttribute("data-state")).toBe("expanded");
        fireEvent.click(screen.getAllByRole("button", { name: /sidebar|barre|toggle/i })[0]);
        expect(barre().getAttribute("data-state")).toBe("collapsed");
        expect(barre().getAttribute("data-collapsible")).toBe("icon");
        unmount();
        // Autre page : le choix de la personne (repliée) est gardé.
        monter();
        expect(barre().getAttribute("data-state")).toBe("collapsed");
    });

    it("replie=true force les icônes sans effacer le choix", () => {
        const { rerender } = monter({ replie: true });
        const barre = () => document.querySelector("[data-slot='sidebar']") as HTMLElement;
        expect(barre().getAttribute("data-state")).toBe("collapsed");
        act(() => {
            rerender(
                <FournisseurLangue>
                    <ShellStudio replie={false}>
                        <p>x</p>
                    </ShellStudio>
                </FournisseurLangue>,
            );
        });
        expect(barre().getAttribute("data-state")).toBe("expanded");
    });
});
