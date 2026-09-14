import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import {
    Select,
    SelectContent,
    SelectItem,
    SelectTrigger,
    SelectValue,
} from "@/components/ui/select";
import { Switch } from "@/components/ui/switch";

/**
 * [.mark] The "Turn taking" section of an agent's configuration dialog.
 *
 * What it settles: the agent that talks over the caller, or leaves a silence.
 * It is the section that weighs most on how the agent is perceived, and every
 * value in it used to be a literal in the pipeline that nobody had chosen.
 *
 * 🔒 No default is chosen here either: the dialog hands over values already
 * resolved, and every resolved default reproduces what the pipeline ran with
 * before this patch.
 *
 * 🔑 Related settings are shown together, with the sentence that ties them:
 * the transcription latency was MEASURED with a detector set to 0.2 s, so
 * moving the detector without it makes the end of turn wrong.
 */

export interface ReglagesTourDeParole {
    user_speech_timeout: number;
    stt_ttfs_p99_latency: number | null;
    user_turn_stop_timeout: number;
    turn_wait_for_transcript: boolean;
    turn_start_use_interim: boolean;
    vad_confidence: number;
    vad_start_secs: number;
    vad_stop_secs: number;
    vad_min_volume: number;
    smart_turn_pre_speech_ms: number;
    smart_turn_max_duration_secs: number;
    audio_idle_timeout: number;
    filter_incomplete_user_turns: boolean;
    incomplete_short_timeout: number;
    incomplete_long_timeout: number;
    audio_in_noise_filter: 'none' | 'rnnoise';
}

interface SectionTourDeParoleProps {
    reglages: ReglagesTourDeParole;
    onChange: (reglages: ReglagesTourDeParole) => void;
    /** True when the transcription service or a realtime model owns the turns. */
    tourPiloteAilleurs: boolean;
    /** True when the agent's end-of-turn strategy is Smart Turn. */
    smartTurnActif: boolean;
}

type CleNumerique = {
    [K in keyof ReglagesTourDeParole]: ReglagesTourDeParole[K] extends number ? K : never;
}[keyof ReglagesTourDeParole];

type CleBooleenne = {
    [K in keyof ReglagesTourDeParole]: ReglagesTourDeParole[K] extends boolean ? K : never;
}[keyof ReglagesTourDeParole];

export const SectionTourDeParole = ({
    reglages,
    onChange,
    tourPiloteAilleurs,
    smartTurnActif,
}: SectionTourDeParoleProps) => {
    const nombre = (cle: CleNumerique, etiquette: string, aide: string, pas = "0.1") => (
        <div className="space-y-2">
            <Label htmlFor={cle} className="text-xs">
                {etiquette}
            </Label>
            <Input
                id={cle}
                type="number"
                step={pas}
                value={reglages[cle]}
                onChange={(e) => {
                    const valeur = parseFloat(e.target.value);
                    if (!isNaN(valeur)) onChange({ ...reglages, [cle]: valeur });
                }}
            />
            <p className="text-xs text-muted-foreground">{aide}</p>
        </div>
    );

    const interrupteur = (cle: CleBooleenne, etiquette: string, aide: string) => (
        <div className="space-y-2">
            <div className="flex items-center justify-between gap-4">
                <Label htmlFor={cle} className="text-sm">
                    {etiquette}
                </Label>
                <Switch
                    id={cle}
                    checked={reglages[cle]}
                    onCheckedChange={(coche) => onChange({ ...reglages, [cle]: coche })}
                />
            </div>
            <p className="text-xs text-muted-foreground">{aide}</p>
        </div>
    );

    const bruit = (
        <div className="space-y-4 border-t pt-4">
            <p className="text-xs font-medium">Noise</p>
            <div className="space-y-2">
                <Label htmlFor="audio_in_noise_filter" className="text-xs">
                    Clean the caller&apos;s audio
                </Label>
                <Select
                    value={reglages.audio_in_noise_filter}
                    onValueChange={(valeur: 'none' | 'rnnoise') =>
                        onChange({ ...reglages, audio_in_noise_filter: valeur })
                    }
                >
                    <SelectTrigger id="audio_in_noise_filter">
                        <SelectValue />
                    </SelectTrigger>
                    <SelectContent>
                        <SelectItem value="none">No filter</SelectItem>
                        <SelectItem value="rnnoise">RNNoise</SelectItem>
                    </SelectContent>
                </Select>
                <p className="text-xs text-muted-foreground">
                    RNNoise is free and runs locally. ⚠️ A noise filter can get in the
                    transcription&apos;s way as easily as it helps: judge it on a real
                    phone line, not on a browser call.
                </p>
            </div>
        </div>
    );

    if (tourPiloteAilleurs) {
        // ⛔ The noise filter stays: it cleans the INCOMING audio, whoever
        // decides the turn boundaries. Hiding it with the rest would take a
        // working setting off the screen.
        return (
            <div className="space-y-4">
                <div>
                    <h3 className="text-sm font-semibold mb-1">Turn taking</h3>
                    <p className="text-xs text-muted-foreground">
                        Hidden for this agent: its transcription service decides the turn
                        boundaries itself (Deepgram Flux, Cartesia ink-2), or it runs a
                        realtime model that does. The pipeline follows those signals and
                        builds none of these settings, so showing them here would show
                        values that play no part in the call.
                    </p>
                </div>
                {bruit}
            </div>
        );
    }

    return (
        <div className="space-y-4">
            <div>
                <h3 className="text-sm font-semibold mb-1">Turn taking</h3>
                <p className="text-xs text-muted-foreground">
                    When the agent decides the caller has finished. The section that
                    weighs most on whether it cuts people off or leaves a silence.
                </p>
            </div>

            {nombre(
                "user_speech_timeout",
                "Pause before the agent answers (seconds)",
                "How long the caller may pause without losing the floor. Pipecat's own value, 0.6 s, applied until now.",
            )}

            <div className="space-y-2">
                <Label htmlFor="stt_ttfs_p99_latency" className="text-xs">
                    Transcription latency allowed (seconds)
                </Label>
                <Input
                    id="stt_ttfs_p99_latency"
                    type="number"
                    step="0.05"
                    placeholder="Provider value (0.35 s for Deepgram)"
                    value={reglages.stt_ttfs_p99_latency ?? ""}
                    onChange={(e) => {
                        const brut = e.target.value;
                        if (brut === "") {
                            onChange({ ...reglages, stt_ttfs_p99_latency: null });
                            return;
                        }
                        const valeur = parseFloat(brut);
                        if (!isNaN(valeur)) {
                            onChange({ ...reglages, stt_ttfs_p99_latency: valeur });
                        }
                    }}
                />
                <p className="text-xs text-muted-foreground">
                    Leave empty to keep the value Pipecat measured for the provider.
                    ⚠️ That measurement was taken with the voice detector set to 0.2 s:
                    change &quot;Silence before speech ends&quot; below without this one,
                    and the end of turn is wrong.
                </p>
            </div>

            {nombre(
                "user_turn_stop_timeout",
                "Hard ceiling on waiting for a transcript (seconds)",
                "The turn ends anyway past this. Read by the pipeline for a long time, on no screen until now.",
                "0.5",
            )}

            {interrupteur(
                "turn_wait_for_transcript",
                "Wait for a transcript before answering",
                "Off, the agent answers on silence alone: faster, but on nothing that was understood.",
            )}

            {interrupteur(
                "turn_start_use_interim",
                "Let partial transcripts confirm the caller started",
                "Off, only final transcripts count, so interruptions are detected later.",
            )}

            <div className="space-y-4 border-t pt-4">
                <p className="text-xs font-medium">Voice detector</p>
                {nombre(
                    "vad_confidence",
                    "Confidence required (0 to 1)",
                    "Higher misses quiet speech; lower takes background noise for a caller.",
                    "0.05",
                )}
                {nombre(
                    "vad_start_secs",
                    "Sound before speech starts (seconds)",
                    "Range is ours: Pipecat sets no bound on this one.",
                    "0.05",
                )}
                {nombre(
                    "vad_stop_secs",
                    "Silence before speech ends (seconds)",
                    "⚠️ Tied to the transcription latency above, measured at 0.2 s.",
                    "0.05",
                )}
                {nombre(
                    "vad_min_volume",
                    "Minimum volume (0 to 1)",
                    "Below this, sound is not treated as speech.",
                    "0.05",
                )}
                {nombre(
                    "audio_idle_timeout",
                    "No audio at all before the turn ends (seconds)",
                    "For instance if the caller mutes their microphone mid-sentence. 0 disables it.",
                    "0.5",
                )}
            </div>

            {bruit}

            {smartTurnActif && (
                <div className="space-y-4 border-t pt-4">
                    <p className="text-xs font-medium">Smart Turn</p>
                    {nombre(
                        "smart_turn_pre_speech_ms",
                        "Audio kept before speech (milliseconds)",
                        "What the Smart Turn model is given ahead of the caller's first word.",
                        "50",
                    )}
                    {nombre(
                        "smart_turn_max_duration_secs",
                        "Longest segment examined (seconds)",
                        "Beyond this, the model stops looking further back.",
                        "1",
                    )}
                </div>
            )}

            <div className="space-y-4 border-t pt-4">
                {interrupteur(
                    "filter_incomplete_user_turns",
                    "Let the model judge if the caller finished",
                    "⚠️ Off by default: one extra model call per turn, not checked against Mistral, and its follow-up prompts are in English.",
                )}
                {reglages.filter_incomplete_user_turns && (
                    <>
                        {nombre(
                            "incomplete_short_timeout",
                            "Wait after a sentence cut short (seconds)",
                            "Before the agent prompts the caller again.",
                            "0.5",
                        )}
                        {nombre(
                            "incomplete_long_timeout",
                            "Wait after the caller asked for time (seconds)",
                            "Before the agent prompts the caller again.",
                            "0.5",
                        )}
                    </>
                )}
            </div>
        </div>
    );
};
