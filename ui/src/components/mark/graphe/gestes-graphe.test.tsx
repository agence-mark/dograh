import { applyNodeChanges, SelectionMode } from "@xyflow/react";
import { fireEvent, render, screen } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import type { FlowNode } from "@/components/flow/types";
import { useWorkflowStore } from "@/app/workflow/[workflowId]/stores/workflowStore";

import { BandeauSelection, BOUTON_MOLETTE, gestesDuGraphe } from "./gestes-graphe";

const noeud = (id: string, x: number, selected = false): FlowNode =>
    ({ id, type: "agentNode", position: { x, y: 0 }, data: { name: id }, selected }) as FlowNode;

describe("gestes du graphe (T4)", () => {
    it("la molette maintenue déplace la vue, le clic gauche trace un rectangle de sélection", () => {
        const g = gestesDuGraphe(false);
        expect(g.panOnDrag).toEqual([BOUTON_MOLETTE]);
        expect(BOUTON_MOLETTE).toBe(1);
        expect(g.selectionOnDrag).toBe(true);
        expect(g.selectionMode).toBe(SelectionMode.Partial);
    });

    it("sur une version passée, rien ne se sélectionne", () => {
        const g = gestesDuGraphe(true);
        expect(g.selectionOnDrag).toBe(false);
    });

    it("glisser une étape sélectionnée déplace le groupe : toutes les positions sont enregistrées, annulées d'un coup", () => {
        const avant = [noeud("a", 0, true), noeud("b", 100, true), noeud("c", 200, false)];
        useWorkflowStore.getState().clearStore();
        useWorkflowStore.getState().initializeWorkflow(1, "Agent", avant, []);
        const changes = [
            { id: "a", type: "position" as const, position: { x: 50, y: 20 }, dragging: false },
            { id: "b", type: "position" as const, position: { x: 150, y: 20 }, dragging: false },
        ];
        useWorkflowStore.getState().setNodes(applyNodeChanges(changes, useWorkflowStore.getState().nodes) as FlowNode[], changes);
        const pos = () => Object.fromEntries(useWorkflowStore.getState().nodes.map((n) => [n.id, n.position]));
        expect(pos()).toEqual({ a: { x: 50, y: 20 }, b: { x: 150, y: 20 }, c: { x: 200, y: 0 } });
        useWorkflowStore.getState().undo();
        expect(pos()).toEqual({ a: { x: 0, y: 0 }, b: { x: 100, y: 0 }, c: { x: 200, y: 0 } });
    });
});

describe("bandeau de la sélection (T4)", () => {
    let erreur: ReturnType<typeof vi.spyOn>;
    beforeEach(() => {
        erreur = vi.spyOn(console, "error").mockImplementation(() => {});
    });

    it("dit le nombre d'étapes dès qu'il y en a deux, et rien pour une seule", () => {
        const { rerender } = render(<BandeauSelection nombre={1} onAnnuler={() => {}} />);
        expect(screen.queryByRole("status")).toBeNull();
        rerender(<BandeauSelection nombre={3} onAnnuler={() => {}} />);
        expect(screen.getByRole("status").textContent).toContain("3");
    });

    it("Échap annule la sélection, sauf pendant une saisie ; sans sélection, rien n'écoute", () => {
        const annuler = vi.fn();
        const { rerender } = render(<><input aria-label="champ" /><BandeauSelection nombre={2} onAnnuler={annuler} /></>);
        fireEvent.keyDown(screen.getByLabelText("champ"), { key: "Escape" });
        expect(annuler).not.toHaveBeenCalled();
        fireEvent.keyDown(document.body, { key: "Enter" });
        expect(annuler).not.toHaveBeenCalled();
        fireEvent.keyDown(document.body, { key: "Escape" });
        expect(annuler).toHaveBeenCalledTimes(1);
        rerender(<BandeauSelection nombre={0} onAnnuler={annuler} />);
        fireEvent.keyDown(document.body, { key: "Escape" });
        expect(annuler).toHaveBeenCalledTimes(1);
        expect(erreur).not.toHaveBeenCalled(); // aucun « Cannot update a component while rendering »
    });
});
