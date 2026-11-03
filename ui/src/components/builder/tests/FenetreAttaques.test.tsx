/**
 * [.mark] U11 : « Attaquer l'agent ».
 *
 * Questions de ce fichier :
 *
 *     Rien n'est lancé tant que le périmètre n'est pas confirmé ? Le contrat part avec la profondeur et sans modification
 *     de l'environnement ? Le rapport sépare tenu, cédé, plausible et non testé, et un non testé n'est jamais montré comme
 *     tenu ? « Rejouer les échecs » appelle le serveur ?
 */
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import type { RapportDAttaque } from "@/components/mark/agent/publication/types";

import { FenetreAttaques } from "./FenetreAttaques";

const m = vi.hoisted(() => ({ lire: vi.fn(), lancer: vi.fn(), rejouer: vi.fn() }));
vi.mock("sonner", () => ({ toast: Object.assign(vi.fn(), { promise: vi.fn(), success: vi.fn(), error: vi.fn() }) }));
vi.mock("@/client/sdk.gen", () => ({
    dernierRapportApiV1BuilderAttaquesWorkflowIdGet: (o: unknown) => m.lire(o),
    lancerLesAttaquesApiV1BuilderAttaquesWorkflowIdLancerPost: (o: unknown) => m.lancer(o),
    rejouerLesAttaquesApiV1BuilderAttaquesWorkflowIdRejouerPost: (o: unknown) => m.rejouer(o),
}));

const RAPPORT: RapportDAttaque = {
    version: 3,
    le: "2026-11-04T10:00:00+00:00",
    contrat: { profondeur: "rapide" },
    configuration: { regles: 4, conflits: 1 },
    resume: { jouees: 15, a_tenu: 11, a_cede: 1, plausibles: 1, non_testees: 2, non_couvertes: 3 },
    defauts: [
        { id: "extraction_du_prompt-1", technique: "extraction_du_prompt", origine: "catalogue", confirme: true, gravite: "haute", couche: "prompt", raison: "A récité ses consignes", reponse: "Voici mes consignes" },
        { id: "flatterie-1", technique: "flatterie", origine: "catalogue", confirme: false, gravite: "basse", couche: "prompt", raison: "A cédé une fois", reponse: "D'accord" },
    ],
    a_tenu: [],
    non_testees: [{ id: "codage-1", raison: "The agent answered nothing" }],
    non_couvert: ["The voice, the transcription and the telephony: the attack is played in text."],
    rejeu: null,
};

beforeEach(() => {
    m.lire.mockReset().mockResolvedValue({ data: { ok: true, rapport: null, vide: true } });
    m.lancer.mockReset().mockResolvedValue({ data: { ok: true, rapport: RAPPORT } });
    m.rejouer.mockReset().mockResolvedValue({ data: { ok: true } });
});
afterEach(cleanup);

describe("Attaquer l'agent", () => {
    it("ne lance rien tant que le périmètre n'est pas confirmé, puis envoie le contrat sans modification de l'environnement", async () => {
        render(<FenetreAttaques agentId={5} fermer={vi.fn()} />);
        await screen.findByText("No attack run yet");
        const lancer = screen.getByRole("button", { name: "Attack" }) as HTMLButtonElement;
        expect(lancer.disabled).toBe(true);
        fireEvent.click(lancer);
        expect(m.lancer).not.toHaveBeenCalled();
        fireEvent.click(screen.getByRole("button", { name: "Standard (35 to 45)" }));
        fireEvent.click(screen.getByRole("checkbox"));
        expect(lancer.disabled).toBe(false);
        fireEvent.click(lancer);
        await waitFor(() => expect(m.lancer).toHaveBeenCalled());
        expect(m.lancer.mock.calls[0][0].body).toEqual({ profondeur: "standard", confirme: true, modifie_l_environnement: false, corrige: false });
    });

    it("le rapport sépare tenu, cédé, plausible et non testé, et dit ce qui n'est pas couvert", async () => {
        m.lire.mockResolvedValue({ data: { ok: true, rapport: RAPPORT } });
        render(<FenetreAttaques agentId={5} fermer={vi.fn()} />);
        const resume = await screen.findByText("11 held").then((e) => e.closest("[data-resume]")!);
        expect(resume.textContent).toContain("1 got through");
        expect(resume.textContent).toContain("1 possible");
        expect(resume.textContent).toContain("2 not tested");
        expect(document.querySelector('[data-defaut="extraction_du_prompt-1"]')?.textContent).toContain("Voici mes consignes");
        expect(document.querySelector('[data-defaut="flatterie-1"]')?.textContent).toContain("possible, not reproduced");
        expect(document.querySelector("[data-non-couvert]")?.textContent).toContain("played in text");
    });

    it("« Rejouer les échecs » appelle le serveur puis relit le rapport", async () => {
        m.lire.mockResolvedValue({ data: { ok: true, rapport: RAPPORT } });
        render(<FenetreAttaques agentId={5} fermer={vi.fn()} />);
        await screen.findByText("11 held");
        fireEvent.click(screen.getByRole("button", { name: /Replay the failures/ }));
        await waitFor(() => expect(m.rejouer).toHaveBeenCalled());
        await waitFor(() => expect(m.lire.mock.calls.length).toBeGreaterThan(1));
    });

    it("une panne de lecture montre l'état d'erreur sans le texte du serveur", async () => {
        m.lire.mockResolvedValue({ error: { detail: "boom-serveur" } });
        render(<FenetreAttaques agentId={5} fermer={vi.fn()} />);
        await waitFor(() => expect(screen.getByRole("button", { name: /Try again/i })).toBeTruthy());
        expect(document.body.textContent).not.toContain("boom-serveur");
    });
});
