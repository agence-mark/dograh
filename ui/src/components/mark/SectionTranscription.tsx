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
 * resolved. Number conversion is off by default; the town check is ON by
 * default (decision D5 of 2026-09-16).
 */
export interface ReglagesTranscription {
    conversion_nombres_transcription: boolean;
    verification_communes: boolean;
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
                Rewrites the numbers the caller dictates as digits before the model reads them,
                and reads postal codes said both ways (&quot;soixante sept cent quarante&quot;,
                &quot;soixante mille sept cent quarante&quot;), amounts and invoice or quote
                references.
            </p>
            <p className="text-xs text-muted-foreground">
                The recorded transcript keeps the caller&apos;s words.
            </p>
            <p className="text-xs text-muted-foreground">French only. No effect in realtime mode.</p>
        </div>

        <div className="space-y-2">
            <div className="flex items-center justify-between gap-4">
                <Label htmlFor="verification_communes" className="text-sm">
                    Recognise the caller&apos;s town
                </Label>
                <Switch
                    id="verification_communes"
                    checked={reglages.verification_communes}
                    onCheckedChange={(coche) =>
                        onChange({ ...reglages, verification_communes: coche })
                    }
                />
            </div>
            <p className="text-xs text-muted-foreground">
                Matches the town the caller names against the official list of French communes
                before the model reads it.
            </p>
            <p className="text-xs text-muted-foreground">
                Acts only at steps that collect a <code>commune</code> or <code>adresse…</code>{" "}
                variable.
            </p>
            <p className="text-xs text-muted-foreground">No effect in realtime mode.</p>
        </div>
    </div>
);
