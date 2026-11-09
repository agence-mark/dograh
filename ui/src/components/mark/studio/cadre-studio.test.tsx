/**
 * [.mark] Le cadre du studio (U1, sous-lot 2) : menus des deux espaces (E3), barre repliable, fil d'Ariane, barre
 * d'actions, pied, compteurs sans fausse valeur, aucune entrée morte (carte de rangement).
 */
import { existsSync } from "node:fs";
import { join } from "node:path";

import { act, cleanup, fireEvent, render, screen, within } from "@testing-library/react";
import { afterEach, beforeAll, describe, expect, it, vi } from "vitest";

import { REDIRECTIONS } from "@/lib/redirections";
import { FournisseurLangue } from "../langue/langue";
import { entreeActive, espaceDe, MENU_CLIENT, MENU_LABO, MENU_RELATION, toutesLesEntrees } from "./navigation-studio";
import { EnteteStudio, ShellStudio } from "./shell-studio";

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
vi.mock("./selecteur-espace", () => ({
    SelecteurEspace: ({ espace }: { espace: string }) => <div data-espace={espace} data-testid="selecteur-espace" />,
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

    it("Clés, Alertes et Relation clients ne sont plus des entrées du Labo ni du client (K1b)", () => {
        for (const menu of [MENU_LABO, MENU_CLIENT]) {
            const ids = toutesLesEntrees(menu).map((x) => x.id);
            for (const parti of ["cles", "alertes", "relation-accueil", "relation-messages"]) expect(ids, parti).not.toContain(parti);
        }
        expect(MENU_LABO.some((g) => g.id === "relation")).toBe(false);
    });

    it("la Relation clients est un espace à part, avec son menu (comme la maquette)", () => {
        expect(MENU_RELATION.map((g) => g.label?.fr ?? "")).toEqual(["", "CLIENTS"]);
        expect(titres(MENU_RELATION)).toEqual(["Accueil", "Messages", "Clients", "Avis et témoignages", "Entrées dans les portails"]);
    });

    it("le client : le même ensemble, sans l'atelier, avec son accueil", () => {
        expect(MENU_CLIENT.map((g) => g.label?.fr ?? "")).toEqual(["", "AGENTS", "BRANCHER", "ORGANISATION"]);
        expect(titres(MENU_CLIENT)).toEqual(expect.arrayContaining(["Accueil", "Builder IA", "Chat", "À améliorer", "Agents", "Conversations", "Réglages"]));
    });

    it("rien de mort : chaque entrée mène à un écran qui existe aujourd'hui", () => {
        const app = join(process.cwd(), "src", "app");
        for (const entree of [...toutesLesEntrees(MENU_LABO), ...toutesLesEntrees(MENU_CLIENT)]) {
            // Une ancienne adresse retirée (« À trier », l'ancienne page des outils) mène à sa place par une redirection : elle ne meurt pas.
            const redirigee = REDIRECTIONS.some((r) => r.source === entree.actuelle);
            expect(existsSync(join(app, entree.actuelle, "page.tsx")) || redirigee, `${entree.id} -> ${entree.actuelle}`).toBe(true);
        }
    });

    it("aucune fonction en moins : tous les écrans de l'ancien menu restent atteignables", () => {
        // « /cles » et « /alertes » ne sont plus des entrées : ce sont des onglets, atteints par redirection (K1b).
        const liens = new Set(toutesLesEntrees(MENU_LABO).map((x) => x.actuelle));
        for (const ancien of [
            "/workflow", "/campaigns", "/model-configurations", "/telephony-configurations", "/tools", "/files",
            "/usage", "/reports", "/bibliotheque", "/a-trier", "/settings",
        ]) {
            expect(liens.has(ancien), ancien).toBe(true);
        }
    });

    it("les enregistrements et le cache de la voix ne sont plus une entrée du menu : ils sont dans Entreprise (E56)", () => {
        const ids = new Set(toutesLesEntrees(MENU_LABO).map((x) => x.id));
        expect(ids.has("sons")).toBe(false);
        expect(ids.has("entreprise")).toBe(true);
        expect(toutesLesEntrees(MENU_CLIENT).some((x) => x.id === "sons")).toBe(false);
    });

    it("l'espace se lit dans l'adresse", () => {
        expect(espaceDe("/workflow")).toEqual({ espace: "labo", base: "/labo", org: null });
        expect(espaceDe("/clients/acme/agents")).toEqual({ espace: "client", base: "/clients/acme", org: "acme" });
        expect(espaceDe("/relation")).toEqual({ espace: "relation", base: "/relation", org: null });
        expect(espaceDe("/relation/clients/7")).toEqual({ espace: "relation", base: "/relation", org: null });
        expect(entreeActive(MENU_RELATION, "/relation/clients/7", "/relation")?.id).toBe("relation-clients");
        expect(entreeActive(MENU_RELATION, "/relation", "/relation")?.id).toBe("relation-accueil");
    });

    it("l'entrée surlignée suit l'adresse ; un alias ne prend pas la place du propriétaire", () => {
        expect(entreeActive(MENU_LABO, "/workflow/12/runs", "/labo")?.id).toBe("agents");
        expect(entreeActive(MENU_LABO, "/settings", "/labo")?.id).toBe("reglages");
        expect(entreeActive(MENU_LABO, "/a-trier", "/labo")?.id).toBe("a-ameliorer");
        expect(entreeActive(MENU_LABO, "/labo", "/labo")?.id).toBe("builder");
        expect(entreeActive(MENU_CLIENT, "/clients/acme", "/clients/acme")?.id).toBe("accueil");
        expect(entreeActive(MENU_LABO, "/labo/agents", "/labo")?.id).toBe("agents");
        expect(entreeActive(MENU_LABO, "/agents/12", "/labo")?.id).toBe("agents");
        expect(entreeActive(MENU_LABO, "/conversations/5", "/labo")?.id).toBe("conversations");
        expect(entreeActive(MENU_CLIENT, "/clients/acme/campagnes/new", "/clients/acme")?.id).toBe("campagnes");
        expect(entreeActive(MENU_LABO, "/inconnu", "/labo")).toBeNull();
    });
});

describe("barre latérale", () => {
    it("montre le menu du Labo hors d'un client, en français par défaut, avec les nouvelles adresses pour liens", () => {
        monter();
        expect(screen.getByRole("link", { name: "Agents" }).getAttribute("href")).toBe("/labo/agents");
        expect(screen.getByRole("link", { name: "Conversations" }).getAttribute("href")).toBe("/labo/conversations");
        expect(screen.getByRole("link", { name: "Qualité" }).getAttribute("href")).toBe("/labo/qualite");
        expect(screen.getByRole("link", { name: "Agents" }).getAttribute("data-active")).toBe("true");
        expect(document.querySelector("[data-espace='labo']")).not.toBeNull();
    });

    it("montre le menu de la Relation clients dans /relation, sans fil d'Ariane doublé sur l'accueil", () => {
        chemin = "/relation";
        monter();
        expect(screen.getByRole("link", { name: "Messages" }).getAttribute("href")).toBe("/relation/messages");
        expect(screen.getByRole("link", { name: "Entrées dans les portails" }).getAttribute("href")).toBe("/relation/entrees");
        expect(screen.queryByRole("link", { name: "Agents" })).toBeNull();
        expect(document.querySelector("[data-espace='relation']")).not.toBeNull();
        const fil = screen.getByRole("navigation", { name: "Fil d'Ariane" });
        expect(within(fil).getByText("Relation clients")).toBeTruthy();
        expect(within(fil).queryByText("Accueil")).toBeNull();
    });

    it("montre le menu du client dans /clients/<org>", () => {
        chemin = "/clients/acme/agents";
        monter();
        expect(screen.getByRole("link", { name: "Accueil" }).getAttribute("href")).toBe("/clients/acme");
        expect(screen.getByRole("link", { name: "Agents" }).getAttribute("href")).toBe("/clients/acme/agents");
        expect(document.querySelector("[data-espace='client']")).not.toBeNull();
    });

    it("« Ouvrir son portail » est au bas de la barre d'un client, pas du Labo (É15)", () => {
        chemin = "/clients/7/agents";
        monter();
        expect(screen.getByRole("button", { name: "Ouvrir son portail" })).toBeTruthy();
        cleanup();
        chemin = "/labo/agents";
        monter();
        expect(screen.queryByRole("button", { name: "Ouvrir son portail" })).toBeNull();
    });

    it("aucun champ de recherche (E60)", () => {
        monter();
        expect(screen.queryByRole("searchbox")).toBeNull();
        expect(screen.queryByPlaceholderText(/rechercher|search/i)).toBeNull();
    });

    it("le sélecteur d'espace (U2) tient la place du sélecteur d'organisation", () => {
        monter();
        expect(screen.getByTestId("selecteur-espace")).toBeTruthy();
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

    it("le pied : la personne seule, ni langue ni thème (ils sont dans Réglages › Affichage, K1)", () => {
        monter();
        expect(screen.getByText("evan@exemple.fr")).toBeTruthy();
        expect(screen.queryByRole("group", { name: "Langue" })).toBeNull();
        expect(screen.queryByText("thème")).toBeNull();
    });
});

describe("cadre", () => {
    it("fil d'Ariane déduit de l'adresse : espace puis entrée du menu", () => {
        monter();
        const fil = screen.getByRole("navigation", { name: "Fil d'Ariane" });
        expect(within(fil).getByText("Labo")).toBeTruthy();
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

describe("emplacement d'actions et fil d'Ariane posés par la page (K7)", () => {
    const AvecEntete = ({ afficher }: { afficher: boolean }) => (
        <FournisseurLangue>
            <ShellStudio>
                <p>contenu de la page</p>
                {afficher && <EnteteStudio miettes={[{ libelle: "Labo", href: "/labo" }, { libelle: "Chat", href: "/labo/builder" }, { libelle: "Titre du chat" }]} actions={<button type="button">Arrêter le chat</button>} />}
            </ShellStudio>
        </FournisseurLangue>
    );

    it("la page pose son fil d'Ariane (titre en dernier maillon) et ses actions à droite, sans masquer le fil", async () => {
        chemin = "/labo/builder/4";
        render(<AvecEntete afficher />);
        const fil = await screen.findByRole("navigation", { name: /Fil d'Ariane|Breadcrumb/ });
        expect(within(fil).getByText("Titre du chat")).toBeTruthy();
        expect(within(fil).getByText("Chat").closest("a")?.getAttribute("href")).toBe("/labo/builder");
        expect(fil.hasAttribute("hidden")).toBe(false);
        const barre = document.querySelector("[data-barre-actions]") as HTMLElement;
        expect(within(barre).getByText("Arrêter le chat")).toBeTruthy();
    });

    it("sans la page, le fil du cadre revient", async () => {
        chemin = "/labo/builder/4";
        const { rerender } = render(<AvecEntete afficher />);
        await screen.findByText("Titre du chat");
        rerender(<AvecEntete afficher={false} />);
        expect(screen.queryByText("Titre du chat")).toBeNull();
        expect(screen.queryByText("Arrêter le chat")).toBeNull();
    });
});
