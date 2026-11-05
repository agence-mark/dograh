/** [.mark] SA-V : le libellé d'un interrupteur d'étape se clique (il bascule l'interrupteur) : curseur main, règle de l'écran. */
import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it } from "vitest";

import { PropertyInput } from "./PropertyInput";

afterEach(cleanup);

describe("libellé d'un interrupteur d'étape", () => {
    it("a le curseur main", () => {
        render(
            <PropertyInput
                spec={{ name: "allow_interrupt", type: "boolean", display_name: "Interrupt allowed", description: "" } as never}
                value={true}
                onChange={() => undefined}
                context={{ tools: [], documents: [], recordings: [] }}
            />,
        );
        expect(screen.getByText("Interrupt allowed").closest("label")?.className).toContain("cursor-pointer");
    });
});
