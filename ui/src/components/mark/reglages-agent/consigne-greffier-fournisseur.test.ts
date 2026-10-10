/**
 * [.mark] The clerk's provider, as the screen resolves it to grey the
 * temperature out (review of 05/10): same order as the server, the agent's
 * full configuration read in its real shape, provider names in lower case.
 */
import { describe, expect, it } from "vitest";

import { fournisseurDuGreffier } from "./consigne-greffier";

const ORGANISATION = { llm: { provider: "mistral" } };
const complete = (provider: string, mode: "pipeline" | "realtime" = "pipeline") => ({
    version: 2,
    mode: "byok",
    byok: { mode, [mode]: { llm: { provider, model: "m" } } },
});

describe("the clerk's provider", () => {
    it("is its own first, in lower case", () => {
        expect(fournisseurDuGreffier(" Mistral ", { model_overrides: { llm: { provider: "openai" } } }, ORGANISATION)).toBe("mistral");
    });

    it("reads the agent's full configuration in its real shape, which replaces the organization's", () => {
        expect(fournisseurDuGreffier("", { model_configuration_v2_override: complete("openai") }, ORGANISATION)).toBe("openai");
        expect(fournisseurDuGreffier("", { model_configuration_v2_override: complete("groq", "realtime") }, ORGANISATION)).toBe("groq");
        expect(fournisseurDuGreffier("", { model_configuration_v2_override: { version: 2, mode: "dograh", dograh: {} } }, ORGANISATION)).toBe("dograh");
        // A shape the screen does not know: left open, never the organization's.
        expect(fournisseurDuGreffier("", { model_configuration_v2_override: { mode: "byok" } }, ORGANISATION)).toBeUndefined();
    });

    it("then the per-service override, then the organization's", () => {
        expect(fournisseurDuGreffier("", { model_overrides: { llm: { provider: "OpenRouter" } } }, ORGANISATION)).toBe("openrouter");
        expect(fournisseurDuGreffier("", {}, ORGANISATION)).toBe("mistral");
        expect(fournisseurDuGreffier("", null, null)).toBeUndefined();
    });

});
