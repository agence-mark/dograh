/**
 * [.mark] Partie 3, sous-lot 17b : « Ouvrir son portail » ouvre la route d'entrée du portail (`/api/auth/entree-mark?lien=`) avec le lien
 * « client.jeton » rendu par le fork ; l'adresse du portail vient de l'environnement, sans barre finale.
 */
import { afterEach, describe, expect, it, vi } from "vitest";

afterEach(() => {
    vi.unstubAllEnvs();
    vi.resetModules();
});

describe("[.mark] lien d'entrée dans le portail", () => {
    it("porte la route d'entrée, le client avant le jeton, et encode le lien", async () => {
        vi.stubEnv("NEXT_PUBLIC_PORTAIL_URL", "https://portail.exemple.test/");
        const { lienDEntree } = await import("./commun");
        expect(lienDEntree("41.abc_DEF-123")).toBe("https://portail.exemple.test/api/auth/entree-mark?lien=41.abc_DEF-123");
        expect(lienDEntree("41.a b")).toBe("https://portail.exemple.test/api/auth/entree-mark?lien=41.a%20b");
    });

    it("sans adresse de portail réglée, le lien reste relatif (le bouton est alors désactivé)", async () => {
        vi.stubEnv("NEXT_PUBLIC_PORTAIL_URL", "");
        const { ADRESSE_PORTAIL } = await import("./commun");
        expect(ADRESSE_PORTAIL).toBe("");
    });
});
