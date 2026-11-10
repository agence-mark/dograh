/**
 * [.mark] Clôture SA-5 (É35, Evan 09/11) : la liste des appels d'un agent comme la maquette : « Chercher un mot », « Tous les motifs » (les
 * motifs viennent du serveur) et les colonnes Motif, Résumé, Issue, Durée, Jugé par, Note (pastille rouge sous le seuil). Aucun filtrage
 * ici : la recherche et le motif sont rendus au parent, qui les envoie au serveur.
 */
import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import type { WorkflowRunResponseSchema } from "@/client/types.gen";
import { FournisseurLangue } from "@/components/mark/langue/langue";

vi.mock("@/components/mark/studio/liste-deroulante", async () => await import("@/components/mark/studio/liste-deroulante-natif-test"));
vi.mock("next/navigation", () => ({ useRouter: () => ({ push: vi.fn() }) }));
vi.mock("@/hooks/useOrganizationTimezone", () => ({ useOrganizationTimezone: () => "Europe/Paris" }));
vi.mock("@/components/filters/FilterBuilder", () => ({ FilterBuilder: () => <div data-testid="filtres-avances" /> }));
vi.mock("@/components/MediaPreviewDialog", () => ({ MediaPreviewButton: () => null, MediaPreviewDialog: () => ({ openPreview: vi.fn(), dialog: null }) }));

import { WorkflowRunsTable } from "./WorkflowRunsTable";

afterEach(() => {
    cleanup();
    window.localStorage.clear();
});

const run = (id: number, extra: Partial<WorkflowRunResponseSchema> = {}): WorkflowRunResponseSchema =>
    ({
        id, workflow_id: 9, name: `r${id}`, mode: "twilio", created_at: "2026-11-09T10:00:00Z", is_completed: true, transcript_url: null,
        recording_url: null, cost_info: { call_duration_seconds: 192 }, definition_id: null, call_type: "inbound",
        gathered_context: { mapped_call_disposition: "RDV_pris" }, motif: "Devis", resume: "Un devis pour une chaudière.", juge_par: "openai/juge-m",
        note_juge: 2.5, ...extra,
    }) as WorkflowRunResponseSchema;

const monter = (runs: WorkflowRunResponseSchema[], extra: Record<string, unknown> = {}) => {
    const onRecherche = vi.fn();
    const onMotif = vi.fn();
    render(
        <FournisseurLangue>
            <WorkflowRunsTable
                forme="agent" runs={runs} loading={false} error={null} currentPage={1} totalPages={1} totalCount={runs.length} onPageChange={vi.fn()}
                availableAttributes={[]} activeFilters={[]} onFiltersChange={vi.fn()} onApplyFilters={vi.fn()} onClearFilters={vi.fn()}
                isExecutingFilters={false} workflowId={9} recherche="" onRecherche={onRecherche} motif="" onMotif={onMotif} motifs={["Devis", "Dépannage"]}
                {...extra}
            />
        </FournisseurLangue>,
    );
    return { onRecherche, onMotif };
};

describe("[.mark] la liste des appels d'un agent", () => {
    it("montre Motif, Résumé, Issue, Durée, Jugé par et Note, et plus « Type d'appel »", () => {
        monter([run(1)]);
        const entetes = Array.from(document.querySelectorAll("thead th")).map((t) => t.textContent);
        expect(entetes).toEqual(["Quand", "Motif", "Résumé", "Issue", "Durée", "Jugé par", "Note"]);
        const ligne = document.querySelector("tbody tr")!;
        expect(ligne.textContent).toContain("Un devis pour une chaudière.");
        expect(ligne.textContent).toContain("RDV_pris");
        expect(ligne.textContent).toContain("3m 12s");
        expect(ligne.textContent).toContain("openai/juge-m");
        expect(ligne.textContent).toContain("2,5");
        expect(ligne.querySelector("[data-urgente]")).not.toBeNull(); // sous le seuil : pastille rouge
    });

    it("un appel sans motif, résumé ni juge montre des tirets, jamais rien d'inventé", () => {
        monter([run(2, { motif: null, resume: null, juge_par: null, note_juge: null, gathered_context: {} })]);
        const cellules = Array.from(document.querySelectorAll("tbody tr td")).map((c) => c.textContent);
        expect(cellules.filter((c) => c === "–").length).toBeGreaterThanOrEqual(5);
    });

    it("la recherche et « Tous les motifs » sont rendus au parent, qui interroge le serveur", () => {
        const { onMotif } = monter([run(1)]);
        expect(screen.getByLabelText("Chercher un mot")).toBeTruthy();
        const liste = screen.getByLabelText("Motif") as HTMLSelectElement;
        expect(Array.from(liste.options).map((o) => o.textContent)).toEqual(["Tous les motifs", "Devis", "Dépannage"]);
        fireEvent.change(liste, { target: { value: "Dépannage" } });
        expect(onMotif).toHaveBeenCalledWith("Dépannage");
        expect(screen.getByTestId("filtres-avances")).toBeTruthy(); // aucune fonction en moins : le constructeur de filtres reste
    });

    it("sans résultat pour une recherche : l'état « filtre » avec « Effacer », la barre reste", () => {
        monter([], { recherche: "zzz" });
        expect(screen.getByLabelText("Chercher un mot")).toBeTruthy();
        expect(screen.queryByText("Aucun appel encore")).toBeNull();
    });
});
