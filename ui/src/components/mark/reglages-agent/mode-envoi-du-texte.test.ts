/**
 * [.mark] Voix-soniox, relecture m3 : l'écran dit le mode d'envoi du texte RETENU et d'où il vient, avec la même règle
 * que le serveur (`mode_d_envoi_du_texte` : l'agent gagne quand il demande « mot à mot », sinon la voix Soniox).
 * Le thème « Voix » rendu en entier est couvert par `page-reglages-agent.test.tsx` ; ici, la règle.
 */
import { describe, expect, it } from "vitest";

import { modeRetenu } from "./mode-envoi-du-texte";

const SONIOX_PHRASE = { provider: "soniox", text_aggregation_mode: "sentence" };
const SONIOX_MOT = { provider: "soniox", text_aggregation_mode: "token" };

describe("[.mark] le mode d'envoi du texte retenu", () => {
    it("l'agent qui demande mot à mot l'emporte, sur toute voix", () => {
        expect(modeRetenu("token", SONIOX_PHRASE)).toEqual({ mode: "token", origine: "agent" });
        expect(modeRetenu("token", { provider: "elevenlabs" })).toEqual({ mode: "token", origine: "agent" });
        expect(modeRetenu("token", null)).toEqual({ mode: "token", origine: "agent" });
    });

    it("sinon, la voix Soniox réglée mot à mot l'emporte", () => {
        expect(modeRetenu("sentence", SONIOX_MOT)).toEqual({ mode: "token", origine: "voix" });
    });

    it("sinon, phrase par phrase par défaut", () => {
        expect(modeRetenu("sentence", SONIOX_PHRASE)).toEqual({ mode: "sentence", origine: "defaut" });
        expect(modeRetenu(undefined, { provider: "soniox" })).toEqual({ mode: "sentence", origine: "defaut" });
        expect(modeRetenu("sentence", null)).toEqual({ mode: "sentence", origine: "defaut" });
    });

    it("le réglage de la voix Soniox ne joue que sous la voix Soniox", () => {
        expect(modeRetenu("sentence", { provider: "elevenlabs", text_aggregation_mode: "token" })).toEqual({
            mode: "sentence",
            origine: "defaut",
        });
    });
});
