/**
 * [.mark] Clôture SA-5 (Evan, 09/11) : la vue « Issues de l'appel » de la maquette (partie 3), en lecture seule : les issues enregistrées de
 * l'agent (celles de départ et les siennes), « Régler » ouvre l'éditeur du thème Données posé sur ce réglage. Rien ne s'y écrit.
 */
import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { UnsavedChangesProvider } from "@/context/UnsavedChangesContext";
import type { WorkflowConfigurations } from "@/types/workflow-configurations";

import { FournisseurLangue } from "../langue/langue";
import { ID_THEME_DONNEES } from "./ThemeDonnees";
import { ThemeInterventions } from "./ThemeInterventions";

vi.mock("sonner", () => ({ toast: { success: vi.fn(), error: vi.fn() } }));

afterEach(() => {
    cleanup();
    vi.clearAllMocks();
    window.localStorage.clear();
});

const DEPART = [
    { code: "XFER", description: "Transféré à une personne." },
    { code: "RDV_PRIS", description: "Un rendez-vous est pris." },
];

const monter = (issues: Array<{ code: string; description: string }>, versReglage = vi.fn()) => {
    render(
        <FournisseurLangue>
            <UnsavedChangesProvider>
                <ThemeInterventions
                    resolue={{ call_dispositions: issues } as WorkflowConfigurations}
                    workflowName="Agent"
                    onSave={vi.fn().mockResolvedValue(undefined)}
                    ouvert
                    onBasculer={() => undefined}
                    ouvrir={() => undefined}
                    versReglage={versReglage}
                    issuesParDefaut={DEPART}
                />
            </UnsavedChangesProvider>
        </FournisseurLangue>,
    );
    return versReglage;
};

describe("[.mark] la vue Issues de l'appel", () => {
    it("liste les issues enregistrées dans leur ordre, celles de départ et les siennes", () => {
        monter([...DEPART, { code: "DEVIS_DEMANDE", description: "Le client veut un devis." }]);
        const vue = document.querySelector("[data-vue='issues-de-l-appel']")!;
        expect(vue.textContent).toContain("Issues de l'appel");
        const lignes = Array.from(vue.querySelectorAll("li")).map((l) => l.textContent ?? "");
        expect(lignes).toHaveLength(3);
        expect(lignes[0]).toContain("XFER");
        expect(lignes[0]).toContain("De départ");
        expect(lignes[2]).toContain("DEVIS_DEMANDE");
        expect(lignes[2]).toContain("Propre à l'agent");
        expect(vue.querySelector("input, textarea")).toBeNull(); // lecture seule
    });

    it("« Régler » ouvre l'éditeur du thème Données, posé sur les issues", () => {
        const versReglage = monter(DEPART);
        fireEvent.click(screen.getByRole("button", { name: "Régler : RDV_PRIS" }));
        expect(versReglage).toHaveBeenCalledWith(ID_THEME_DONNEES, "call_dispositions");
    });

    it("un agent sans issue enregistrée le dit", () => {
        monter([]);
        expect(screen.getByText(/Aucune issue enregistrée/)).toBeTruthy();
        expect(document.querySelectorAll("[data-vue='issues-de-l-appel'] li")).toHaveLength(0);
    });
});
