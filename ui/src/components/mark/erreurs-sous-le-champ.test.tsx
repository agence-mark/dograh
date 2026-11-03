/**
 * [.mark] Une erreur de saisie se lit sous le champ, jamais dans une notification (`15-notifications.md`, règle 5).
 * Deux endroits la portent : la fenêtre à champs (`verifier`) et les réglages avancés d'une campagne (`erreurs`).
 */
import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import CampaignAdvancedSettings from "@/app/campaigns/CampaignAdvancedSettings";
import { lireNotifications, viderNotifications } from "@/components/mark/notifications";

import { FournisseurLangue } from "./langue/langue";
import { FenetreChamps } from "./studio/fenetre-champs";

beforeEach(() => viderNotifications());
afterEach(cleanup);

const fenetre = (onValider: () => void) => (
    <FournisseurLangue>
        <FenetreChamps
            ouverte
            fermer={() => {}}
            titre="Nouvelle famille"
            valider="Créer"
            onValider={onValider}
            verifier={(v) => (String(v.nom).trim() ? null : { nom: "Donnez un nom." })}
            sections={[{ champs: [{ id: "nom", t: "texte", l: "Nom" }] }]}
        />
    </FournisseurLangue>
);

describe("fenêtre à champs : la vérification parle sous le champ", () => {
    it("garde la fenêtre ouverte, ne valide pas et n'envoie aucune notification", () => {
        const onValider = vi.fn();
        render(fenetre(onValider));
        fireEvent.click(screen.getByText("Créer"));
        expect(screen.getByRole("alert").textContent).toBe("Donnez un nom.");
        expect(screen.getByLabelText("Nom").getAttribute("aria-invalid")).toBe("true");
        expect(onValider).not.toHaveBeenCalled();
        expect(lireNotifications()).toHaveLength(0);
    });

    it("efface la faute dès que le champ change, puis valide", () => {
        const onValider = vi.fn();
        render(fenetre(onValider));
        fireEvent.click(screen.getByText("Créer"));
        fireEvent.change(screen.getByLabelText("Nom"), { target: { value: "Accueil" } });
        expect(screen.queryByRole("alert")).toBeNull();
        fireEvent.click(screen.getByText("Créer"));
        expect(onValider).toHaveBeenCalledTimes(1);
    });
});

describe("réglages avancés d'une campagne : les fautes sous leur champ", () => {
    const props = {
        maxConcurrency: "99", onMaxConcurrencyChange: () => {}, effectiveLimit: 5, orgConcurrentLimit: 5, fromNumbersCount: 0,
        rateLimitPerSecond: "9", onRateLimitPerSecondChange: () => {},
        retryEnabled: false, onRetryEnabledChange: () => {}, maxRetries: "2", onMaxRetriesChange: () => {},
        retryDelaySeconds: "120", onRetryDelaySecondsChange: () => {},
        retryOnBusy: true, onRetryOnBusyChange: () => {}, retryOnNoAnswer: true, onRetryOnNoAnswerChange: () => {},
        retryOnVoicemail: true, onRetryOnVoicemailChange: () => {},
        scheduleEnabled: false, onScheduleEnabledChange: () => {}, scheduleTimezone: "Europe/Paris", onScheduleTimezoneChange: () => {},
        timeSlots: [], onTimeSlotsChange: () => {},
        circuitBreakerEnabled: false, onCircuitBreakerEnabledChange: () => {},
        circuitBreakerFailureThreshold: "5", onCircuitBreakerFailureThresholdChange: () => {},
        circuitBreakerWindowSeconds: "60", onCircuitBreakerWindowSecondsChange: () => {},
        circuitBreakerMinCalls: "3", onCircuitBreakerMinCallsChange: () => {},
    };

    it("lit la faute des appels simultanés et celle de la cadence sous leur champ", () => {
        render(
            <CampaignAdvancedSettings
                {...props}
                erreurs={{ simultanes: "Appels simultanés : entre 1 et 5.", cadence: "Appels par seconde : entre 1 et 5." }}
            />,
        );
        const alertes = screen.getAllByRole("alert").map((a) => a.textContent);
        expect(alertes).toEqual(["Appels simultanés : entre 1 et 5.", "Appels par seconde : entre 1 et 5."]);
        expect(document.getElementById("max-concurrency")?.getAttribute("aria-invalid")).toBe("true");
        expect(document.getElementById("dial-rate")?.getAttribute("aria-describedby")).toBe("dial-rate-erreur");
    });

    it("n'affiche rien sans faute", () => {
        render(<CampaignAdvancedSettings {...props} />);
        expect(screen.queryByRole("alert")).toBeNull();
    });
});
