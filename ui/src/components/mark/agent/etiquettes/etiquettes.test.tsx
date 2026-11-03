/**
 * [.mark] Les étiquettes des agents (U3, E30), côté écran.
 *
 * Questions de ce fichier :
 *
 *     Le filtre ne propose-t-il que les étiquettes qui ont un agent, et garde-t-il les agents qui en portent au moins
 *     une ? La fenêtre coche les étiquettes de l'agent, crée une nouvelle sans doubler une existante, et enregistre
 *     par la vraie route ? La liste des agents montre-t-elle les étiquettes sur les lignes et se filtre-t-elle ?
 */
import { cleanup, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import type { EtiquettesResponse } from "@/client/types.gen";

import { FenetreEtiquettes } from "./FenetreEtiquettes";
import { FiltreEtiquettes } from "./FiltreEtiquettes";
import { ajouter, basculer, etiquettesDuFiltre, filtrerLesAgents } from "./logique";

const m = vi.hoisted(() => ({ lire: vi.fn(), poser: vi.fn() }));
vi.mock("next/navigation", () => ({ useRouter: () => ({ push: vi.fn(), refresh: vi.fn() }) }));
vi.mock("sonner", () => ({ toast: Object.assign(vi.fn(), { error: vi.fn(), success: vi.fn() }) }));
vi.mock("@/lib/auth", () => ({ useAuth: () => ({ user: { id: "u" }, loading: false }) }));
vi.mock("@/hooks/useOrganizationTimezone", () => ({ useOrganizationTimezone: () => "UTC" }));
vi.mock("@/client/sdk.gen", () => ({
    lireLesEtiquettesApiV1EtiquettesGet: m.lire,
    poserLesEtiquettesApiV1EtiquettesAgentsWorkflowIdPut: m.poser,
}));

const DONNEES: EtiquettesResponse = {
    etiquettes: [
        { nom: "Recette", nb_agents: 2 },
        { nom: "Banc", nb_agents: 1 },
        { nom: "Orpheline", nb_agents: 0 },
    ],
    par_agent: { "1": ["Recette", "Banc"], "2": ["Recette"] },
};

beforeEach(() => {
    m.lire.mockReset();
    m.poser.mockReset();
    m.lire.mockResolvedValue({ data: DONNEES });
});
afterEach(cleanup);

describe("la logique", () => {
    it("le filtre ne propose que les étiquettes qui ont au moins un agent", () => {
        expect(etiquettesDuFiltre(DONNEES)).toEqual(["Recette", "Banc"]);
        expect(etiquettesDuFiltre(null)).toEqual([]);
    });

    it("garde les agents qui portent au moins une étiquette choisie, tous si aucune n'est choisie", () => {
        const agents = [{ id: 1 }, { id: 2 }, { id: 3 }];
        expect(filtrerLesAgents(agents, DONNEES.par_agent, [])).toHaveLength(3);
        expect(filtrerLesAgents(agents, DONNEES.par_agent, ["Banc"]).map((a) => a.id)).toEqual([1]);
        expect(filtrerLesAgents(agents, DONNEES.par_agent, ["Banc", "Recette"]).map((a) => a.id)).toEqual([1, 2]);
        expect(filtrerLesAgents(agents, DONNEES.par_agent, ["recette"]).map((a) => a.id)).toEqual([1, 2]);
        expect(filtrerLesAgents(agents, DONNEES.par_agent, ["Inconnue"])).toEqual([]);
    });

    it("coche et décoche sans tenir compte de la casse ; une étiquette existante n'est pas dupliquée", () => {
        expect(basculer(["Recette"], "recette")).toEqual([]);
        expect(basculer([], "Banc")).toEqual(["Banc"]);
        expect(ajouter("  recette ", [], ["Recette"])).toEqual({ selection: ["Recette"], connues: ["Recette"] });
        expect(ajouter("Nouvelle", ["Recette"], ["Recette"])).toEqual({
            selection: ["Recette", "Nouvelle"],
            connues: ["Recette", "Nouvelle"],
        });
        expect(ajouter("   ", [], [])).toBe("vide");
        expect(ajouter("x".repeat(41), [], [])).toBe("trop-long");
    });
});

describe("le filtre de la liste", () => {
    it("n'est pas dessiné quand aucune étiquette n'a d'agent", () => {
        const { container } = render(<FiltreEtiquettes proposees={[]} choisies={[]} onChange={vi.fn()} />);
        expect(container.firstChild).toBeNull();
    });

    it("propose les étiquettes et rend la sélection cochée", async () => {
        const onChange = vi.fn();
        render(<FiltreEtiquettes proposees={["Recette", "Banc"]} choisies={["Recette"]} onChange={onChange} />);
        const pastille = document.querySelector("[data-filtre-etiquettes]") as HTMLElement;
        expect(pastille.textContent).toContain("1");
        fireEvent.click(pastille);
        fireEvent.click(await screen.findByRole("checkbox", { name: "Banc" }));
        expect(onChange).toHaveBeenCalledWith(["Recette", "Banc"]);
        fireEvent.click(screen.getByRole("button", { name: "Clear" }));
        expect(onChange).toHaveBeenLastCalledWith([]);
    });
});

describe("la fenêtre « Étiquettes » d'un agent", () => {
    const monter = (agentId = 1) => {
        const onEnregistre = vi.fn();
        const onOuvertChange = vi.fn();
        render(<FenetreEtiquettes agentId={agentId} ouvert onOuvertChange={onOuvertChange} onEnregistre={onEnregistre} />);
        return { onEnregistre, onOuvertChange };
    };

    it("coche celles que l'agent porte, parmi toutes celles de l'organisation", async () => {
        monter(2);
        const liste = await waitFor(() => {
            const l = document.querySelector("[data-liste-etiquettes]");
            if (!l) throw new Error("liste absente");
            return l as HTMLElement;
        });
        const coche = (nom: string) => within(liste).getByRole("checkbox", { name: nom }).getAttribute("aria-checked");
        expect([coche("Recette"), coche("Banc"), coche("Orpheline")]).toEqual(["true", "false", "false"]);
    });

    it("enregistre la sélection et une étiquette nouvelle par la route, puis ferme", async () => {
        m.poser.mockResolvedValue({ data: DONNEES });
        const { onEnregistre, onOuvertChange } = monter(2);
        await screen.findByRole("checkbox", { name: "Banc" });
        fireEvent.click(screen.getByRole("checkbox", { name: "Banc" }));
        fireEvent.change(screen.getByLabelText("New label"), { target: { value: "Nouvelle" } });
        fireEvent.keyDown(screen.getByLabelText("New label"), { key: "Enter" });
        fireEvent.click(screen.getByRole("button", { name: "Save" }));
        await waitFor(() => expect(m.poser).toHaveBeenCalled());
        expect(m.poser).toHaveBeenCalledWith({ path: { workflow_id: 2 }, body: { etiquettes: ["Recette", "Banc", "Nouvelle"] } });
        await waitFor(() => expect(onOuvertChange).toHaveBeenCalledWith(false));
        expect(onEnregistre).toHaveBeenCalledTimes(1);
    });

    it("taper une étiquette qui existe déjà la coche, sans en créer une seconde", async () => {
        m.poser.mockResolvedValue({ data: DONNEES });
        monter(2);
        await screen.findByRole("checkbox", { name: "Banc" });
        fireEvent.change(screen.getByLabelText("New label"), { target: { value: "banc" } });
        fireEvent.click(screen.getByRole("button", { name: "Add" }));
        fireEvent.click(screen.getByRole("button", { name: "Save" }));
        await waitFor(() => expect(m.poser).toHaveBeenCalled());
        expect(m.poser.mock.calls[0][0].body.etiquettes).toEqual(["Recette", "Banc"]);
    });

    it("refuse une étiquette trop longue avant tout envoi, et dit l'échec du serveur sans fermer", async () => {
        const { onOuvertChange } = monter(2);
        await screen.findByRole("checkbox", { name: "Banc" });
        fireEvent.change(screen.getByLabelText("New label"), { target: { value: "x".repeat(41) } });
        fireEvent.click(screen.getByRole("button", { name: "Add" }));
        expect(screen.getByRole("alert").textContent).toContain("40 characters");
        fireEvent.change(screen.getByLabelText("New label"), { target: { value: "" } });
        m.poser.mockResolvedValue({ error: { detail: "An agent has 20 labels at most." } });
        fireEvent.click(screen.getByRole("button", { name: "Save" }));
        await waitFor(() => expect(m.poser).toHaveBeenCalled());
        expect(onOuvertChange).not.toHaveBeenCalledWith(false);
    });
});

describe("la liste des agents", () => {
    it("montre les étiquettes sur les lignes et se filtre", async () => {
        const { AgentFolderView } = await import("@/components/workflow/folders/AgentFolderView");
        const agent = (id: number, name: string) => ({ id, name, status: "active", created_at: "2026-10-01T00:00:00Z", total_runs: 0, folder_id: null });
        render(<AgentFolderView workflows={[agent(1, "Alpha"), agent(2, "Bravo"), agent(3, "Charlie")] as never} folders={[]} />);
        await waitFor(() => expect(document.querySelectorAll("[data-etiquettes-de-l-agent]")).toHaveLength(2));
        expect(screen.getByText("Charlie")).toBeTruthy();

        fireEvent.click(document.querySelector("[data-filtre-etiquettes]") as HTMLElement);
        fireEvent.click(await screen.findByRole("checkbox", { name: "Banc" }));
        await waitFor(() => expect(screen.queryByText("Bravo")).toBeNull());
        expect(screen.getByText("Alpha")).toBeTruthy();
        expect(screen.queryByText("Charlie")).toBeNull();
        // L'étiquette sans agent n'est pas au filtre.
        expect(screen.queryByRole("checkbox", { name: "Orpheline" })).toBeNull();
    });
});
