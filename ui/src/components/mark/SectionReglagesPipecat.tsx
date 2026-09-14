"use client";

import { SlidersHorizontal } from "lucide-react";
import { useMemo, useState } from "react";
import { toast } from "sonner";

import { Button } from "@/components/ui/button";
import {
    Card,
    CardContent,
    CardDescription,
    CardFooter,
    CardHeader,
    CardTitle,
} from "@/components/ui/card";
import { useOrgConfig } from "@/context/OrgConfigContext";
import { useUnsavedChanges } from "@/context/UnsavedChangesContext";
import type { WorkflowConfigurations } from "@/types/workflow-configurations";

import { messagesHorsBornes } from "./bornes-reglages";
import {
    type ReglagesCoupureMicro,
    SectionCoupureMicro,
} from "./SectionCoupureMicro";
import { type ReglagesRelance, SectionRelance } from "./SectionRelance";
import {
    type ReglagesTourDeParole,
    SectionTourDeParole,
} from "./SectionTourDeParole";
import { type ReglagesVoix, SectionVoix } from "./SectionVoix";
import { transcriptionPiloteLesTours } from "./transcriptionPiloteLesTours";

/**
 * [.mark] The Pipecat settings, as a section of the agent settings PAGE.
 *
 * Why this file exists, and it is worth reading before touching it
 * ---------------------------------------------------------------
 * These four sections were first mounted in
 * `app/workflow/[workflowId]/components/ConfigurationsDialog.tsx`. That file is
 * mounted in NO screen of the application, and it already was orphaned in
 * Dograh's own code (checked on `b3bb7328`, `20b3e12`, and against the running
 * install). So the server was right, the settings were in the published spec,
 * 359 tests were green — and nobody could touch a single one of them.
 *
 * The tests did not catch it because they rendered the dialog and asserted the
 * four sections were mounted INSIDE it. None asserted the dialog itself was
 * mounted anywhere. Hence `section-reglages-pipecat-montee.test.tsx`, which
 * reads `settings/page.tsx` and asserts this component is imported AND
 * rendered there. It is the test that was missing.
 *
 * The real screen is `/workflow/{id}/settings`.
 *
 * Shape of the file
 * -----------------
 * The four sections themselves are untouched: they are written and tested. This
 * file is the glue — it owns their state, it owns the Save button, and it is
 * the ONE place that knows which settings belong to which section.
 *
 * No value is chosen here. Every default is the one the pipeline already
 * hardcodes; the resolved configuration is handed in by the page.
 */

// ---------------------------------------------------------------------------
// The key partition.
//
// Listed explicitly, and NOT as `Object.keys(DEFAUTS_PIPECAT)`. That shortcut
// made the turn-taking section carry every Pipecat key, voice ones included;
// spread after the voice section on save, it silently put the voice settings
// back to the values they had when the screen opened. So flipping the markdown
// switch and saving stored `false`. Measured 2026-09-14, and it is exactly the
// defect `cles-des-sections.test.ts` guards against.
//
// These four lists must stay a PARTITION of the Pipecat settings: every key
// once, none twice, none invented. And none of them may collide with a key
// `GeneralSection` owns — both invariants are asserted in that same test file.
// ---------------------------------------------------------------------------

export const CLES_COUPURE = [
    "mute_until_first_bot_complete",
    "mute_during_function_call",
    "mute_engine_callback",
    "mute_first_speech",
    "mute_always",
] as const;

export const CLES_VOIX = [
    "tts_markdown_filter_enabled",
    "tts_push_silence_after_stop",
    "tts_silence_time_s",
    "tts_text_aggregation_mode",
    "tts_replacements",
] as const;

export const CLES_RELANCE = [
    "user_idle_prompt",
    "user_idle_goodbye_prompt",
    "user_idle_max_prompts",
] as const;

export const CLES_TOUR_DE_PAROLE = [
    "user_speech_timeout",
    "stt_ttfs_p99_latency",
    "user_turn_stop_timeout",
    "turn_wait_for_transcript",
    "turn_start_use_interim",
    "vad_confidence",
    "vad_start_secs",
    "vad_stop_secs",
    "vad_min_volume",
    "smart_turn_pre_speech_ms",
    "smart_turn_max_duration_secs",
    "audio_idle_timeout",
    "filter_incomplete_user_turns",
    "incomplete_short_timeout",
    "incomplete_long_timeout",
    "audio_in_noise_filter",
] as const;

const extraireCoupure = (
    configurations: WorkflowConfigurations,
): ReglagesCoupureMicro =>
    Object.fromEntries(
        CLES_COUPURE.map((cle) => [cle, (configurations as Record<string, unknown>)[cle]]),
    ) as unknown as ReglagesCoupureMicro;

const extraireVoix = (configurations: WorkflowConfigurations): ReglagesVoix =>
    Object.fromEntries(
        CLES_VOIX.map((cle) => [
            cle,
            // The replacements list is the one key with no scalar default: an
            // agent that never touched it has nothing stored, and the tag field
            // would render on undefined.
            cle === "tts_replacements"
                ? ((configurations as Record<string, unknown>)[cle] ?? [])
                : (configurations as Record<string, unknown>)[cle],
        ]),
    ) as unknown as ReglagesVoix;

const extraireRelance = (
    configurations: WorkflowConfigurations,
): ReglagesRelance =>
    Object.fromEntries(
        CLES_RELANCE.map((cle) => [cle, (configurations as Record<string, unknown>)[cle]]),
    ) as unknown as ReglagesRelance;

const extraireTourDeParole = (
    configurations: WorkflowConfigurations,
): ReglagesTourDeParole =>
    Object.fromEntries(
        CLES_TOUR_DE_PAROLE.map((cle) => [
            cle,
            (configurations as Record<string, unknown>)[cle],
        ]),
    ) as unknown as ReglagesTourDeParole;

/**
 * The same sentence the other sections of the page use.
 *
 * Copied rather than imported on purpose: `settings/page.tsx` imports THIS
 * file, so importing its constant back would be a cycle. The copy is kept
 * honest by `section-reglages-pipecat.test.tsx`, which reads their file and
 * asserts the two sentences still match -- two wordings for the same
 * instruction on the same screen is how a user learns to distrust it.
 */
export const RAPPEL_PUBLICATION = "Publish the agent to apply the changes.";

/** The id the card carries, and the one `NAV_ITEMS` must point at. */
export const ID_SECTION_REGLAGES_PIPECAT = "speech-tuning";

interface SectionReglagesPipecatProps {
    /** The RESOLVED configuration, as the page hands it to every other section. */
    workflowConfigurations: WorkflowConfigurations;
    workflowName: string;
    onSave: (
        configurations: WorkflowConfigurations,
        workflowName: string,
    ) => Promise<void>;
}

export const SectionReglagesPipecat = ({
    workflowConfigurations,
    workflowName,
    onSave,
}: SectionReglagesPipecatProps) => {
    const { userConfig } = useOrgConfig();

    const [reglagesTourDeParole, setReglagesTourDeParole] = useState<ReglagesTourDeParole>(
        () => extraireTourDeParole(workflowConfigurations),
    );
    const [reglagesCoupure, setReglagesCoupure] = useState<ReglagesCoupureMicro>(
        () => extraireCoupure(workflowConfigurations),
    );
    const [reglagesRelance, setReglagesRelance] = useState<ReglagesRelance>(
        () => extraireRelance(workflowConfigurations),
    );
    const [reglagesVoix, setReglagesVoix] = useState<ReglagesVoix>(
        () => extraireVoix(workflowConfigurations),
    );
    const [isSaving, setIsSaving] = useState(false);

    // Read from the SAME resolution the server uses: a section hidden for an
    // agent that does use these settings is as wrong as one shown for an agent
    // that does not.
    const tourPiloteAilleurs = transcriptionPiloteLesTours({
        organisation: userConfig,
        agent: workflowConfigurations,
    });

    // `turn_stop_strategy` belongs to `GeneralSection`, not to us. We only READ
    // it, to know whether the Smart Turn fields apply. Changing it in General
    // shows here once General has been saved — which is when the page refreshes
    // the configuration it hands every section.
    const smartTurnActif = workflowConfigurations.turn_stop_strategy === "turn_analyzer";

    const isDirty = useMemo(() => {
        const enregistre = {
            ...extraireTourDeParole(workflowConfigurations),
            ...extraireCoupure(workflowConfigurations),
            ...extraireRelance(workflowConfigurations),
            ...extraireVoix(workflowConfigurations),
        };
        const courant = {
            ...reglagesTourDeParole,
            ...reglagesCoupure,
            ...reglagesRelance,
            ...reglagesVoix,
        };
        return JSON.stringify(enregistre) !== JSON.stringify(courant);
    }, [
        workflowConfigurations,
        reglagesTourDeParole,
        reglagesCoupure,
        reglagesRelance,
        reglagesVoix,
    ]);

    // The server bounds these settings; the screen bounded none of them until
    // 2026-09-14. A value out of range made the save return 422, and the catch
    // below only logged -- no message, no success, "Unsaved changes" still up.
    // Worse: the payload carries the WHOLE configuration, so one bad field also
    // blocked the three other blocks. Now the button says no before the server
    // has to.
    const fautifs = useMemo(
        () => messagesHorsBornes({
            ...reglagesTourDeParole,
            ...reglagesRelance,
            ...reglagesVoix,
        } as Record<string, unknown>),
        [reglagesTourDeParole, reglagesRelance, reglagesVoix],
    );
    const nombreDeFautifs = Object.keys(fautifs).length;

    useUnsavedChanges(ID_SECTION_REGLAGES_PIPECAT, isDirty);

    const handleSave = async () => {
        setIsSaving(true);
        try {
            // Spread the whole resolved configuration first, then our four
            // sections. The page refreshes this prop from the server response
            // after every save, so starting from it does NOT undo what another
            // section just saved — and a key this screen knows nothing about
            // survives untouched.
            await onSave(
                {
                    ...workflowConfigurations,
                    ...reglagesTourDeParole,
                    ...reglagesCoupure,
                    ...reglagesRelance,
                    ...reglagesVoix,
                },
                workflowName,
            );
            toast.success(`Speech tuning saved. ${RAPPEL_PUBLICATION}`);
        } catch (error) {
            // Upstream sections swallow this (settings/page.tsx:477, :1079,
            // :1279). Ours does not: these are the only settings on the screen
            // with bounds this tight, and a save that fails in silence is the
            // same family of defect as a setting nobody can see.
            console.error("Failed to save speech tuning:", error);
            toast.error(
                error instanceof Error && error.message
                    ? `Speech tuning not saved: ${error.message}`
                    : "Speech tuning not saved. Check the values and try again.",
            );
        } finally {
            setIsSaving(false);
        }
    };

    return (
        <Card id={ID_SECTION_REGLAGES_PIPECAT}>
            <CardHeader>
                <CardTitle className="flex items-center gap-2 text-base">
                    <SlidersHorizontal className="h-4 w-4" />
                    Speech Tuning
                </CardTitle>
                <CardDescription>
                    Turn taking, voice output, idle prompts and interruptions. These
                    settings shape how the conversation feels on the phone.
                </CardDescription>
            </CardHeader>
            <CardContent className="space-y-8">
                <SectionTourDeParole
                    reglages={reglagesTourDeParole}
                    onChange={setReglagesTourDeParole}
                    tourPiloteAilleurs={tourPiloteAilleurs}
                    smartTurnActif={smartTurnActif}
                />
                <SectionCoupureMicro
                    reglages={reglagesCoupure}
                    onChange={setReglagesCoupure}
                />
                <SectionRelance reglages={reglagesRelance} onChange={setReglagesRelance} />
                <SectionVoix reglages={reglagesVoix} onChange={setReglagesVoix} />
            </CardContent>
            <CardFooter className="justify-end gap-3 border-t pt-6">
                {nombreDeFautifs > 0 && (
                    // NAME them, never just count them. Two reasons, both from
                    // review: this card is long, so "1 setting is out of range"
                    // makes you hunt; and a setting can be out of range while
                    // its field is HIDDEN (the whole turn-taking block when the
                    // transcription drives the turns, the Smart Turn fields
                    // when that strategy is off, the silence duration when the
                    // silence is off). Counting alone would then lock the card
                    // with nothing on screen to fix -- a dead end.
                    <span className="text-xs text-destructive">
                        {Object.entries(fautifs)
                            .map(([cle, message]) => `${cle}: ${message}`)
                            .join(" ")}
                    </span>
                )}
                {nombreDeFautifs === 0 && isDirty && (
                    <span className="text-xs text-muted-foreground">Unsaved changes</span>
                )}
                <Button onClick={handleSave} disabled={isSaving || !isDirty || nombreDeFautifs > 0}>
                    {isSaving ? "Saving..." : "Save Speech Tuning"}
                </Button>
            </CardFooter>
        </Card>
    );
};
