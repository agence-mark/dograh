/**
 * [.mark] K8 : les réglages avancés d'une campagne n'ont plus de phrase d'aide visible : chaque explication est dans le
 * « ! » de son champ, et l'interrupteur et son « ! » sont deux éléments distincts.
 */
import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { FournisseurLangue } from "@/components/mark/langue/langue";

vi.mock("react-timezone-select", () => ({ default: () => <div data-testid="fuseau" /> }));

import CampaignAdvancedSettings from "./CampaignAdvancedSettings";

afterEach(() => cleanup());

const rien = () => undefined;

describe("[.mark] K8 : réglages avancés d'une campagne", () => {
    it("aucune note visible, un « ! » par réglage expliqué", () => {
        const { container } = render(
            <FournisseurLangue>
                <CampaignAdvancedSettings
                    maxConcurrency=""
                    onMaxConcurrencyChange={rien}
                    effectiveLimit={4}
                    orgConcurrentLimit={10}
                    fromNumbersCount={2}
                    rateLimitPerSecond="1"
                    onRateLimitPerSecondChange={rien}
                    retryEnabled
                    onRetryEnabledChange={rien}
                    maxRetries="2"
                    onMaxRetriesChange={rien}
                    retryDelaySeconds="120"
                    onRetryDelaySecondsChange={rien}
                    retryOnBusy
                    onRetryOnBusyChange={rien}
                    retryOnNoAnswer
                    onRetryOnNoAnswerChange={rien}
                    retryOnVoicemail={false}
                    onRetryOnVoicemailChange={rien}
                    scheduleEnabled={false}
                    onScheduleEnabledChange={rien}
                    scheduleTimezone="UTC"
                    onScheduleTimezoneChange={rien}
                    timeSlots={[]}
                    onTimeSlotsChange={rien}
                    circuitBreakerEnabled
                    onCircuitBreakerEnabledChange={rien}
                    circuitBreakerFailureThreshold="50"
                    onCircuitBreakerFailureThresholdChange={rien}
                    circuitBreakerWindowSeconds="120"
                    onCircuitBreakerWindowSecondsChange={rien}
                    circuitBreakerMinCalls="5"
                    onCircuitBreakerMinCallsChange={rien}
                />
            </FournisseurLangue>,
        );
        const texte = container.textContent ?? "";
        expect(texte).not.toMatch(/Maximum number of simultaneous calls|Automatically retry failed calls|Restrict when calls are made|Auto-pause campaign|Pause when failure rate/);
        // Six réglages expliqués : appels simultanés, cadence, tentatives, plages, coupe-circuit, seuil.
        expect(screen.getAllByRole("button", { name: "Précision" }).length).toBe(6);
        // L'interrupteur reste un contrôle à part : le « ! » n'est pas dans son étiquette.
        const etiquette = container.querySelector('label[for="retry-enabled"]');
        expect(etiquette?.querySelector('[role="button"]')).toBeNull();
    });
});
