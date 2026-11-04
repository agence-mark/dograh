/**
 * [.mark] Partie 3, lot 15 (SE-29, P-1, P-2) : le journal d'équipe.
 *
 *   - P-1 : un compte sans nom se dit « Compte sans nom », jamais son identifiant brut ;
 *   - P-2 : les filtres « Qui » et « Espace » partent au serveur (le total suit), un filtre sans résultat se dit et s'efface ;
 *   - P-6 : les gestes d'écriture du Hub sont dits en clair.
 */
import { cleanup, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { FournisseurLangue } from "@/components/mark/langue/langue";

const sdk = vi.hoisted(() => ({ journal: vi.fn(), membres: vi.fn() }));
vi.mock("@/client/sdk.gen", () => ({
    lireLeJournalApiV1EquipeMarkJournalGet: sdk.journal,
    listerLesMembresApiV1EquipeMarkMembresGet: sdk.membres,
}));
vi.mock("@/lib/espaces", () => ({
    listerEspaces: vi.fn(async () => [
        { id: 7, nom: "Nuances de Feu", provider_id: "ndf", espace: "client", selectionne: false },
        { id: 1, nom: "Labo", provider_id: "labo", espace: "labo", selectionne: true },
    ]),
}));
vi.mock("sonner", () => ({ toast: { error: vi.fn(), success: vi.fn() } }));

import { VueJournal } from "./VueJournal";

Element.prototype.scrollIntoView = vi.fn();
Element.prototype.hasPointerCapture = vi.fn(() => false);
Element.prototype.releasePointerCapture = vi.fn();
const ouvrir = (liste: HTMLElement) => fireEvent.keyDown(liste, { key: "Enter" });

const ligne = (id: number, extra: Record<string, unknown>) => ({
    id,
    quand: "2026-11-03T10:00:00Z",
    user_id: 1,
    auteur: "oss_1",
    prenom: null,
    nom: null,
    qui: null,
    sans_nom: false,
    action: "agents.modifier",
    organization_id: 7,
    detail: null,
    ...extra,
});

beforeEach(() => {
    sdk.membres.mockResolvedValue({
        data: {
            membres: [
                { user_id: 1, email: "evan@exemple.fr", prenom: "Evan", nom: "L", role_id: 1, role_nom: "Administrateur" },
                { user_id: 2, email: "pierre@exemple.fr", prenom: null, nom: null, role_id: 2, role_nom: "Membre" },
            ],
            total: 2,
            limit: 100,
            offset: 0,
        },
    });
    sdk.journal.mockResolvedValue({
        data: {
            lignes: [
                ligne(1, { prenom: "Evan", nom: "L", qui: "Evan L" }),
                ligne(2, { user_id: 2, auteur: "oss_brut_42", sans_nom: true, action: "tests.jouer" }),
                ligne(3, { user_id: null, auteur: "portail : Nuances", qui: "portail : Nuances", action: "relation.message" }),
            ],
            total: 3,
            limit: 25,
            offset: 0,
        },
    });
});
afterEach(() => {
    cleanup();
    sdk.journal.mockReset();
    sdk.membres.mockReset();
});

const monter = () =>
    render(
        <FournisseurLangue>
            <VueJournal />
        </FournisseurLangue>,
    );

describe("[.mark] lot 15 : le journal d'équipe", () => {
    it("P-1 : « Compte sans nom » à la place de l'identifiant brut ; un geste sans compte garde son auteur ; P-6 : le geste du Hub est dit en clair", async () => {
        monter();
        await screen.findByText("Evan L");
        expect(screen.getByText("Compte sans nom")).toBeTruthy();
        expect(document.body.textContent).not.toContain("oss_brut_42");
        expect(screen.getByText("portail : Nuances")).toBeTruthy();
        expect(screen.getByText("A répondu à un client")).toBeTruthy();
    });

    it("P-2 : choisir un membre et un espace envoie les filtres au serveur, à la première page", async () => {
        monter();
        const filtres = await screen.findByTestId("filtres-du-journal");
        await waitFor(() => expect(sdk.membres).toHaveBeenCalled());
        const [qui, espace] = within(filtres).getAllByRole("combobox");
        ouvrir(qui);
        fireEvent.click(await screen.findByRole("option", { name: "Evan L" }));
        await waitFor(() => expect(sdk.journal).toHaveBeenLastCalledWith({ query: expect.objectContaining({ membre: 1 }) }));
        ouvrir(espace);
        fireEvent.click(await screen.findByRole("option", { name: "Nuances de Feu" }));
        await waitFor(() => expect(sdk.journal).toHaveBeenLastCalledWith({ query: expect.objectContaining({ membre: 1, organization_id: 7 }) }));
    });

    it("P-2 : un filtre sans résultat le dit et « effacer » revient à tout le monde", async () => {
        monter();
        const filtres = await screen.findByTestId("filtres-du-journal");
        sdk.journal.mockResolvedValue({ data: { lignes: [], total: 0, limit: 25, offset: 0 } });
        const [, espace] = within(filtres).getAllByRole("combobox");
        ouvrir(espace);
        fireEvent.click(await screen.findByRole("option", { name: "Labo" }));
        expect(await screen.findByText(/aucun résultat/i)).toBeTruthy();
        sdk.journal.mockResolvedValue({ data: { lignes: [ligne(1, { qui: "Evan L", prenom: "Evan", nom: "L" })], total: 1, limit: 25, offset: 0 } });
        fireEvent.click(screen.getByRole("button", { name: /effacer|clear/i }));
        await screen.findByText("Evan L");
        await waitFor(() => expect(sdk.journal.mock.calls.at(-1)![0].query).not.toHaveProperty("organization_id"));
    });
});
