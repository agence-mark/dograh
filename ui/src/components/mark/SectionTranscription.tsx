import { Label } from "@/components/ui/label";
import { Switch } from "@/components/ui/switch";

/**
 * [.mark] The "Transcription" section of an agent's settings page.
 *
 * ⛔ Its own section, NOT a field of the turn-taking one: that section is
 * hidden for agents whose transcription drives the turns (Deepgram Flux), and
 * the first agent this switch is for runs on Flux. Put there, it would have
 * been invisible exactly where it is needed. So this section is never hidden.
 *
 * 🔒 Defaults are not chosen here: the page hands over the value already
 * resolved, and the resolved default is off, which is today's behaviour.
 */
export interface ReglagesTranscription {
    conversion_nombres_transcription: boolean;
}

interface SectionTranscriptionProps {
    reglages: ReglagesTranscription;
    onChange: (reglages: ReglagesTranscription) => void;
}

export const SectionTranscription = ({ reglages, onChange }: SectionTranscriptionProps) => (
    <div className="space-y-4">
        <div>
            <h3 className="text-sm font-semibold mb-1">Transcription</h3>
            <p className="text-xs text-muted-foreground">
                What happens to the caller&apos;s words before the model reads them.
            </p>
        </div>

        <div className="space-y-2">
            <div className="flex items-center justify-between gap-4">
                <Label htmlFor="conversion_nombres_transcription" className="text-sm">
                    Write dictated numbers as digits
                </Label>
                <Switch
                    id="conversion_nombres_transcription"
                    checked={reglages.conversion_nombres_transcription}
                    onCheckedChange={(coche) =>
                        onChange({ ...reglages, conversion_nombres_transcription: coche })
                    }
                />
            </div>
            <p className="text-xs text-muted-foreground">
                Converts numbers the caller dictates into digits before the model reads them.
            </p>
            <p className="text-xs text-muted-foreground">No effect in realtime mode.</p>
            <p className="text-xs text-muted-foreground">
                With the &quot;minimum words&quot; interruption and interim transcripts turned
                off, dictated numbers count as fewer words.
            </p>
        </div>
    </div>
);
