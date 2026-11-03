/**
 * [.mark] La fenêtre d'un service (U3, E35).
 *
 * Questions de ce fichier :
 *
 *     La fenêtre monte-t-elle le formulaire des fournisseurs sur UN seul service, en mode « global » pour
 *     l'organisation et « remplacement » pour l'agent ? « Tester la connexion » dit-il ce que le fork répond, sans
 *     rien écrire ? Aucun appel à un fournisseur : la vérification du fork est simulée.
 */
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { FenetreService } from "./FenetreService";

const m = vi.hoisted(() => ({ valider: vi.fn(), formulaire: vi.fn() }));
vi.mock("@/client/sdk.gen", () => ({ validateUserConfigurationsApiV1UserConfigurationsUserValidateGet: m.valider }));
vi.mock("@/components/ServiceConfigurationForm", () => ({
    ServiceConfigurationForm: (props: Record<string, unknown>) => {
        m.formulaire(props);
        return <div data-testid="formulaire" />;
    },
}));

beforeEach(() => {
    m.valider.mockReset();
    m.formulaire.mockReset();
});
afterEach(cleanup);

const monter = (surcharge: Partial<React.ComponentProps<typeof FenetreService>> = {}) =>
    render(<FenetreService service="llm" portee="organisation" fermer={vi.fn()} enregistrer={vi.fn()} {...(surcharge as object)} />);

describe("le formulaire monté", () => {
    it("pour l'organisation : un seul service, en mode global, sans le choix temps réel de l'écran entier", () => {
        monter({ service: "tts" });
        const props = m.formulaire.mock.calls.at(-1)![0];
        expect(props).toMatchObject({ mode: "global", segments: ["tts"], forceRealtime: false });
        expect(screen.getByRole("dialog").textContent).toContain("Voice");
    });

    it("pour l'agent : le mode remplacement, avec ce que l'agent remplace déjà", () => {
        const remplacements = { tts: { provider: "cartesia" } } as never;
        monter({ service: "tts", portee: "agent", remplacementsAgent: remplacements });
        expect(m.formulaire.mock.calls.at(-1)![0]).toMatchObject({ mode: "override", segments: ["tts"], currentOverrides: remplacements });
    });

    it("le temps réel verrouille le mode temps réel", () => {
        monter({ service: "realtime" });
        expect(m.formulaire.mock.calls.at(-1)![0]).toMatchObject({ segments: ["realtime"], forceRealtime: true });
    });

    it("transmet l'enregistrement du formulaire à l'appelant", async () => {
        const enregistrer = vi.fn(async () => undefined);
        monter({ enregistrer });
        await (m.formulaire.mock.calls.at(-1)![0].onSave as (c: Record<string, unknown>) => Promise<void>)({ llm: { provider: "mistral" } });
        expect(enregistrer).toHaveBeenCalledWith({ llm: { provider: "mistral" } });
    });
});

describe("« Tester la connexion »", () => {
    it("ne vérifie rien tant qu'on n'a pas cliqué", () => {
        monter();
        expect(m.valider).not.toHaveBeenCalled();
    });

    it("force la vérification (TTL 0) et dit que la connexion fonctionne quand le fork ne refuse rien", async () => {
        m.valider.mockResolvedValue({ data: { status: [] } });
        monter();
        fireEvent.click(screen.getByRole("button", { name: "Test the connection" }));
        await waitFor(() => expect(document.querySelector('[data-essai="ok"]')).not.toBeNull());
        expect(m.valider).toHaveBeenCalledWith({ query: { validity_ttl_seconds: 0 } });
    });

    it("rapporte le refus du fork pour CE service, et ignore le refus d'un autre", async () => {
        m.valider.mockResolvedValue({ data: { status: [{ model: "tts", message: "Clé refusée" }] } });
        monter({ service: "llm" });
        fireEvent.click(screen.getByRole("button", { name: "Test the connection" }));
        await waitFor(() => expect(document.querySelector('[data-essai="ok"]')).not.toBeNull());
        cleanup();
        monter({ service: "tts" });
        fireEvent.click(screen.getByRole("button", { name: "Test the connection" }));
        await waitFor(() => expect(document.querySelector('[data-essai="echec"]')?.textContent).toBe("Clé refusée"));
    });

    it("rapporte une erreur du serveur au lieu d'afficher une réussite", async () => {
        m.valider.mockResolvedValue({ error: { detail: "Mistral: invalid key" } });
        monter();
        fireEvent.click(screen.getByRole("button", { name: "Test the connection" }));
        await waitFor(() => expect(document.querySelector('[data-essai="echec"]')?.textContent).toContain("Mistral: invalid key"));
        expect(document.querySelector('[data-essai="ok"]')).toBeNull();
    });
});
