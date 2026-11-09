/**
 * [.mark] Partie 3, N4 (décision 19) : la page « Builder IA » premium.
 *
 * Questions de ce fichier :
 *
 *     La barre de la saisie porte Joindre, @, /, le mode du chat et le modèle en pastille ?
 *     Le mode choisi part avec l'ouverture du chat (posé avant le premier tour) et « demander » n'envoie rien ?
 *     Le « / » ouvre le menu des commandes SOUS la saisie ?
 *     « Reprendre » montre les derniers chats en cartes, « Mise en route » une barre reliée à « Prêt à publier » ?
 *     L'avertissement MCP est une ligne douce, la gravité une pastille pâle (seule « Grave » est pleine) ?
 */
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

const m = vi.hoisted(() => ({
    push: vi.fn(),
    session: { user: { id: "u" }, loading: false },
    source: "cle_api" as string,
    agents: [] as { id: number; name: string }[],
    etapes: [] as { id: string; etat: string; niveau: string }[],
    prenom: null as string | null,
}));
vi.mock("next/navigation", () => ({ usePathname: () => "/labo", useRouter: () => ({ push: m.push }), useParams: () => ({}) }));
vi.mock("@/lib/auth", () => ({ useAuth: () => m.session }));
vi.mock("@/client", () => ({
    getWorkflowsSummaryApiV1WorkflowSummaryGet: vi.fn(async () => ({ data: m.agents })),
    lireLesSourcesApiV1BuilderSourcesGet: vi.fn(async () => ({ data: { sources: { builder: m.source } } })),
    lireLeCerveauApiV1BuilderCerveauGet: vi.fn(async () => ({ data: { modele: "un-modele", plafond_depense: 3 } })),
    lireLesDemarragesApiV1BuilderDemarragesGet: vi.fn(async () => ({ data: [] })),
    listerLesFilsApiV1BuilderFilsGet: vi.fn(async () => ({
        data: [
            { id: 9, titre: "Corriger l'accueil", etat: "terminee", changements: 2, cout: 0.1, workflow_id: 5, genre: "claude_code", auteur: "Evan", modifie_le: null },
            { id: 8, titre: "Relire le numéro", etat: "terminee", changements: 0, cout: 0.1, workflow_id: null, genre: "builder", modifie_le: null },
            { id: 7, titre: "Troisième", etat: "terminee", changements: 0, cout: 0.1, workflow_id: null, genre: "builder", modifie_le: null },
            { id: 6, titre: "Quatrième, hors des trois derniers", etat: "terminee", changements: 0, cout: 0.1, workflow_id: null, genre: "builder", modifie_le: null },
        ],
    })),
    listerLesRecettesApiV1BuilderRecettesGet: vi.fn(async () => ({ data: { recettes: [] } })),
    ouvrirUnFilApiV1BuilderFilsPost: vi.fn(async () => ({ data: { id: 41 } })),
    lireLesAmeliorationsApiV1AmeliorationsGet: vi.fn(async () => ({ data: { lignes: [], page: 0, a_une_suite: false, compteurs: {} } })),
    lireLaPreparationApiV1WorkflowWorkflowIdPreparationGet: vi.fn(async () => ({ data: { etapes: m.etapes } })),
}));

vi.mock("@/client/sdk.gen", async (importOriginal) => ({
    ...(await importOriginal<Record<string, unknown>>()),
    lireLaPreparationApiV1WorkflowWorkflowIdPreparationGet: vi.fn(async () => ({ data: { etapes: m.etapes } })),
    monProfilApiV1EquipeMarkMoiGet: vi.fn(async () => ({ data: { prenom: m.prenom } })),
}));

import * as client from "@/client";
import { Gravite } from "@/components/mark/studio/marques";
import { AvertissementClaudeCode } from "@/components/mark/sources/marques";

vi.stubGlobal("ResizeObserver", class { observe() {} unobserve() {} disconnect() {} });

afterEach(() => {
    cleanup();
    m.agents = [];
    m.etapes = [];
    m.source = "cle_api";
    m.prenom = null;
    m.push.mockClear();
    vi.mocked(client.ouvrirUnFilApiV1BuilderFilsPost).mockClear();
});

async function accueil() {
    const { default: PageAccueil } = await import("./PageAccueil");
    render(<PageAccueil />);
    await screen.findByText(/un-modele/);
}

describe("la salutation (É2, clôture D2)", () => {
    it("dit « Hello Evan, » (« Bonjour Evan, » en français) quand le compte a un prénom, rien de plus sinon", async () => {
        m.prenom = "Evan";
        await accueil();
        expect((await screen.findByRole("heading", { level: 1 })).textContent).toBe("Hello Evan, what do we build?");
        cleanup();
        m.prenom = null;
        await accueil();
        expect((await screen.findByRole("heading", { level: 1 })).textContent).toBe("Hello, what do we build?");
    });
});

describe("la barre de la saisie", () => {
    it("porte Joindre, @, /, le mode du chat et le modèle en pastille", async () => {
        await accueil();
        expect(screen.getByRole("button", { name: /Joindre|Attach/ })).toBeTruthy();
        expect(screen.getByRole("button", { name: /Citer un agent|Quote an agent/ })).toBeTruthy();
        expect(screen.getByRole("button", { name: /Commandes|Commands/ })).toBeTruthy();
        expect(document.querySelector("[data-selecteur-mode='demander']")).not.toBeNull();
        expect(screen.getByText("un-modele").className).toMatch(/rounded-full/);
    });

    it("le bouton « / » écrit le signe et ouvre le menu des commandes SOUS la saisie", async () => {
        await accueil();
        fireEvent.click(screen.getByRole("button", { name: /Commandes|Commands/ }));
        const menu = await waitFor(() => {
            const el = document.querySelector<HTMLElement>("[data-menu-saisie='/']");
            expect(el).not.toBeNull();
            return el as HTMLElement;
        });
        expect(menu.className).toMatch(/top-full/);
        expect(menu.className).not.toMatch(/bottom-full/);
        expect((screen.getByRole("textbox") as HTMLTextAreaElement).value).toBe("/");
    });
});

describe("le mode part avec l'ouverture du chat", () => {
    const ecrireEtEnvoyer = async () => {
        fireEvent.change(screen.getByRole("textbox"), { target: { value: "Prépare un plan" } });
        const envoyer = screen.getByRole("button", { name: /Envoyer|Send/ });
        await waitFor(() => expect((envoyer as HTMLButtonElement).disabled).toBe(false));
        fireEvent.click(envoyer);
        await waitFor(() => expect(client.ouvrirUnFilApiV1BuilderFilsPost).toHaveBeenCalled());
        return vi.mocked(client.ouvrirUnFilApiV1BuilderFilsPost).mock.calls[0][0] as { body: Record<string, unknown> };
    };

    it("« Plan » choisi sur l'accueil est envoyé avec la demande", async () => {
        await accueil();
        fireEvent.click(document.querySelector("[data-selecteur-mode]") as HTMLElement);
        fireEvent.click(await waitFor(() => {
            const ligne = document.querySelector<HTMLElement>("[data-mode='plan']");
            expect(ligne).not.toBeNull();
            return ligne as HTMLElement;
        }));
        await waitFor(() => expect(document.querySelector("[data-selecteur-mode='plan']")).not.toBeNull());
        const appel = await ecrireEtEnvoyer();
        expect(appel.body.mode).toBe("plan");
        await waitFor(() => expect(m.push).toHaveBeenCalledWith("/labo/builder/41"));
    });

    it("sans choix, rien n'est envoyé : le chat repart sur « demander »", async () => {
        await accueil();
        const appel = await ecrireEtEnvoyer();
        expect("mode" in appel.body).toBe(false);
    });
});

describe("sous la saisie", () => {
    it("« Reprendre » montre les trois derniers chats en cartes qui ouvrent le chat", async () => {
        m.agents = [{ id: 5, name: "Cabinet Dupont" }];
        await accueil();
        const cartes = await waitFor(() => {
            const l = [...document.querySelectorAll<HTMLAnchorElement>("[data-reprendre]")];
            expect(l).toHaveLength(3);
            return l;
        });
        expect(cartes.map((c) => c.getAttribute("href"))).toEqual(["/labo/builder/9", "/labo/builder/8", "/labo/builder/7"]);
        expect(cartes[0].textContent).toContain("Cabinet Dupont");
        expect(cartes[0].textContent).toContain("Claude Code");
        expect(screen.queryByText("Quatrième, hors des trois derniers")).toBeNull();
    });

    it("« Mise en route » : une barre de progression reliée à « Prêt à publier », 2 faites sur 3", async () => {
        m.agents = [{ id: 5, name: "Cabinet Dupont" }];
        m.etapes = [
            { id: "a", etat: "fait", niveau: "requis" },
            { id: "b", etat: "herite", niveau: "requis" },
            { id: "c", etat: "a_faire", niveau: "requis" },
            { id: "d", etat: "sans_objet", niveau: "conseille" },
        ];
        await accueil();
        const barre = await screen.findByRole("progressbar");
        expect(barre.getAttribute("aria-valuenow")).toBe("67");
        const carte = barre.closest("a") as HTMLAnchorElement;
        expect(carte.textContent).toMatch(/2 sur 3|2 of 3/);
        expect(carte.getAttribute("href")).toBe("/agents/5/settings");
    });

    it("sans agent, pas de « Mise en route »", async () => {
        await accueil();
        await new Promise((r) => setTimeout(r, 50));
        expect(screen.queryByRole("progressbar")).toBeNull();
    });
});

describe("les marques douces", () => {
    it("l'avertissement MCP est une ligne douce : pas de carte pleine rouge", () => {
        render(<AvertissementClaudeCode />);
        const ligne = screen.getByRole("status");
        expect(ligne.className).not.toMatch(/bg-destructive/);
        expect(ligne.className).toMatch(/text-\(--danger-ink\)/);
    });

    it("la gravité est une pastille pâle ; seule « Grave » est pleine en rouge", () => {
        const { container } = render(
            <>
                <Gravite n={3} />
                <Gravite n={2} />
                <Gravite n={1} />
            </>,
        );
        const [grave, surveiller, faible] = [...container.querySelectorAll("[data-gravite]")].map((e) => e.className);
        expect(grave).toMatch(/bg-destructive/);
        expect(surveiller).toMatch(/bg-\(--info-soft\)/);
        expect(faible).toMatch(/bg-\(--neutral-soft\)/);
        expect(surveiller + faible).not.toMatch(/text-white/);
    });
});
