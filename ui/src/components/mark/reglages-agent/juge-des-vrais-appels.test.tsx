/**
 * [.mark] RA-B (R6, audit 06) : « Juge des vrais appels » par agent : l'interrupteur, les trois filtres repris de Dograh (part
 * jugée, durée minimale, répondeurs exclus) et le libellé « allumé mais pas réglé » quand le juge du Labo ne peut pas juger.
 */
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { FournisseurLangue } from "../langue/langue";
import { JugeDesVraisAppels } from "./JugeDesVraisAppels";

const m = vi.hoisted(() => ({ lire: vi.fn(), regler: vi.fn(), depense: vi.fn() }));
vi.mock("@/client/sdk.gen", async (importOriginal) => (await import("../sdk-factice")).sdkFactice(await importOriginal(), {
    lireLeJugeDesVraisAppelsApiV1WorkflowWorkflowIdJugeVraisAppelsGet: m.lire,
    reglerLeJugeDesVraisAppelsApiV1WorkflowWorkflowIdJugeVraisAppelsPut: m.regler,
    getDepenseDesRolesApiV1AppelSimuleDepenseGet: m.depense,
}));
vi.mock("sonner", () => ({ toast: { success: vi.fn(), error: vi.fn(), warning: vi.fn(), info: vi.fn(), loading: vi.fn() } }));

const lu = (c: object = {}) => ({ data: { actif: true, part: 100, duree_min_s: 0, repondeurs_exclus: false, etat_du_juge: "regle", ...c } });
const depenseDuJuge = (j: object = {}) => ({
    mois: "2026-11-01",
    appelant: { appels: 0, jetons: 0, cout: 0, budget_mois: 0, actif: true, atteint: false },
    juge: { appels: 12, jetons: 18000, cout: 1.25, budget_mois: 5, actif: true, atteint: false, ...j },
});
const monter = () => render(<FournisseurLangue><JugeDesVraisAppels workflowId={7} /></FournisseurLangue>);

beforeEach(() => {
    m.depense.mockResolvedValue({ data: depenseDuJuge() });
    m.regler.mockImplementation(async ({ body }) => ({ data: { ...lu().data, ...body } }));
});
afterEach(() => {
    cleanup();
    vi.clearAllMocks();
});

describe("Juge des vrais appels", () => {
    it("éteint : seul l'interrupteur se montre, aucun filtre", async () => {
        m.lire.mockResolvedValue(lu({ actif: false }));
        monter();
        await waitFor(() => expect((screen.getByRole("checkbox", { name: "Juge des vrais appels" }) as HTMLInputElement).disabled).toBe(false));
        expect(document.querySelector('[data-filtre="part"]')).toBeNull();
    });

    it("allumé : les trois filtres se règlent et partent avec leur valeur", async () => {
        m.lire.mockResolvedValue(lu());
        monter();
        const part = (await screen.findByLabelText("Part des appels jugés (%)")) as HTMLInputElement;
        fireEvent.change(part, { target: { value: "30" } });
        fireEvent.blur(part);
        await waitFor(() => expect(m.regler).toHaveBeenLastCalledWith({ path: { workflow_id: 7 }, body: { actif: true, part: 30 } }));
        const duree = screen.getByLabelText("Durée minimale (secondes)");
        fireEvent.change(duree, { target: { value: "10" } });
        fireEvent.blur(duree);
        await waitFor(() => expect(m.regler).toHaveBeenLastCalledWith({ path: { workflow_id: 7 }, body: { actif: true, duree_min_s: 10 } }));
        fireEvent.click(screen.getByRole("checkbox", { name: "Exclure les répondeurs" }));
        await waitFor(() => expect(m.regler).toHaveBeenLastCalledWith({ path: { workflow_id: 7 }, body: { actif: true, repondeurs_exclus: true } }));
    });

    it("clôture, lot C : chacun des cinq critères du vécu est activable, coché par défaut, et part avec la liste des éteints", async () => {
        m.lire.mockResolvedValue(lu());
        monter();
        const boucle = (await screen.findByLabelText("L'agent ne tourne pas en boucle")) as HTMLInputElement;
        expect(document.querySelectorAll("[data-vecu]")).toHaveLength(5);
        expect(Array.from(document.querySelectorAll<HTMLInputElement>("[data-vecu] input")).every((c) => c.checked)).toBe(true);
        fireEvent.click(boucle);
        await waitFor(() => expect(m.regler).toHaveBeenLastCalledWith({ path: { workflow_id: 7 }, body: { actif: true, vecu_eteints: ["boucle"] } }));
        await waitFor(() => expect((screen.getByLabelText("L'agent ne tourne pas en boucle") as HTMLInputElement).checked).toBe(false));
        fireEvent.click(screen.getByLabelText("Aucun blanc prolongé pendant l'appel"));
        await waitFor(() => expect(m.regler).toHaveBeenLastCalledWith({ path: { workflow_id: 7 }, body: { actif: true, vecu_eteints: ["boucle", "blanc"] } }));
        fireEvent.click(screen.getByLabelText("L'agent ne tourne pas en boucle"));
        await waitFor(() => expect(m.regler).toHaveBeenLastCalledWith({ path: { workflow_id: 7 }, body: { actif: true, vecu_eteints: ["blanc"] } }));
    });

    it("une valeur hors bornes est dite sous le champ et n'est pas envoyée", async () => {
        m.lire.mockResolvedValue(lu());
        monter();
        const part = (await screen.findByLabelText("Part des appels jugés (%)")) as HTMLInputElement;
        fireEvent.change(part, { target: { value: "250" } });
        fireEvent.blur(part);
        expect(await screen.findByText(/entre 1 et 100/i)).toBeTruthy();
        expect(m.regler).not.toHaveBeenCalled();
    });

    it.each([
        ["eteint", /allumé mais pas réglé/i, /est éteint/i],
        ["sans_cle", /allumé mais pas réglé/i, /n'a pas de clé/i],
    ])("allumé mais pas réglé (%s) : l'écran le dit", async (etat, titre, detail) => {
        m.lire.mockResolvedValue(lu({ etat_du_juge: etat }));
        monter();
        const alerte = await screen.findByRole("status");
        expect(alerte.textContent).toMatch(titre);
        expect(alerte.textContent).toMatch(detail);
    });

    it("allumé et réglé : aucun libellé d'alerte", async () => {
        m.lire.mockResolvedValue(lu());
        monter();
        await screen.findByLabelText("Part des appels jugés (%)");
        expect(screen.queryByRole("status")).toBeNull();
    });

    it("allumé : la dépense du mois du juge est dite sous l'interrupteur, avec son budget", async () => {
        m.lire.mockResolvedValue(lu());
        monter();
        const ligne = await waitFor(() => {
            const l = document.querySelector("[data-depense-du-juge]");
            expect(l).not.toBeNull();
            return l as Element;
        });
        expect(ligne.textContent).toMatch(/Dépensé ce mois-ci/);
        expect(ligne.textContent).toMatch(/1[,.]25/);
        expect(ligne.textContent).toMatch(/18[\s  ]?000/);
        expect(ligne.textContent).toMatch(/sur 5|of 5/);
        expect(ligne.textContent).not.toMatch(/Budget atteint/);
    });

    it("budget atteint : la ligne le dit et mène au réglage du budget", async () => {
        m.lire.mockResolvedValue(lu());
        m.depense.mockResolvedValue({ data: depenseDuJuge({ cout: 5.2, atteint: true }) });
        monter();
        const ligne = await waitFor(() => {
            const l = document.querySelector("[data-depense-du-juge]");
            expect(l).not.toBeNull();
            return l as Element;
        });
        expect(ligne.textContent).toMatch(/Budget atteint/);
        expect(ligne.textContent).toMatch(/Réglages du Labo/);
    });

    it("éteint, ou dépense illisible : aucune ligne de dépense, pas de fausse valeur", async () => {
        m.lire.mockResolvedValue(lu({ actif: false }));
        monter();
        await waitFor(() => expect((screen.getByRole("checkbox", { name: "Juge des vrais appels" }) as HTMLInputElement).disabled).toBe(false));
        expect(document.querySelector("[data-depense-du-juge]")).toBeNull();
        cleanup();
        m.lire.mockResolvedValue(lu());
        m.depense.mockResolvedValue({ error: { detail: "x" } });
        monter();
        await screen.findByLabelText("Part des appels jugés (%)");
        expect(document.querySelector("[data-depense-du-juge]")).toBeNull();
    });
});
