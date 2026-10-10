/**
 * [.mark] The step's field labels, as seen in a step's window of the graph
 * (chantier agent-leger-greffier, lot E, P1).
 *
 * ⛔ This file RENDERS the node's edit form (the same `NodeEditForm` the graph
 * opens), fed with the specs the server serves at `/node-types`
 * (`specs-premiere-replique.json`, checked against the server by
 * `api/tests/mark/test_porte_parlee_premiere_replique.py`). The record is a garage's:
 * nothing here is written for one trade.
 */
import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import type { NodeSpec } from "@/client/types.gen";
import { NodeEditForm } from "@/components/flow/renderer/NodeEditForm";

import { ecrireEtiquettes, lireEtiquettes } from "./EtiquettesEtape";
import specs from "./specs-premiere-replique.json";

const CHAMPS = ["immatriculation", "kilometrage", "commune_garage"];
const CONTEXTE = { tools: [], documents: [], recordings: [], champsFiche: CHAMPS };
const spec = (specs as Record<string, unknown>).agentNode as NodeSpec;

afterEach(cleanup);

const rendre = (champs_etape: string | undefined, onChange = vi.fn()) => {
    render(
        <NodeEditForm
            spec={spec}
            values={{ name: "Step", prompt: "Ask.", ...(champs_etape ? { champs_etape } : {}) }}
            onChange={onChange}
            context={CONTEXTE}
        />,
    );
    return onChange;
};

describe("[.mark] step field labels", () => {
    it("reads and writes one comma-separated string", () => {
        expect(lireEtiquettes(" a , b ,, ")).toEqual(["a", "b"]);
        expect(lireEtiquettes(undefined)).toEqual([]);
        expect(ecrireEtiquettes(["a", "b"])).toBe("a, b");
    });

    it("offers the record's fields and adds one at the end", () => {
        const onChange = rendre("kilometrage");
        expect(screen.getByText("Step field labels")).toBeTruthy();
        fireEvent.click(screen.getByRole("button", { name: "+ immatriculation" }));
        expect(onChange).toHaveBeenLastCalledWith(
            expect.objectContaining({ champs_etape: "kilometrage, immatriculation" }),
        );
    });

    it("reorders with the arrows and removes", () => {
        const onChange = rendre("immatriculation, kilometrage");
        fireEvent.click(screen.getByRole("button", { name: "Move kilometrage up" }));
        expect(onChange).toHaveBeenLastCalledWith(
            expect.objectContaining({ champs_etape: "kilometrage, immatriculation" }),
        );
        fireEvent.click(screen.getByRole("button", { name: "Remove immatriculation" }));
        expect(onChange).toHaveBeenLastCalledWith(expect.objectContaining({ champs_etape: "kilometrage" }));
    });

    it("says when a label is not a field of the record", () => {
        rendre("immatriculation, couleur");
        expect(screen.getByRole("alert").textContent).toContain("couleur");
    });
});
