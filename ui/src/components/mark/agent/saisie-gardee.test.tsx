/**
 * [.mark] K6 (gestes sûrs) : une modification de l'agent ailleurs ne remonte pas l'onglet quand il porte une saisie non
 * enregistrée ; elle la garde, prévient, et recharge sur demande. Sans saisie, l'onglet se relit seul comme avant.
 */
import { act, cleanup, fireEvent, render, screen } from "@testing-library/react";
import { useState } from "react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { useBrouillonLocal } from "./brouillon-local";
import { EntetePageAgent } from "./EntetePageAgent";

const m = vi.hoisted(() => ({ declencher: null as null | (() => void), montages: 0 }));

vi.mock("@/lib/auth", () => ({ useAuth: () => ({ user: { id: 1 }, loading: false }) }));
vi.mock("@/client/sdk.gen", () => ({
    lireLesTestsApiV1BuilderTestsWorkflowIdGet: vi.fn(async () => ({ data: { tests: [] } })),
    getWorkflowApiV1WorkflowFetchWorkflowIdGet: async () => ({ data: { name: "Agent", workflow_uuid: "u", version_number: 1, version_status: "draft" } }),
}));
vi.mock("./ActionsAgent", () => ({ ActionsAgent: () => null }));
vi.mock("./EnteteAgent", () => ({ EnteteAgent: () => null }));
vi.mock("@/components/mark/sources/useModifications", () => ({
    LigneLive: ({ quand }: { quand?: () => void }) => {
        m.declencher = () => quand?.();
        return null;
    },
}));

function Onglet({ sale }: { sale: boolean }) {
    useBrouillonLocal(sale);
    const [saisie, setSaisie] = useState("");
    m.montages += 1;
    return <input aria-label="champ" value={saisie} onChange={(e) => setSaisie(e.target.value)} />;
}

afterEach(() => {
    cleanup();
    m.montages = 0;
});

const ecrireAilleurs = () => {
    // la saisie est faite avant l'écriture distante
    fireEvent.change(screen.getByLabelText("champ"), { target: { value: "ma saisie" } });
    act(() => m.declencher?.());
};

describe("saisie gardée quand l'agent change ailleurs", () => {
    it("garde la saisie, prévient, et ne recharge que sur demande", async () => {
        render(
            <EntetePageAgent agentId={1} onglet="reglages">
                <Onglet sale />
            </EntetePageAgent>,
        );
        ecrireAilleurs();
        expect((screen.getByLabelText("champ") as HTMLInputElement).value).toBe("ma saisie");
        expect(await screen.findByRole("status")).toBeTruthy();
        fireEvent.click(screen.getByRole("button", { name: /Recharger|Reload/ }));
        expect((screen.getByLabelText("champ") as HTMLInputElement).value).toBe("");
        expect(screen.queryByRole("status")).toBeNull();
    });

    it("sans saisie non enregistrée, l'onglet se relit seul", () => {
        render(
            <EntetePageAgent agentId={1} onglet="reglages">
                <Onglet sale={false} />
            </EntetePageAgent>,
        );
        ecrireAilleurs();
        expect((screen.getByLabelText("champ") as HTMLInputElement).value).toBe("");
        expect(screen.queryByRole("status")).toBeNull();
    });
});
