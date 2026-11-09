/**
 * [.mark] Builder partie 3, lot 22 : la carte « Bloc réutilisable » de la fiche d'un élément de la bibliothèque.
 *
 * | Test | La garantie |
 * |---|---|
 * | familles | seule une famille qui écrit des prompts a la carte |
 * | étiquette | la carte montre l'étiquette à déposer et la dernière version en Recette |
 * | suivre ou rester | « Utilisé dans » liste les prompts ; le choix joue dans les deux sens et écrit dans le brouillon de CET agent |
 * | mode (D17) | le mode du bloc et celui de l'agent (défaut, en direct, figé) se posent dans le brouillon de CET agent ; l'écran dit que le choix vaut à la prochaine publication |
 */
import { cleanup, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import type { Element as ElementBibliotheque } from "@/client/types.gen";

import { FournisseurLangue } from "../mark/langue/langue";
import { BlocReutilisable } from "./BlocReutilisable";

const m = vi.hoisted(() => ({
    lire: vi.fn(),
    corriger: vi.fn(),
    succes: vi.fn(),
    echec: vi.fn(),
}));
vi.mock("@/client/sdk.gen", () => ({
    lireUtiliseDansApiV1MarkEtiquettesPromptUtiliseDansGet: m.lire,
    corrigerUneEtiquetteApiV1MarkEtiquettesPromptWorkflowIdCorrigerPost: m.corriger,
    lireLesEtiquettesApiV1MarkEtiquettesPromptGet: vi.fn(async () => ({ data: { objets: [], problemes: [] } })),
}));
vi.mock("@/lib/auth", () => ({ useAuth: () => ({ user: { id: 1 }, loading: false }) }));
vi.mock("next/navigation", () => ({ useParams: () => ({}) }));
vi.mock("@/components/mark/notifications", () => ({ notifier: { succes: m.succes, echec: m.echec } }));

afterEach(cleanup);
beforeEach(() => {
    m.lire.mockReset();
    m.corriger.mockReset();
    m.succes.mockReset();
});

const element = (famille: string): ElementBibliotheque =>
    ({
        famille,
        slug: "politesse",
        titre: "Règles de politesse",
        version_courante: 3,
        versions: [
            { numero: 1, statut: "recette", auteur: "a", contenu: { texte: "x" } },
            { numero: 2, statut: "recette", auteur: "a", contenu: { texte: "y" } },
            { numero: 3, statut: "candidat", auteur: "a", contenu: { texte: "z" } },
        ],
    }) as unknown as ElementBibliotheque;

const rendre = (famille = "prompt-general") =>
    render(
        <FournisseurLangue>
            <BlocReutilisable element={element(famille)} />
        </FournisseurLangue>,
    );

describe("la carte Bloc réutilisable", () => {
    it("n'existe pas pour une famille qui n'écrit pas de prompt", () => {
        rendre("scenarios-test");
        expect(screen.queryByTestId("bloc-reutilisable")).toBeNull();
    });

    it("montre l'étiquette et la dernière Recette, puis joue suivre et rester dans les deux sens", async () => {
        m.lire.mockResolvedValue({
            data: { cle: "bloc:politesse", citations: [{ agent_id: 7, agent: "Accueil", noeud_id: "1", etape: "Tri", champ: "nodes[1].prompt", cle: "bloc:politesse", version: null }] },
        });
        m.corriger.mockResolvedValue({ data: { problemes: [] } });
        rendre();
        expect(screen.getByText("{{bloc:politesse}}")).not.toBeNull();
        expect(screen.getByTestId("bloc-reutilisable").textContent).toMatch(/Règles de politesse · v2/);
        const rester = await screen.findByRole("radio", { name: "Reste sur v2" });
        expect(screen.getByRole("radio", { name: "Suit la dernière" }).getAttribute("aria-checked")).toBe("true");
        expect(screen.getByRole("link", { name: "Ouvrir l'étape" }).getAttribute("href")).toBe("/workflow/7?etape=1");
        fireEvent.click(rester);
        await waitFor(() =>
            expect(m.corriger).toHaveBeenCalledWith({
                path: { workflow_id: 7 },
                body: { type: "passer_version", cle: "bloc:politesse", champ: "nodes[1].prompt", version: 2 },
            }),
        );
        expect(m.succes).toHaveBeenCalled();

        m.lire.mockResolvedValue({
            data: { cle: "bloc:politesse", citations: [{ agent_id: 7, agent: "Accueil", noeud_id: "1", etape: "Tri", champ: "nodes[1].prompt", cle: "bloc:politesse@v2", version: 2 }] },
        });
        cleanup();
        rendre();
        fireEvent.click(await screen.findByRole("radio", { name: "Suit la dernière" }));
        await waitFor(() =>
            expect(m.corriger).toHaveBeenLastCalledWith({ path: { workflow_id: 7 }, body: { type: "suivre", cle: "bloc:politesse@v2", champ: "nodes[1].prompt" } }),
        );
    });

    it("dit quand aucun prompt ne cite le bloc", async () => {
        m.lire.mockResolvedValue({ data: { cle: "bloc:politesse", citations: [] } });
        rendre();
        expect(await screen.findByTestId("utilise-dans-vide")).not.toBeNull();
    });

    it("D17 : pose le mode du bloc et celui de l'agent dans le brouillon, et dit que ça vaut à la prochaine publication", async () => {
        m.lire.mockResolvedValue({
            data: {
                cle: "bloc:politesse",
                citations: [{ agent_id: 7, agent: "Accueil", noeud_id: "1", etape: "Tri", champ: "nodes[1].prompt", cle: "bloc:politesse", version: null, mode_du_bloc: "direct", mode_de_l_agent: null }],
            },
        });
        m.corriger.mockResolvedValue({ data: { problemes: [] } });
        rendre();
        const duBloc = await screen.findByRole("radiogroup", { name: "Mode du bloc sur cet agent" });
        expect(within(duBloc).getByRole("radio", { name: "En direct" }).getAttribute("aria-checked")).toBe("true");
        fireEvent.click(within(duBloc).getByRole("radio", { name: "Figé" }));
        await waitFor(() => expect(m.corriger).toHaveBeenLastCalledWith({ path: { workflow_id: 7 }, body: { type: "mode_fige", cle: "bloc:politesse" } }));
        await waitFor(() => expect(m.succes).toHaveBeenCalledWith({ fr: "Mode enregistré dans le brouillon : il vaut à la prochaine publication.", en: "Mode saved in the draft: it applies from the next publication." }));
        const delAgent = screen.getByRole("radiogroup", { name: "Mode des blocs de l'agent" });
        expect(within(delAgent).getByRole("radio", { name: "Défaut" }).getAttribute("aria-checked")).toBe("true");
        fireEvent.click(within(delAgent).getByRole("radio", { name: "Figé" }));
        await waitFor(() => expect(m.corriger).toHaveBeenLastCalledWith({ path: { workflow_id: 7 }, body: { type: "agent_fige", cle: "bloc:politesse" } }));
    });
});
