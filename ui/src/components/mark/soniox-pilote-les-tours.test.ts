/**
 * [.mark] Chantier exposition-soniox (2026-09-29): Soniox drives the turns
 * when it decides the end of the turn (`endpoint_detection`, on by default),
 * exactly as the server's `stt_uses_external_turns` says. The pause settings of
 * the « Turn taking » theme are then hidden, as under Flux; switched off, the
 * local detector decides and they are shown.
 *
 * ⛔ Same rule on both sides: `api/tests/mark/test_soniox_expose.py`
 * (`test_qui_decide_de_la_fin_de_tour`) holds the server's half.
 */
import { describe, expect, it } from "vitest";

import { transcriptionPiloteLesTours } from "./transcriptionPiloteLesTours";

describe("[.mark] Soniox and the turn-taking settings", () => {
    it("Soniox with no setting decides the turns (default on)", () => {
        expect(
            transcriptionPiloteLesTours({ organisation: { stt: { provider: "soniox", model: "stt-rt-v5" } } }),
        ).toBe(true);
    });

    it("Soniox switched to the local detector does not", () => {
        expect(
            transcriptionPiloteLesTours({
                organisation: { stt: { provider: "soniox", model: "stt-rt-v5", endpoint_detection: false } },
            }),
        ).toBe(false);
    });

    it("an agent's override of the switch wins over the organization", () => {
        expect(
            transcriptionPiloteLesTours({
                organisation: { stt: { provider: "soniox", model: "stt-rt-v5" } },
                agent: { model_overrides: { stt: { endpoint_detection: false } } },
            }),
        ).toBe(false);
    });

    it("an agent moved to Soniox over a Deepgram organization decides by default", () => {
        expect(
            transcriptionPiloteLesTours({
                organisation: { stt: { provider: "deepgram", model: "nova-3-general" } },
                agent: { model_overrides: { stt: { provider: "soniox", model: "stt-rt-v5" } } },
            }),
        ).toBe(true);
    });

    it("the switch of Soniox does not leak onto another provider", () => {
        expect(
            transcriptionPiloteLesTours({
                organisation: { stt: { provider: "deepgram", model: "nova-3-general", endpoint_detection: true } },
            }),
        ).toBe(false);
    });
});
