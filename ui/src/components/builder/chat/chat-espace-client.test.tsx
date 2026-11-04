/**
 * [.mark] U2 quater (lot H2, E57) : le builder et le chat dans l'espace d'un client.
 *
 * Questions de ce fichier :
 *
 *     Les adresses de l'écran suivent l'espace (une conversation s'ouvre au Labo ou chez le client, jamais ailleurs) ?
 *     Les pages « Builder IA » et « Chat » d'un client montent les vrais écrans du builder et non la liste des agents ?
 *     Dans l'espace d'un client, le coût du builder n'est pas un lien vers les réglages du Labo ?
 */
import { existsSync, readFileSync } from "node:fs";
import { join } from "node:path";

import { cleanup, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { adressesDe } from "./adresses";

const m = vi.hoisted(() => ({ chemin: "/clients/7/builder", push: vi.fn(), session: { user: { id: "u" }, loading: false } }));
vi.mock("next/navigation", () => ({ usePathname: () => m.chemin, useRouter: () => ({ push: m.push }), useParams: () => ({}) }));
// Un objet stable : le vrai `useAuth` ne rend pas un nouvel utilisateur à chaque rendu (les effets en dépendent).
vi.mock("@/lib/auth", () => ({ useAuth: () => m.session }));
vi.mock("@/components/mark/studio/nom-espace", () => ({ useNomEspace: (_e: string, org: string | null) => (org === "7" ? "Nuances de Feu" : "Labo") }));
vi.mock("@/client", () => ({
    getWorkflowsSummaryApiV1WorkflowSummaryGet: vi.fn(async () => ({ data: [] })),
    lireLesSourcesApiV1BuilderSourcesGet: vi.fn(async () => ({ data: { sources: { builder: "cle_api" } } })),
    lireLeCerveauApiV1BuilderCerveauGet: vi.fn(async () => ({ data: { modele: "un-modele", plafond_depense: 3 } })),
    lireLesDemarragesApiV1BuilderDemarragesGet: vi.fn(async () => ({ data: [] })),
    listerLesFilsApiV1BuilderFilsGet: vi.fn(async () => ({ data: [{ id: 9, titre: "Un chat", etat: "terminee", changements: 0, cout: 0.1 }] })),
    ouvrirUnFilApiV1BuilderFilsPost: vi.fn(),
    lireLesAmeliorationsApiV1AmeliorationsGet: vi.fn(async () => ({ data: { lignes: [], page: 0, a_une_suite: false, compteurs: {} } })),
}));

afterEach(cleanup);

describe("les adresses du builder suivent l'espace", () => {
    it("chez un client : la conversation s'ouvre dans /clients/<org>/chat, pas de réglages du Labo", () => {
        const a = adressesDe("/clients/7/builder");
        expect(a.client).toBe(true);
        expect(a.org).toBe("7");
        expect(a.fil(9)).toBe("/clients/7/chat/9");
        expect(a.reglages).toBeNull();
    });
    it("au Labo : la conversation s'ouvre dans /labo/builder, les réglages sont ceux du Labo", () => {
        const a = adressesDe("/labo");
        expect(a.client).toBe(false);
        expect(a.fil(9)).toBe("/labo/builder/9");
        expect(a.reglages).toBe("/labo/reglages");
    });
});

describe("les pages du client montent les écrans du builder", () => {
    const app = join(process.cwd(), "src", "app", "clients", "[org]");
    it.each([
        ["builder", "PageAccueil"],
        ["chat", "PageHistorique"],
        [join("chat", "[fil]"), "PageFil"],
    ])("%s", (dossier, ecran) => {
        const fichier = join(app, dossier, "page.tsx");
        expect(existsSync(fichier)).toBe(true);
        expect(readFileSync(fichier, "utf8")).toContain(`@/components/builder/chat/${ecran}`);
    });
});

describe("l'écran dans l'espace d'un client", () => {
    it("l'accueil dit pour qui on construit, et le coût n'y est pas un lien vers le Labo", async () => {
        m.chemin = "/clients/7/builder";
        const { default: PageAccueil } = await import("./PageAccueil");
        render(<PageAccueil />);
        expect(await screen.findByText(/Que construit-on pour Nuances de Feu \?|What do we build for Nuances de Feu \?/)).toBeTruthy();
        const cout = await screen.findByText(/un-modele/);
        expect(cout.closest("a")).toBeNull();
    });
    it("V2b : sans modèle réglé, l'accueil n'affiche aucune ligne de coût (jamais « - · $… par chat »)", async () => {
        m.chemin = "/clients/7/builder";
        const client = await import("@/client");
        vi.mocked(client.lireLeCerveauApiV1BuilderCerveauGet).mockResolvedValueOnce({ data: { modele: "", plafond_depense: 2 } } as never);
        const { default: PageAccueil } = await import("./PageAccueil");
        render(<PageAccueil />);
        await screen.findByText(/Que construit-on pour Nuances de Feu \?|What do we build for Nuances de Feu \?/);
        await new Promise((r) => setTimeout(r, 50));
        expect(screen.queryByText(/par chat|per chat/)).toBeNull();
    });
    it("V2b : avec un modèle réglé, le plafond est écrit dans la langue de l'écran", async () => {
        m.chemin = "/clients/7/builder";
        const { default: PageAccueil } = await import("./PageAccueil");
        render(<PageAccueil />);
        expect((await screen.findByText(/un-modele/)).textContent).toMatch(/un-modele · \$3\.00 per chat/);
    });
    it("V4 : chaque sorte de carte de démarrage a sa couleur (un jeton), jamais la même pour toutes", async () => {
        m.chemin = "/labo/builder";
        const client = await import("@/client");
        const carte = (slug: string, icone: string) => ({ slug, titre: slug, phrase: "p", demande: "d", besoin: "rien", icone, proposee_dans: "labo_et_clients" });
        vi.mocked(client.lireLesDemarragesApiV1BuilderDemarragesGet).mockResolvedValueOnce({
            data: [carte("a", "agent"), carte("b", "amelioration"), carte("c", "test"), carte("d", "fichier"), carte("e", "etincelle")],
        } as never);
        const { default: PageAccueil } = await import("./PageAccueil");
        render(<PageAccueil />);
        const couleurs = await waitFor(() => {
            const icones = [...document.querySelectorAll<HTMLElement>("[data-demarrage] [data-icone]")];
            expect(icones).toHaveLength(5);
            return icones.map((i) => i.style.color);
        });
        expect(couleurs).toEqual(["agent", "amelioration", "test", "fichier", "etincelle"].map((n) => `var(--demarrage-${n})`));
        expect(new Set(couleurs).size).toBe(5);
    });
    it("l'accueil d'un client a sa section « À améliorer » (état « fait » quand rien n'attend) avec le lien de son espace", async () => {
        m.chemin = "/clients/7/builder";
        const { default: PageAccueil } = await import("./PageAccueil");
        render(<PageAccueil />);
        expect(await screen.findByText(/Rien à améliorer|Nothing to improve/)).toBeTruthy();
        const liens = screen.getAllByRole("link", { name: /Tout voir|See all/ }).map((l) => l.getAttribute("href"));
        expect(liens).toContain("/clients/7/a-ameliorer");
    });
    it("le chat d'un client ouvre ses conversations chez lui", async () => {
        m.chemin = "/clients/7/chat";
        const { default: PageHistorique } = await import("./PageHistorique");
        render(<PageHistorique />);
        const lien = await screen.findByText("Un chat");
        expect(lien.closest("a")?.getAttribute("href")).toBe("/clients/7/chat/9");
    });
});
