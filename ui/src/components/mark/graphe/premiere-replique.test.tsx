/**
 * [.mark] The "First reply" field, as seen in a step's window of the graph
 * (plan porte-parlee, lot 2, D2).
 *
 * ⛔ This file RENDERS the node's edit form (the same `NodeEditForm` the graph
 * opens), fed with the specs the server serves at `/node-types`. The fixture is
 * checked against the server by `api/tests/mark/test_porte_parlee_premiere_replique.py`,
 * so this test cannot prove a screen that does not exist.
 *
 * The graph editor is never translated (convention T3): the field reads in
 * English like every other field of a node.
 */
import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import type { NodeSpec } from "@/client/types.gen";
import { NodeEditForm } from "@/components/flow/renderer/NodeEditForm";

import { etapesSansPremiereReplique } from "./premiere-replique";
import specs from "./specs-premiere-replique.json";

const CONTEXTE = { tools: [], documents: [], recordings: [] };

afterEach(cleanup);

describe.each(["agentNode", "endCall"] as const)("[.mark] first reply on %s", (type) => {
    const spec = (specs as Record<string, unknown>)[type] as NodeSpec;

    it("shows the field right after the prompt, with its help", () => {
        const { container } = render(
            <NodeEditForm spec={spec} values={{ name: "Step", prompt: "Ask." }} onChange={() => {}} context={CONTEXTE} />,
        );
        expect(screen.getByText("First reply")).toBeTruthy();
        expect(screen.getByText(/Used only when "Transitions in the reply" is on/)).toBeTruthy();
        const textes = container.textContent ?? "";
        expect(textes.indexOf("Prompt")).toBeLessThan(textes.indexOf("First reply"));
    });

    it("sends what is typed under premiere_replique, and keeps the other values", () => {
        const onChange = vi.fn();
        render(
            <NodeEditForm
                spec={spec}
                values={{ name: "Step", prompt: "Ask.", premiere_replique: "" }}
                onChange={onChange}
                context={CONTEXTE}
            />,
        );
        const zones = screen.getAllByRole("textbox");
        const zone = zones.find((z) => (z as HTMLTextAreaElement).value === "" && z.tagName === "TEXTAREA");
        expect(zone).toBeTruthy();
        fireEvent.change(zone!, { target: { value: "Quelle marque ?" } });
        expect(onChange).toHaveBeenCalledWith({ name: "Step", prompt: "Ask.", premiere_replique: "Quelle marque ?" });
    });
});

// The same rule as `etapes_sans_premiere_replique` (Python), on the graph of
// `test_porte_parlee_premiere_replique.py` (convention E8).
describe("[.mark] steps without a first reply", () => {
    const graphe = (etape?: string | null, fin?: string | null) => ({
        nodes: [
            { id: "start", type: "startCall", data: { name: "Start" } },
            { id: "etape", type: "agentNode", data: { name: "Etape", premiere_replique: etape } },
            { id: "end", type: "endCall", data: { name: "End", premiere_replique: fin } },
        ],
        edges: [{ target: "end" }, { target: "etape" }, { target: "end" }],
    });

    it("lists the steps a transition leads to, never the greeting, as the server does", () => {
        expect(etapesSansPremiereReplique(graphe())).toEqual(["Etape", "End"]);
        expect(etapesSansPremiereReplique(graphe("Quelle marque ?", "   "))).toEqual(["End"]);
        expect(etapesSansPremiereReplique(graphe("Quelle marque ?", "Au revoir."))).toEqual([]);
        expect(etapesSansPremiereReplique(null)).toEqual([]);
    });
});
