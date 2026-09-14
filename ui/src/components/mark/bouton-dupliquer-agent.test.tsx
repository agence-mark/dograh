/**
 * [.mark] The Duplicate button on an agent's row.
 *
 * The questions this file answers:
 *
 *     Does the button call the duplication route with the right agent, does it
 *     refuse a second click while the first is running, is it absent on an
 *     archived agent, and does an HTTP error read as an error?
 *
 * ⛔ The last one is not decoration. The generated client does NOT throw on an
 * HTTP error: it resolves with `{ data, error }`. Without the check, a 500
 * would show a success toast and refresh the list onto nothing.
 */

import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { readFileSync } from "fs";
import { join } from "path";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { BoutonDupliquerAgent } from "./BoutonDupliquerAgent";

const dupliquer = vi.fn();
const erreurs: string[] = [];
const succes: string[] = [];

vi.mock("@/client", () => ({
    duplicateWorkflowEndpointApiV1WorkflowWorkflowIdDuplicatePost: (
        ...args: unknown[]
    ) => dupliquer(...args),
}));

vi.mock("sonner", () => ({
    toast: {
        error: (m: string) => erreurs.push(m),
        success: (m: string) => succes.push(m),
    },
}));

describe("Bouton Dupliquer", () => {
    beforeEach(() => {
        dupliquer.mockReset();
        erreurs.length = 0;
        succes.length = 0;
    });

    it("appelle la route avec l'identifiant de l'agent", async () => {
        dupliquer.mockResolvedValue({ data: { id: 42 } });
        const onDuplique = vi.fn();
        render(<BoutonDupliquerAgent workflowId={7} onDuplique={onDuplique} />);

        fireEvent.click(screen.getByRole("button", { name: /duplicate/i }));

        await waitFor(() => expect(onDuplique).toHaveBeenCalled());
        expect(dupliquer).toHaveBeenCalledWith({ path: { workflow_id: 7 } });
    });

    it("dit ou se trouve la copie", () => {
        // Without this, people look for the copy inside the folder the
        // original sits in and conclude the button did nothing.
        dupliquer.mockResolvedValue({ data: { id: 42 } });
        render(<BoutonDupliquerAgent workflowId={7} onDuplique={vi.fn()} />);

        fireEvent.click(screen.getByRole("button", { name: /duplicate/i }));

        return waitFor(() =>
            expect(succes.join(" ")).toMatch(/at the root of the list/i),
        );
    });

    it("se desactive pendant la duplication", async () => {
        let resoudre: (v: unknown) => void = () => {};
        dupliquer.mockReturnValue(new Promise((r) => (resoudre = r)));
        render(<BoutonDupliquerAgent workflowId={7} onDuplique={vi.fn()} />);

        const bouton = screen.getByRole("button", { name: /duplicate/i });
        fireEvent.click(bouton);
        expect(bouton.hasAttribute("disabled")).toBe(true);

        fireEvent.click(bouton);
        expect(dupliquer).toHaveBeenCalledTimes(1);

        resoudre({ data: { id: 42 } });
        await waitFor(() => expect(bouton.hasAttribute("disabled")).toBe(false));
    });

    it("traite une erreur HTTP comme une erreur, pas comme un succes", async () => {
        dupliquer.mockResolvedValue({ error: { detail: "boom" } });
        const onDuplique = vi.fn();
        render(<BoutonDupliquerAgent workflowId={7} onDuplique={onDuplique} />);

        fireEvent.click(screen.getByRole("button", { name: /duplicate/i }));

        await waitFor(() => expect(erreurs.length).toBe(1));
        expect(succes).toEqual([]);
        expect(onDuplique).not.toHaveBeenCalled();
    });

    it("est monte dans la liste des agents, et masque sur les archives", () => {
        // ⚠️ Read honestly: this reads their table rather than rendering it
        // (it needs routing, a transition and a folder list). It catches the
        // failure that threatens us -- an upstream rewrite dropping our
        // one-line mount, which no other test would notice.
        // vitest runs with the ui/ package as its working directory.
        const table = readFileSync(
            join(process.cwd(), "src/components/workflow/WorkflowTable.tsx"),
            "utf8",
        );

        expect(table).toMatch(/from ['"]@\/components\/mark\/BoutonDupliquerAgent['"]/);
        expect(table).toContain("<BoutonDupliquerAgent");
        expect(table).toContain("{!showArchived && (");
    });
});
