/**
 * [.mark] `notifier` et la zone d'affichage : boutons (Annuler, Réessayer, Publier), « Détails » pour l'équipe seulement,
 * jamais le texte brut du serveur, `aria-live`, fermeture au clavier.
 */
import { act, cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

const sdk = vi.hoisted(() => ({ publier: vi.fn() }));
vi.mock("@/client/sdk.gen", () => ({ publishWorkflowApiV1WorkflowWorkflowIdPublishPost: sdk.publier }));

import { definirLabo } from "@/lib/espaceCourant";

import { lireNotifications, viderNotifications } from "./magasin";
import { declarerAgentCourant, notifier } from "./notifier";
import { ZoneNotifications } from "./ZoneNotifications";

beforeEach(() => {
    vi.useFakeTimers();
    viderNotifications();
    definirLabo(null);
    declarerAgentCourant(null);
    sdk.publier.mockReset();
});
afterEach(() => {
    cleanup();
    viderNotifications();
    vi.useRealTimers();
});

const textes = () => lireNotifications().map((n) => n.texte.en);

describe("Annuler : suppression différée de 5 s", () => {
    it("n'exécute rien avant 5 s, puis exécute", () => {
        const executer = vi.fn();
        notifier.annulable({ fr: "Supprimé.", en: "Deleted." }, { executer });
        vi.advanceTimersByTime(4999);
        expect(executer).not.toHaveBeenCalled();
        vi.advanceTimersByTime(1);
        expect(executer).toHaveBeenCalledTimes(1);
    });

    it("« Annuler » empêche l'exécution, restaure, et le dit", () => {
        const executer = vi.fn();
        const restaurer = vi.fn();
        notifier.annulable({ fr: "Supprimé.", en: "Deleted." }, { executer, restaurer });
        render(<ZoneNotifications />);
        fireEvent.click(screen.getByRole("button", { name: "Undo" }));
        expect(textes()).toEqual(["Action undone."]);
        vi.advanceTimersByTime(10_000);
        expect(executer).not.toHaveBeenCalled();
        expect(restaurer).toHaveBeenCalledTimes(1);
    });

    it("fermer la notification avant 5 s n'annule pas la suppression", () => {
        const executer = vi.fn();
        const cle = notifier.annulable({ fr: "Supprimé.", en: "Deleted." }, { executer });
        render(<ZoneNotifications />);
        expect(lireNotifications().some((n) => n.cle === cle)).toBe(true);
        fireEvent.click(screen.getByRole("button", { name: "Close" }));
        vi.advanceTimersByTime(5000);
        expect(executer).toHaveBeenCalledTimes(1);
    });

    it("la notification reste 5 s, le temps de pouvoir annuler", () => {
        notifier.annulable({ fr: "Supprimé.", en: "Deleted." }, { executer: vi.fn() });
        vi.advanceTimersByTime(4500);
        expect(lireNotifications().some((n) => n.bouton)).toBe(true);
    });
});

describe("Réessayer", () => {
    it("le bouton rappelle l'action et ferme la notification", () => {
        const reessayer = vi.fn();
        notifier.echec({ fr: "Envoi impossible.", en: "Could not send." }, { reessayer });
        render(<ZoneNotifications />);
        fireEvent.click(screen.getByRole("button", { name: "Retry" }));
        expect(reessayer).toHaveBeenCalledTimes(1);
        expect(lireNotifications()).toHaveLength(0);
    });
});

describe("Publier", () => {
    it("sans agent connu, la phrase de rappel garde le rôle du bouton", () => {
        notifier.succes({ fr: "Réglages enregistrés.", en: "Settings saved." }, { publier: true });
        expect(lireNotifications()[0].bouton).toBeUndefined();
        expect(textes()).toEqual(["Settings saved. Publish the agent to apply."]);
    });

    it("avec l'agent de l'écran, un bouton « Publier » publie, puis annonce le résultat dans la même fenêtre", async () => {
        vi.useRealTimers();
        sdk.publier.mockResolvedValue({ data: {}, error: undefined });
        declarerAgentCourant(12);
        notifier.succes({ fr: "Réglages enregistrés.", en: "Settings saved." }, { publier: true });
        render(<ZoneNotifications />);
        await act(async () => {
            fireEvent.click(screen.getByRole("button", { name: "Publish" }));
        });
        expect(sdk.publier).toHaveBeenCalledWith({ path: { workflow_id: 12 } });
        expect(textes()).toEqual(["Agent published."]);
    });

    it("un échec de publication propose « Réessayer »", async () => {
        vi.useRealTimers();
        sdk.publier.mockResolvedValue({ data: undefined, error: { detail: "boom" } });
        declarerAgentCourant(12);
        notifier.succes({ fr: "Réglages enregistrés.", en: "Settings saved." }, { publier: true });
        render(<ZoneNotifications />);
        await act(async () => {
            fireEvent.click(screen.getByRole("button", { name: "Publish" }));
        });
        expect(textes()).toEqual(["Could not publish. Try again."]);
        expect(screen.getByRole("button", { name: "Retry" })).toBeTruthy();
    });
});

describe("Détails : le motif du serveur", () => {
    it("jamais montré à un client, même replié", () => {
        notifier.echec({ fr: "Agent non créé. Réessayez.", en: "Agent not created. Try again." }, { erreur: { detail: "IntegrityError: duplicate key" } });
        render(<ZoneNotifications />);
        expect(screen.queryByText(/IntegrityError/)).toBeNull();
        expect(screen.queryByRole("button", { name: "Details" })).toBeNull();
    });

    it("pour l'équipe : une ligne « Détails » repliée, qui s'ouvre", () => {
        definirLabo(1);
        notifier.echec({ fr: "Agent non créé. Réessayez.", en: "Agent not created. Try again." }, { erreur: { detail: "IntegrityError: duplicate key" } });
        render(<ZoneNotifications />);
        expect(screen.queryByText(/IntegrityError/)).toBeNull();
        fireEvent.click(screen.getByRole("button", { name: "Details" }));
        expect(screen.getByText("IntegrityError: duplicate key")).toBeTruthy();
    });

    it("lit une Error, un texte ou la réponse du client d'API", () => {
        notifier.echec({ fr: "a", en: "a" }, { erreur: new Error("réseau coupé") });
        notifier.echec({ fr: "b", en: "b" }, { erreur: "texte" });
        notifier.echec({ fr: "c", en: "c" }, { erreur: { detail: [{ msg: "champ requis" }] } });
        expect(lireNotifications().map((n) => n.detail)).toEqual(["réseau coupé", "texte", "champ requis"]);
    });
});

describe("accessibilité", () => {
    it("la zone est une région aria-live polie ; l'échec est annoncé tout de suite (role=alert)", () => {
        notifier.succes({ fr: "Fait.", en: "Done." });
        notifier.echec({ fr: "Raté.", en: "Failed." });
        const { container } = render(<ZoneNotifications />);
        expect(container.querySelector('[aria-live="polite"]')).toBeTruthy();
        expect(screen.getByRole("alert").textContent).toContain("Failed.");
        expect(screen.getByRole("status").textContent).toContain("Done.");
    });

    it("la minuterie s'arrête au survol et au focus", () => {
        notifier.succes({ fr: "Fait.", en: "Done." });
        render(<ZoneNotifications />);
        const carte = screen.getByRole("status");
        fireEvent.mouseEnter(carte);
        vi.advanceTimersByTime(30_000);
        expect(lireNotifications()).toHaveLength(1);
        fireEvent.mouseLeave(carte);
        act(() => {
            vi.advanceTimersByTime(4000);
        });
        expect(lireNotifications()).toHaveLength(0);
    });

    it("Échap ferme la notification qui a le focus", () => {
        notifier.echec({ fr: "Raté.", en: "Failed." });
        render(<ZoneNotifications />);
        fireEvent.keyDown(screen.getByRole("alert"), { key: "Escape" });
        expect(lireNotifications()).toHaveLength(0);
    });
});

describe("en cours puis résultat", () => {
    it("une seule fenêtre qui change d'état", () => {
        const cours = notifier.enCours({ fr: "Envoi…", en: "Uploading…" });
        expect(lireNotifications()).toHaveLength(1);
        cours.succes({ fr: "Envoyé.", en: "Sent." });
        expect(textes()).toEqual(["Sent."]);
        expect(lireNotifications()[0].sorte).toBe("succes");
    });

    it("suivre : échec d'une réponse refusée (le client d'API ne lève pas d'exception)", async () => {
        vi.useRealTimers();
        notifier.suivre(Promise.resolve({ error: { detail: "non" } }), {
            encours: { fr: "…", en: "…" },
            succes: { fr: "ok", en: "ok" },
            echec: { fr: "ko", en: "ko" },
            echecSi: (r) => r.error,
        });
        await act(async () => {
            await Promise.resolve();
        });
        expect(textes()).toEqual(["ko"]);
        expect(lireNotifications()[0].detail).toBe("non");
    });
});

describe("langue", () => {
    it("sans fournisseur de langue, la zone affiche l'anglais (comme tout l'écran dans les tests)", () => {
        notifier.succes({ fr: "Fait.", en: "Done." });
        render(<ZoneNotifications />);
        expect(screen.getByText("Done.")).toBeTruthy();
    });
});
