/**
 * [.mark] G1b : la section « À améliorer » de l'accueil du builder (maquette `SuiviBuilder`).
 *
 * Ce que ce fichier prouve :
 *
 *     Les trois problèmes « à trier » les plus graves s'affichent (gravité, titre, agent · fréquence · cause), « Tout voir » mène à la page ?
 *     Rien à améliorer : l'état « fait » ; chargement : un squelette ; erreur : « Réessayer » ; 403 : « accès » ?
 *     Rien n'est lu avant la connexion ?
 */
import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { FournisseurLangue } from "../langue/langue";
import { SectionAAmeliorer } from "./SectionAAmeliorer";

const m = vi.hoisted(() => ({ liste: vi.fn(), session: { user: { id: "u" } as { id: string } | null, loading: false } }));
vi.mock("@/client", () => ({ lireLesAmeliorationsApiV1AmeliorationsGet: (o: unknown) => m.liste(o) }));
vi.mock("@/lib/auth", () => ({ useAuth: () => m.session }));

const ligne = (id: number, titre: string, gravite: number) => ({
    id, workflow_id: 3, workflow_nom: "Accueil", titre, critere: titre, etape: null, gravite, frequence: { n: 4, sur: 112, genre: "appels" },
    releve_par: "juge", cause: "prompt", etat: "a_trier", origine: null, origine_suggeree: "recette", assigne: null, version: 4, derniere_le: null,
});
const monter = () => render(<FournisseurLangue><SectionAAmeliorer lien="/clients/a/a-ameliorer" /></FournisseurLangue>);

beforeEach(() => {
    m.session.user = { id: "u" };
    m.liste.mockResolvedValue({ data: { lignes: [ligne(1, "A", 3), ligne(2, "B", 2), ligne(3, "C", 2), ligne(4, "D", 1)], page: 0, a_une_suite: false, compteurs: {} } });
});
afterEach(() => {
    cleanup();
    m.liste.mockReset();
});

describe("[.mark] G1b : section « À améliorer » de l'accueil", () => {
    it("montre les trois premiers problèmes à trier et un lien « Tout voir » vers la page de l'espace", async () => {
        monter();
        expect(await screen.findByText("A")).toBeTruthy();
        expect(screen.getByText("C")).toBeTruthy();
        expect(screen.queryByText("D")).toBeNull();
        expect(screen.getAllByText(/Accueil · 4 appels sur 112 · Prompt/)).toHaveLength(3);
        expect(screen.getByRole("link", { name: "Tout voir" }).getAttribute("href")).toBe("/clients/a/a-ameliorer");
        expect(m.liste).toHaveBeenCalledTimes(1);
        expect(m.liste.mock.calls[0][0]).toEqual({ query: { etat: "a_trier" } });
    });

    it("rien à améliorer : l'état « fait », jamais une liste vide", async () => {
        m.liste.mockResolvedValue({ data: { lignes: [], page: 0, a_une_suite: false, compteurs: {} } });
        monter();
        expect(await screen.findByText("Rien à améliorer")).toBeTruthy();
        expect(document.querySelector("ul")).toBeNull();
    });

    it("pendant la lecture un squelette, jamais un écran blanc", () => {
        m.liste.mockReturnValue(new Promise(() => undefined));
        monter();
        expect(document.querySelector('[aria-busy="true"]')).toBeTruthy();
    });

    it("erreur : « Réessayer » relit ; accès refusé : pas de bouton", async () => {
        m.liste.mockResolvedValueOnce({ error: { detail: "x" } });
        monter();
        fireEvent.click(await screen.findByRole("button", { name: /Réessayer/ }));
        expect(await screen.findByText("A")).toBeTruthy();
        cleanup();
        m.liste.mockResolvedValue({ error: { detail: "x" }, response: { status: 403 } });
        monter();
        expect(await screen.findByText(/Réservé aux administrateurs/)).toBeTruthy();
        expect(screen.queryByRole("button", { name: /Réessayer/ })).toBeNull();
    });

    it("ne lit rien avant la connexion", () => {
        m.session.user = null;
        monter();
        expect(m.liste).not.toHaveBeenCalled();
    });
});
