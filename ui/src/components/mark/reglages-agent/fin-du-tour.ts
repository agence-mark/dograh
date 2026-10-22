/**
 * [.mark] Cloture-code, lot 8 (Evan, 22/10): who decides the END of the turn, as a choice
 * of the theme « Tour de parole », independent of who decides the START (the interruption).
 *
 * « Le fournisseur décide » = the transcription announces the end of the turn itself.
 * « Dograh décide »        = Dograh's own end-of-turn strategy (silence, or the Smart Turn model).
 *
 * The lever already exists and is not new: Soniox's `endpoint_detection` in the transcription
 * configuration (D3 of the fork, `stt_uses_external_turns` on the server). This module only
 * brings it into the theme and writes it where the transcription lives. The rule for « who
 * announces its turns » stays the one of `transcriptionPiloteLesTours.ts`, never a list of its own.
 */
import type { WorkflowConfigurations } from "@/types/workflow-configurations";

import type { Texte } from "../langue/langue";
import { type ConfigurationTranscription, MODELES_QUI_PILOTENT_LES_TOURS } from "../transcriptionPiloteLesTours";

/** The marker the API's migration reads (`DELIBERATE_PER_SERVICE_OVERRIDE_KEY`): keeps a per-service override. */
const MARQUEUR_SURCHARGE_VOULUE = "mark_per_service_override";

export type CasFinDuTour =
    /** The screen cannot read the transcription (another mode of models): no menu, nothing claimed. */
    | { cas: "inconnu" }
    /** Soniox: a real choice, written as `endpoint_detection`. */
    | { cas: "choix" }
    /** The end of the turn is part of the model (Flux, ink-2): frozen, with the model that lets Dograh decide. */
    | { cas: "fige"; autreModele: Texte }
    /** The transcription announces no turns: Dograh decides, with no other choice. */
    | { cas: "dograh" };

export const casFinDuTour = (stt: ConfigurationTranscription | null | undefined): CasFinDuTour => {
    if (!stt?.provider) return { cas: "inconnu" };
    if (stt.provider === "soniox") return { cas: "choix" };
    if (stt.model && MODELES_QUI_PILOTENT_LES_TOURS[stt.provider]?.includes(stt.model)) {
        return {
            cas: "fige",
            autreModele:
                stt.provider === "deepgram"
                    ? {
                          en: "The end of the turn is part of the Flux model. To let Dograh decide, choose Nova-3 (Deepgram) in « Services ».",
                          fr: "La fin du tour fait partie du modèle Flux. Pour laisser Dograh décider, choisissez Nova-3 (Deepgram) dans « Briques ».",
                      }
                    : {
                          en: "The end of the turn is part of the ink-2 model. To let Dograh decide, choose Ink-Whisper (Cartesia) in « Services ».",
                          fr: "La fin du tour fait partie du modèle ink-2. Pour laisser Dograh décider, choisissez Ink-Whisper (Cartesia) dans « Briques ».",
                      },
        };
    }
    return { cas: "dograh" };
};

/** The raw payload of a Soniox choice: where the transcription of THIS agent lives. */
interface CibleTranscription {
    byok?: { pipeline?: { stt?: Record<string, unknown> } };
}

/**
 * What to add to the configuration so the agent writes `endpoint_detection = fournisseurDecide`
 * in its transcription, the way the screen already writes the transcription:
 *
 * - an agent with a FULL configuration of its own (`model_configuration_v2_override`): the value
 *   goes in that configuration's transcription (a full override replaces the organization's);
 * - otherwise a per-service overlay `model_overrides.stt`, field by field over the organization's
 *   (the server merges it and validates the result), with the marker that keeps it an overlay.
 *
 * Nothing else of the transcription is touched, and no secret is written.
 */
export const chargeFinDuTour = (
    resolue: WorkflowConfigurations,
    fournisseurDecide: boolean,
): Partial<WorkflowConfigurations> => {
    const complete = resolue.model_configuration_v2_override;
    if (complete) {
        const copie = JSON.parse(JSON.stringify(complete)) as CibleTranscription;
        const stt = copie.byok?.pipeline?.stt;
        if (stt) stt.endpoint_detection = fournisseurDecide;
        return { model_configuration_v2_override: copie as never };
    }
    const surcharges = resolue.model_overrides ?? {};
    return {
        model_overrides: { ...surcharges, stt: { ...(surcharges.stt ?? {}), endpoint_detection: fournisseurDecide } },
        [MARQUEUR_SURCHARGE_VOULUE]: true,
    } as Partial<WorkflowConfigurations>;
};
