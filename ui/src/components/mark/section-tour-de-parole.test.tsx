/**
 * [.mark] The turn-taking section of an agent's configuration, as seen on screen.
 *
 * The questions this file answers:
 *
 *     Are the fields rendered with the values the pipeline actually runs with,
 *     does the section disappear where these settings play no part, and does
 *     an empty transcription-latency field mean "the provider's value" rather
 *     than zero?
 *
 * ⛔ It RENDERS the component. A field declared in a Pydantic schema is not a
 * field on screen.
 */

import { fireEvent, render } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import {
    type ReglagesTourDeParole,
    SectionTourDeParole,
} from "./SectionTourDeParole";
import {
    transcriptionEffective,
    transcriptionPiloteLesTours,
} from "./transcriptionPiloteLesTours";

// ⛔ The values the pipeline ran with BEFORE the patch, as literals.
const REGLAGES_AUJOURDHUI: ReglagesTourDeParole = {
    user_speech_timeout: 0.6,
    stt_ttfs_p99_latency: null,
    user_turn_stop_timeout: 5,
    turn_wait_for_transcript: true,
    turn_start_use_interim: true,
    vad_confidence: 0.7,
    vad_start_secs: 0.2,
    vad_stop_secs: 0.2,
    vad_min_volume: 0.6,
    smart_turn_pre_speech_ms: 500,
    smart_turn_max_duration_secs: 8,
    audio_idle_timeout: 1,
    filter_incomplete_user_turns: false,
    incomplete_short_timeout: 5,
    incomplete_long_timeout: 10,
};

const afficher = (
    reglages: Partial<ReglagesTourDeParole> = {},
    {
        tourPiloteAilleurs = false,
        smartTurnActif = false,
        onChange = vi.fn(),
    } = {},
) => {
    render(
        <SectionTourDeParole
            reglages={{ ...REGLAGES_AUJOURDHUI, ...reglages }}
            onChange={onChange}
            tourPiloteAilleurs={tourPiloteAilleurs}
            smartTurnActif={smartTurnActif}
        />,
    );
    return onChange;
};

const champ = (id: string) => document.getElementById(id) as HTMLInputElement;

describe("Section Tour de parole", () => {
    it("affiche les valeurs d'aujourd'hui, pas des champs vides", () => {
        afficher();
        expect(champ("user_speech_timeout").value).toBe("0.6");
        expect(champ("vad_stop_secs").value).toBe("0.2");
        expect(champ("user_turn_stop_timeout").value).toBe("5");
        expect(champ("audio_idle_timeout").value).toBe("1");
    });

    it("laisse la latence de transcription VIDE et dit ce que vide veut dire", () => {
        // 🔑 Empty is not zero here: it means "the value Pipecat measured for
        // this provider". A 0 drawn in the box would be a value nobody chose,
        // and would read as "no wait at all".
        afficher();
        expect(champ("stt_ttfs_p99_latency").value).toBe("");
        expect(document.body.textContent).toMatch(
            /leave empty to keep the value pipecat measured/i,
        );
    });

    it("remonte la latence a null quand on vide le champ", () => {
        const onChange = afficher({ stt_ttfs_p99_latency: 0.5 });
        fireEvent.change(champ("stt_ttfs_p99_latency"), { target: { value: "" } });
        expect(onChange).toHaveBeenCalledWith(
            expect.objectContaining({ stt_ttfs_p99_latency: null }),
        );
    });

    it("remonte une valeur numerique modifiee", () => {
        const onChange = afficher();
        fireEvent.change(champ("user_speech_timeout"), { target: { value: "1.5" } });
        expect(onChange).toHaveBeenCalledWith(
            expect.objectContaining({ user_speech_timeout: 1.5 }),
        );
    });

    it("dit que la latence et le detecteur sont lies", () => {
        // The one sentence that keeps someone from moving the detector alone
        // and making the end of turn wrong without knowing it.
        afficher();
        expect(document.body.textContent).toMatch(/tied to the transcription latency/i);
    });

    it("cache Smart Turn tant que la strategie n'est pas Smart Turn", () => {
        afficher();
        expect(champ("smart_turn_pre_speech_ms")).toBeNull();
        afficher({}, { smartTurnActif: true });
        expect(champ("smart_turn_pre_speech_ms").value).toBe("500");
    });

    it("cache les delais de fin de tour tant que le reglage est eteint", () => {
        afficher();
        expect(champ("incomplete_short_timeout")).toBeNull();
        afficher({ filter_incomplete_user_turns: true });
        expect(champ("incomplete_short_timeout").value).toBe("5");
    });

    it("cache toute la section quand la transcription pilote les tours", () => {
        // 🚨 A setting shown in a state that is not its own is worse than a
        // setting not shown: someone would raise the pause, hear nothing
        // change, and conclude the section does nothing.
        afficher({}, { tourPiloteAilleurs: true });
        expect(champ("user_speech_timeout")).toBeNull();
        expect(document.body.textContent).toMatch(
            /decides the turn boundaries itself/i,
        );
    });
});

describe("Quelle transcription pilote les tours", () => {
    it("un modele Flux de l'organisation pilote les tours", () => {
        expect(
            transcriptionPiloteLesTours({
                organisation: { stt: { provider: "deepgram", model: "flux-general-multi" } },
            }),
        ).toBe(true);
    });

    it("un modele classique ne pilote pas les tours", () => {
        expect(
            transcriptionPiloteLesTours({
                organisation: { stt: { provider: "deepgram", model: "nova-3-general" } },
            }),
        ).toBe(false);
    });

    it("la surcharge de l'agent l'emporte sur l'organisation", () => {
        expect(
            transcriptionPiloteLesTours({
                organisation: { stt: { provider: "deepgram", model: "nova-3-general" } },
                agent: {
                    model_overrides: { stt: { provider: "deepgram", model: "flux-general-en" } },
                },
            }),
        ).toBe(true);
    });

    it("une surcharge v2 complete REMPLACE l'organisation, elle ne s'y ajoute pas", () => {
        // ⚠️ Same order as the server. Merging instead of replacing would keep
        // the organization's Flux model and hide the section for an agent that
        // was moved back to a classic model.
        expect(
            transcriptionEffective({
                organisation: { stt: { provider: "deepgram", model: "flux-general-multi" } },
                agent: {
                    model_configuration_v2_override: {
                        stt: { provider: "deepgram", model: "nova-3-general" },
                    },
                },
            }),
        ).toEqual({ provider: "deepgram", model: "nova-3-general" });
    });

    it("le temps reel pilote toujours ses tours", () => {
        expect(transcriptionPiloteLesTours({ estTempsReel: true })).toBe(true);
    });

    it("sans configuration connue, la section reste affichee", () => {
        // ⛔ Hiding on "we do not know" would hide the section for every agent
        // whose configuration has not loaded yet.
        expect(transcriptionPiloteLesTours({})).toBe(false);
    });
});
