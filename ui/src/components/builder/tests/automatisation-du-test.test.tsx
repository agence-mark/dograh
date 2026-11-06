/**
 * [.mark] Partie 3, N3b (décision 20) : la ligne « Lancer depuis une automatisation » de la fenêtre d'un test.
 *
 * Questions de ce fichier :
 *
 *     L'adresse que n8n appelle porte-t-elle l'identifiant de l'agent et le chemin de la route protégée par la clé ?
 *     Un test existant offre-t-il la ligne qui copie cette adresse (et le dit par une notification), un nouveau test
 *     (sans agent écrit, rien à lancer encore) ne l'offre-t-il pas ?
 */
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { adresseDesTestsParAutomatisation, FenetreDeTest } from "./FenetreDeTest";
import type { TestComplet } from "./types";

const m = vi.hoisted(() => ({ succes: vi.fn(), echec: vi.fn() }));

vi.mock("@/client", () => ({
    changerUnTestApiV1BuilderTestsWorkflowIdSlugPatch: vi.fn(),
    creerUnTestApiV1BuilderTestsWorkflowIdPost: vi.fn(),
    rejouerLaSuiteApiV1BuilderTestsWorkflowIdRejouerPost: vi.fn(),
}));
vi.mock("@/components/mark/notifications", () => ({ notifier: { succes: m.succes, echec: m.echec } }));
vi.mock("@/components/mark/studio/liste-deroulante", async () => await import("@/components/mark/studio/liste-deroulante-natif-test"));

const TEST = { slug: "t", nom: "Un test", obligatoire: false, dossier: "", origine: "manuel", criteres: [], scenario: { but: "Veut un rendez-vous." } } as unknown as TestComplet;
const RESSOURCES = { etapes: [], outils: [], issues: [], champs: [], personnages: [], scenarios_types: [] };

const fenetre = (test?: TestComplet) =>
    render(<FenetreDeTest workflowId={42} test={test} ressources={RESSOURCES as never} onFermer={vi.fn()} onFait={vi.fn()} />);

afterEach(() => {
    cleanup();
    vi.clearAllMocks();
});

describe("Lancer depuis une automatisation", () => {
    it("l'adresse est celle de la route des tests par la clé, avec l'agent, sans double barre", () => {
        expect(adresseDesTestsParAutomatisation(42, undefined, "https://api.exemple.test/")).toBe("https://api.exemple.test/api/v1/automatisation/agents/42/tests/lancer");
        expect(adresseDesTestsParAutomatisation(7, "mon test", "https://api.exemple.test")).toBe("https://api.exemple.test/api/v1/automatisation/agents/7/tests/lancer?test=mon%20test");
    });

    it("un test existant offre la ligne ; un clic copie l'adresse et le dit", async () => {
        const ecrire = vi.fn().mockResolvedValue(undefined);
        Object.assign(navigator, { clipboard: { writeText: ecrire } });
        fenetre(TEST);
        fireEvent.click(await screen.findByTestId("lancer-depuis-une-automatisation"));
        await waitFor(() => expect(ecrire).toHaveBeenCalledTimes(1));
        expect(ecrire.mock.calls[0][0]).toMatch(/\/api\/v1\/automatisation\/agents\/42\/tests\/lancer\?test=t$/); // l'adresse de CE test
        expect(m.succes).toHaveBeenCalledTimes(1);
        expect(m.succes.mock.calls[0][0].en).toContain("X-API-Key");
    });

    it("une copie refusée par le navigateur le dit, sans rien d'autre", async () => {
        Object.assign(navigator, { clipboard: { writeText: vi.fn().mockRejectedValue(new Error("refus")) } });
        fenetre(TEST);
        fireEvent.click(await screen.findByTestId("lancer-depuis-une-automatisation"));
        await waitFor(() => expect(m.echec).toHaveBeenCalledTimes(1));
        expect(m.succes).not.toHaveBeenCalled();
    });

    it("un nouveau test (pas encore écrit) n'offre pas la ligne", async () => {
        fenetre(undefined);
        await screen.findByTestId("fenetre-de-test");
        expect(screen.queryByTestId("lancer-depuis-une-automatisation")).toBeNull();
    });
});
