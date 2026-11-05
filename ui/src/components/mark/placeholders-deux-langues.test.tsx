/**
 * [.mark] SA-V : les exemples grisés (placeholders) de la section « Tour de parole » suivent la langue de l'écran.
 * Avant, ils restaient en anglais en français (« Provider value (0.35 s for Deepgram) », rogné à « Provid… » dans le champ).
 */
import { cleanup, render } from "@testing-library/react";
import { afterEach, describe, expect, it } from "vitest";

import { FournisseurLangue } from "./langue/langue";
import { type ReglagesTourDeParole, SectionTourDeParole } from "./SectionTourDeParole";

afterEach(() => {
    cleanup();
    try { window.localStorage.clear(); } catch { /* sans stockage, la langue par défaut est le français */ }
});

const REGLAGES: ReglagesTourDeParole = {
    user_speech_timeout: 0.6, stt_ttfs_p99_latency: null, user_turn_stop_timeout: null, turn_wait_for_transcript: true,
    turn_start_use_interim: true, vad_confidence: 0.7, vad_start_secs: 0.2, vad_stop_secs: 0.2, vad_min_volume: 0.6,
    smart_turn_pre_speech_ms: 500, smart_turn_max_duration_secs: 8, audio_idle_timeout: 1, filter_incomplete_user_turns: false,
    incomplete_short_timeout: 5, incomplete_long_timeout: 10, audio_in_noise_filter: "none",
};

describe("exemples grisés de Tour de parole", () => {
    it("en français : aucun exemple en anglais", () => {
        const { container } = render(
            <FournisseurLangue>
                <SectionTourDeParole reglages={REGLAGES} onChange={() => undefined} tourPiloteAilleurs={false} smartTurnActif={false} />
            </FournisseurLangue>,
        );
        const exemples = [...container.querySelectorAll("input[placeholder]")].map((e) => e.getAttribute("placeholder") ?? "");
        expect(exemples.some((p) => p.startsWith("Valeur du fournisseur"))).toBe(true);
        expect(exemples.some((p) => /Provider value|when the transcription drives/.test(p))).toBe(false);
    });
});
