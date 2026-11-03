/** [.mark] Erreur racine (V2) : texte aux jetons, deux langues, jamais le texte de l'erreur. */
import { act } from "react";
import { createRoot } from "react-dom/client";
import { afterEach, describe, expect, it, vi } from "vitest";

import GlobalError from "./global-error";

vi.mock("@sentry/nextjs", () => ({ captureException: vi.fn() }));
vi.mock("./globals.css", () => ({}));
vi.mock("./mark-theme.css", () => ({}));

afterEach(() => {
    window.localStorage.clear();
    document.body.innerHTML = "";
});

const monter = async (langue?: string) => {
    if (langue) window.localStorage.setItem("mark.langue", langue);
    const hote = document.createElement("div");
    document.body.appendChild(hote);
    const racine = createRoot(hote);
    // `GlobalError` rend <html> : on lit son contenu rendu, hors du document de test.
    await act(async () => racine.render(<GlobalError error={new Error("secret interne SQL")} reset={() => {}} />));
    return hote;
};

describe("erreur racine (V2)", () => {
    it("dit l'erreur en français, propose de réessayer et n'affiche pas le texte de l'erreur", async () => {
        const hote = await monter();
        expect(hote.textContent).toContain("Quelque chose s'est mal passé");
        expect(hote.textContent).toContain("Réessayer");
        expect(hote.textContent).not.toContain("secret interne");
    });
    it("suit la langue choisie", async () => {
        const hote = await monter("en");
        expect(hote.textContent).toContain("This page ran into a problem");
    });
});
