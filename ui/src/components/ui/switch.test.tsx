/**
 * [.mark] SE-2 (Q-1, 04/11) : un interrupteur allumé est sombre, comme la maquette (jeton `primary`, jamais l'accent bleu).
 */
import { cleanup, render } from "@testing-library/react";
import { afterEach, describe, expect, it } from "vitest";

import { Switch } from "./switch";

afterEach(cleanup);

describe("interrupteur", () => {
    it("allumé : fond du jeton primary (sombre en clair), pastille lisible en sombre", () => {
        const { container } = render(<Switch checked aria-label="essai" onCheckedChange={() => {}} />);
        const racine = container.querySelector("[data-slot='switch']")!;
        expect(racine.getAttribute("data-state")).toBe("checked");
        expect(racine.className).toContain("data-[state=checked]:bg-primary");
        expect(racine.className).not.toContain("acc-fill");
        const pastille = container.querySelector("[data-slot='switch-thumb']")!;
        expect(pastille.className).toContain("dark:data-[state=checked]:bg-primary-foreground");
    });
});
