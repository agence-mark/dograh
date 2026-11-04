/**
 * [.mark] Partie 3, sous-lot 11 (SE-14, E-1) : la carte « Archivage proposé ». Le builder propose, rien n'est archivé avant le clic ;
 * le clic archive et offre d'annuler ; un échec le dit sans archiver.
 */
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

const m = vi.hoisted(() => ({ statut: vi.fn(), reversible: vi.fn(), echec: vi.fn(), succes: vi.fn() }));
vi.mock("@/client", () => ({ updateWorkflowStatusApiV1WorkflowWorkflowIdStatusPut: (o: unknown) => m.statut(o) }));
vi.mock("@/components/mark/notifications", () => ({ notifier: { reversible: m.reversible, echec: m.echec, succes: m.succes } }));
vi.mock("next/link", () => ({ default: ({ children, href }: { children: React.ReactNode; href: string }) => <a href={href}>{children}</a> }));

import { CarteProposeArchivage } from "./cartes-c2";

afterEach(() => {
    cleanup();
    Object.values(m).forEach((f) => f.mockReset());
});

const carte = { type: "proposition_archivage", workflow_id: 7, nom: "Accueil v1", raison: "Remplacé par la v2." };

describe("carte d'archivage proposé", () => {
    it("n'archive rien tant qu'on ne clique pas, puis archive et offre d'annuler", async () => {
        m.statut.mockResolvedValue({ data: {} });
        render(<CarteProposeArchivage carte={carte} />);
        expect(screen.getByText("Accueil v1")).toBeTruthy();
        expect(screen.getByText(/Remplacé par la v2/)).toBeTruthy();
        expect(m.statut).not.toHaveBeenCalled();
        fireEvent.click(screen.getByRole("button", { name: "Archive this agent" }));
        await waitFor(() => expect(m.statut).toHaveBeenCalledWith({ path: { workflow_id: 7 }, body: { status: "archived" } }));
        await screen.findByText("Archived");
        expect(screen.queryByRole("button", { name: "Archive this agent" })).toBeNull();
        // « Annuler » : l'inverse remet l'agent actif et rend le bouton.
        const inverse = m.reversible.mock.calls[0][1] as () => Promise<void>;
        await inverse();
        expect(m.statut).toHaveBeenLastCalledWith({ path: { workflow_id: 7 }, body: { status: "active" } });
        await screen.findByRole("button", { name: "Archive this agent" });
    });

    it("un échec le dit et laisse le bouton", async () => {
        m.statut.mockResolvedValue({ error: { detail: "x" } });
        render(<CarteProposeArchivage carte={carte} />);
        fireEvent.click(screen.getByRole("button", { name: "Archive this agent" }));
        await waitFor(() => expect(m.echec).toHaveBeenCalled());
        expect(m.reversible).not.toHaveBeenCalled();
        expect(screen.getByRole("button", { name: "Archive this agent" })).toBeTruthy();
    });
});
