/**
 * [.mark] Constat 7 de cloture-code-avant-migration : le widget de messagerie de Dograh (Chatwoot) est retiré de
 * l'image de l'écran (`ui/Dockerfile` ne pose plus les deux variables `NEXT_PUBLIC_CHATWOOT_*`).
 *
 * | Test | La garantie |
 * |---|---|
 * | sans jeton | aucun script n'est ajouté à la page, aucun `window.chatwootSettings`, et ni `console.warn` ni `console.error` |
 * | avec jeton | (témoin) le script du widget est bien ajouté : le test ne passe pas parce que le composant ne ferait rien |
 */
import { cleanup, render } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

vi.mock("next/navigation", () => ({ usePathname: () => "/workflow" }));

const monter = async () => {
    vi.resetModules();
    const { default: ChatwootWidget } = await import("./ChatwootWidget");
    return render(<ChatwootWidget />);
};

beforeEach(() => {
    delete (window as { chatwootSettings?: unknown }).chatwootSettings;
    document.querySelectorAll("script").forEach((s) => s.remove());
});
afterEach(() => {
    cleanup();
    vi.unstubAllEnvs();
    vi.restoreAllMocks();
});

describe("[.mark] widget Chatwoot", () => {
    it("sans jeton : aucun widget ne se charge et rien n'est écrit dans la console", async () => {
        vi.stubEnv("NEXT_PUBLIC_CHATWOOT_URL", "");
        vi.stubEnv("NEXT_PUBLIC_CHATWOOT_TOKEN", "");
        const avertir = vi.spyOn(console, "warn").mockImplementation(() => {});
        const erreur = vi.spyOn(console, "error").mockImplementation(() => {});
        await monter();
        expect(document.querySelector('script[src*="sdk.js"]')).toBeNull();
        expect(window.chatwootSettings).toBeUndefined();
        expect(avertir).not.toHaveBeenCalled();
        expect(erreur).not.toHaveBeenCalled();
    });

    it("témoin : avec une adresse et un jeton, le script du widget est ajouté", async () => {
        vi.stubEnv("NEXT_PUBLIC_CHATWOOT_URL", "https://messagerie.example.org");
        vi.stubEnv("NEXT_PUBLIC_CHATWOOT_TOKEN", "jeton-d-essai");
        await monter();
        expect(document.querySelector('script[src="https://messagerie.example.org/packs/js/sdk.js"]')).not.toBeNull();
    });
});
