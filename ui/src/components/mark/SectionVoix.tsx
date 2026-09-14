import { Label } from "@/components/ui/label";
import { Switch } from "@/components/ui/switch";

/**
 * [.mark] The "Voice" section of an agent's configuration dialog.
 *
 * Lives in our own folder and is imported in one line by
 * `ConfigurationsDialog.tsx`, so an upstream change to that 500-line
 * hand-written file does not collide with ours on every version bump.
 *
 * 🔒 Defaults are not chosen here: the dialog hands over the value already
 * resolved, and every resolved default reproduces what the pipeline hardcodes
 * today.
 */
export interface ReglagesVoix {
    tts_markdown_filter_enabled: boolean;
}

interface SectionVoixProps {
    reglages: ReglagesVoix;
    onChange: (reglages: ReglagesVoix) => void;
}

export const SectionVoix = ({ reglages, onChange }: SectionVoixProps) => (
    <div className="space-y-4">
        <div>
            <h3 className="text-sm font-semibold mb-1">Voice</h3>
            <p className="text-xs text-muted-foreground">
                How the agent&apos;s text is turned into speech.
            </p>
        </div>

        <div className="space-y-4">
            <div className="flex items-center justify-between gap-4">
                <Label htmlFor="tts-markdown-filter" className="text-sm">
                    Strip markdown before speaking
                </Label>
                <Switch
                    id="tts-markdown-filter"
                    checked={reglages.tts_markdown_filter_enabled}
                    onCheckedChange={(checked) =>
                        onChange({ ...reglages, tts_markdown_filter_enabled: checked })
                    }
                />
            </div>
            <p className="text-xs text-muted-foreground">
                Without this, a model that answers with <strong>**bold**</strong> has the
                asterisks read out loud. It does not touch parentheses: a stage direction
                such as &quot;(one moment, I&apos;m transferring you)&quot; is still spoken,
                and stays a matter for the prompt.
            </p>
        </div>
    </div>
);
