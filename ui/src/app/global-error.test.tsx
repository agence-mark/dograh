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
    // Q-4 : la page est autonome en clair comme en sombre : le script de l'en-tête pose « dark » avant le premier rendu, les couleurs
    // viennent des jetons (aucune couleur en dur : le texte n'est plus « noir en dur »).
    it("Q-4 : son script d'en-tête passe la page en sombre quand le thème choisi l'est, et elle n'a aucune couleur en dur", async () => {
        const { renderToStaticMarkup } = await import("react-dom/server");
        const html = renderToStaticMarkup(<GlobalError error={new Error("x")} reset={() => {}} />);
        const script = /<script>([\s\S]*?)<\/script>/.exec(html)?.[1];
        expect(script).toBeTruthy();
        window.localStorage.setItem("theme", "dark");
        document.documentElement.classList.remove("dark");
        new Function(script!.replace(/&#x27;/g, "'").replace(/&quot;/g, '"'))();
        expect(document.documentElement.classList.contains("dark")).toBe(true);
        window.localStorage.setItem("theme", "light");
        document.documentElement.classList.remove("dark");
        new Function(script!.replace(/&#x27;/g, "'").replace(/&quot;/g, '"'))();
        expect(document.documentElement.classList.contains("dark")).toBe(false);
        expect(html).not.toMatch(/#[0-9a-fA-F]{3,6}|rgb\(|text-black|bg-white/);
        expect(html).toContain("bg-background");
    });
});
