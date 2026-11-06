/**
 * [.mark] L (fluidité) : le changement de page montre une attente à l'instant (jamais un écran blanc), et l'éditeur
 * d'un agent, la page la plus lourde, a sa propre limite de chargement (ce que Next précharge avec le lien).
 */
import { cleanup, render, screen } from "@testing-library/react";
import { existsSync } from "node:fs";
import { join } from "node:path";
import { afterEach, describe, expect, it } from "vitest";

import { FournisseurLangue } from "@/components/mark/langue/langue";

import Loading from "./loading";

afterEach(cleanup);

describe("états de chargement des pages", () => {
    it("le chargement par défaut affiche une attente, pas un écran blanc", () => {
        const { container } = render(
            <FournisseurLangue>
                <Loading />
            </FournisseurLangue>,
        );
        expect(container.querySelector("[aria-busy=true]")).not.toBeNull();
        expect(screen.getByLabelText("Chargement")).toBeTruthy();
    });

    it("l'éditeur d'un agent a sa limite de chargement", () => {
        expect(existsSync(join(__dirname, "agents", "[workflowId]", "loading.tsx"))).toBe(true);
    });
});
