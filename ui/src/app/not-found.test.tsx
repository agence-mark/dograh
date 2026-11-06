/** [.mark] Page introuvable (N4) : texte aux jetons, deux langues, lien de retour. */
import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it } from "vitest";

import { FournisseurLangue } from "@/components/mark/langue/langue";

import NotFound from "./not-found";

afterEach(() => {
    cleanup();
    window.localStorage.clear();
});

describe("page introuvable (N4)", () => {
    it("dit « Page introuvable » en français, avec un lien d'accueil, sans style en ligne", () => {
        const { container } = render(
            <FournisseurLangue>
                <NotFound />
            </FournisseurLangue>,
        );
        expect(screen.getByText("Page introuvable")).toBeTruthy();
        expect(screen.getByRole("link", { name: "Revenir à l'accueil" }).getAttribute("href")).toBe("/");
        expect(container.innerHTML).not.toMatch(/style=|#[0-9a-f]{3,6}\b/i);
    });
});
