/**
 * [.mark] Lot « façon Tala par motif » (T2, T3) : les deux sections de la fenêtre « Publier ».
 *
 * Questions de ce fichier :
 *
 *     Le bilan de santé montre-t-il une ligne par défaut (étape, extrait) ? « Ignorer pour cette version » l'écrit au journal par le
 *     serveur puis range la ligne, et un défaut qui bloque ne propose pas d'ignorer ? Le poids : lignes du plus lourd au plus léger,
 *     trait du seuil seulement s'il existe, jamais de blocage ; un clic sur l'étape l'ouvre ; « Régler un seuil » mène à Briques ?
 */
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { BilanDeSante, PoidsDeLAgentSection } from "./BilanEtPoids";
import type { DefautDuPrompt, PoidsDeLAgent } from "./types";

const m = vi.hoisted(() => ({ ignorer: vi.fn() }));
vi.mock("sonner", () => ({ toast: Object.assign(vi.fn(), { promise: vi.fn(), success: vi.fn(), error: vi.fn() }) }));
vi.mock("@/client/sdk.gen", () => ({
    ignorerUnDefautApiV1BuilderPublicationWorkflowIdIgnorerUnDefautPost: (o: unknown) => m.ignorer(o),
}));

const DEFAUTS: DefautDuPrompt[] = [
    { code: "valeur_en_dur", statut: "avertissement", message: "m", etape: "Accueil", extrait: "45 euros", noeud_id: "1" },
    { code: "action_sans_outil", statut: "echec", message: "m", etape: "Rendez-vous", extrait: "enregistre", noeud_id: "3" },
];

const POIDS = (surcharge: Partial<PoidsDeLAgent> = {}): PoidsDeLAgent => ({
    actif: true,
    plafond_prompt: null,
    poids_max: null,
    etapes: [
        { etape: "Tri", noeud_id: "3", general: 100, texte: 300, conditions: 50, nb_conditions: 2, total: 450 },
        { etape: "Fin", noeud_id: "2", general: 100, texte: 10, conditions: 0, nb_conditions: 0, total: 110 },
    ],
    ...surcharge,
});

beforeEach(() => {
    m.ignorer.mockReset().mockResolvedValue({ data: { ok: true } });
    window.localStorage.clear();
});
afterEach(cleanup);

describe("le bilan de santé du prompt", () => {
    it("montre une ligne par défaut avec l'étape et l'extrait, et mène à l'étape", () => {
        const ouvrir = vi.fn();
        render(<BilanDeSante agentId={5} version={3} defauts={DEFAUTS} ouvrirEtape={ouvrir} />);
        expect(document.querySelectorAll("[data-defaut]").length).toBe(2);
        expect(screen.getByText("« Accueil »", { exact: false })).toBeTruthy();
        expect(screen.getByText("« … 45 euros … »")).toBeTruthy();
        fireEvent.click(screen.getAllByRole("button", { name: "Open the step" })[0]);
        expect(ouvrir).toHaveBeenCalledWith("1");
        expect(screen.getByRole("button", { name: "Add a tool" })).toBeTruthy();
    });

    it("« Ignorer pour cette version » l'écrit au journal par le serveur puis range la ligne ; un défaut qui bloque ne propose pas d'ignorer", async () => {
        render(<BilanDeSante agentId={5} version={3} defauts={DEFAUTS} ouvrirEtape={vi.fn()} />);
        expect(screen.getAllByRole("button", { name: "Ignore for this version" }).length).toBe(1);
        fireEvent.click(screen.getByRole("button", { name: "Ignore for this version" }));
        await waitFor(() => expect(m.ignorer).toHaveBeenCalled());
        expect(m.ignorer.mock.calls[0][0]).toEqual({
            path: { workflow_id: 5 },
            body: { code: "valeur_en_dur", etape: "Accueil", extrait: "45 euros", version: 3 },
        });
        await waitFor(() => expect(document.querySelector('[data-defaut="valeur_en_dur"]')).toBeNull());
        expect(document.querySelector('[data-defaut="action_sans_outil"]')).toBeTruthy();
    });

    it("un échec du journal ne range rien", async () => {
        m.ignorer.mockResolvedValue({ error: { detail: "x" } });
        render(<BilanDeSante agentId={5} version={3} defauts={DEFAUTS} ouvrirEtape={vi.fn()} />);
        fireEvent.click(screen.getByRole("button", { name: "Ignore for this version" }));
        await waitFor(() => expect(m.ignorer).toHaveBeenCalled());
        expect(document.querySelector('[data-defaut="valeur_en_dur"]')).toBeTruthy();
    });

    it("sans défaut, aucune section", () => {
        render(<BilanDeSante agentId={5} version={3} defauts={[]} ouvrirEtape={vi.fn()} />);
        expect(document.querySelector('[data-section="bilan-de-sante"]')).toBeNull();
    });
});

describe("le poids de l'agent", () => {
    it("sans seuil : les nombres seuls, aucun trait de seuil, aucune ligne en rouge", () => {
        render(<PoidsDeLAgentSection poids={POIDS()} regler={vi.fn()} ouvrirEtape={vi.fn()} />);
        expect(screen.getByText(/No threshold set/)).toBeTruthy();
        const lignes = Array.from(document.querySelectorAll("[data-etape-poids]"));
        expect(lignes.map((l) => l.getAttribute("data-etape-poids"))).toEqual(["3", "2"]); // du plus lourd au plus léger
        expect(lignes.every((l) => l.getAttribute("data-au-dessus") === "non")).toBe(true);
        expect(document.querySelectorAll(".w-px").length).toBe(0);
        expect(screen.getByRole("button", { name: "Set a threshold" })).toBeTruthy();
    });

    it("avec un seuil : le trait est dessiné, la ligne au-dessus passe « à relire », la publication n'est pas touchée", () => {
        render(<PoidsDeLAgentSection poids={POIDS({ poids_max: 200 })} regler={vi.fn()} ouvrirEtape={vi.fn()} />);
        expect(screen.getByText(/Threshold of/)).toBeTruthy();
        expect(document.querySelectorAll(".w-px").length).toBe(2);
        expect(document.querySelector('[data-etape-poids="3"]')?.getAttribute("data-au-dessus")).toBe("oui");
        expect(document.querySelector('[data-etape-poids="2"]')?.getAttribute("data-au-dessus")).toBe("non");
        expect(screen.getByRole("button", { name: "Change the threshold" })).toBeTruthy();
    });

    it("un clic sur l'étape l'ouvre ; « Régler un seuil » mène à Briques", () => {
        const ouvrir = vi.fn();
        const regler = vi.fn();
        render(<PoidsDeLAgentSection poids={POIDS()} regler={regler} ouvrirEtape={ouvrir} />);
        fireEvent.click(screen.getByRole("button", { name: "Tri" }));
        expect(ouvrir).toHaveBeenCalledWith("3");
        fireEvent.click(screen.getByRole("button", { name: "Set a threshold" }));
        expect(regler).toHaveBeenCalled();
    });

    it("éteint : aucune section", () => {
        render(<PoidsDeLAgentSection poids={POIDS({ actif: false })} regler={vi.fn()} ouvrirEtape={vi.fn()} />);
        expect(document.querySelector('[data-section="poids-de-l-agent"]')).toBeNull();
    });
});
