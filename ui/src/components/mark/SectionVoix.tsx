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

import { attributsDeBorne, messageHorsBornes } from "./bornes-reglages";
import { ChampEtiquettes } from "./ChampEtiquettes";

/**
 * [.mark] The "Voice" section of an agent's settings page.
 *
 * Lives in our own folder and is imported in one line by
 * `SectionReglagesPipecat.tsx`, so an upstream change to that 1 900-line
 * hand-written file does not collide with ours on every version bump.
 *
 * 🔒 Defaults are not chosen here: the page hands over the value already
 * resolved, and every resolved default reproduces what the pipeline hardcodes
 * today.
 */
export interface ReglagesVoix {
    tts_markdown_filter_enabled: boolean;
    tts_push_silence_after_stop: boolean;
    tts_silence_time_s: number;
    tts_text_aggregation_mode: 'sentence' | 'token';
    tts_replacements: string[];
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

            <div className="space-y-2">
                <Label htmlFor="tts_text_aggregation_mode" className="text-xs">
                    Send text to the voice
                </Label>
                <Select
                    value={reglages.tts_text_aggregation_mode}
                    onValueChange={(valeur: 'sentence' | 'token') =>
                        onChange({ ...reglages, tts_text_aggregation_mode: valeur })
                    }
                >
                    <SelectTrigger id="tts_text_aggregation_mode">
                        <SelectValue />
                    </SelectTrigger>
                    <SelectContent>
                        <SelectItem value="sentence">Sentence by sentence</SelectItem>
                        <SelectItem value="token">Word by word</SelectItem>
                    </SelectContent>
                </Select>
                <p className="text-xs text-muted-foreground">
                    Word by word answers sooner, but it can degrade the voice depending
                    on the provider: judge it by ear.
                </p>
            </div>

            <div className="space-y-2">
                <div className="flex items-center justify-between gap-4">
                    <Label htmlFor="tts_push_silence_after_stop" className="text-sm">
                        Add silence after the agent speaks
                    </Label>
                    <Switch
                        id="tts_push_silence_after_stop"
                        checked={reglages.tts_push_silence_after_stop}
                        onCheckedChange={(coche) =>
                            onChange({ ...reglages, tts_push_silence_after_stop: coche })
                        }
                    />
                </div>
                <p className="text-xs text-muted-foreground">
                    Useful where a phone line clips the last syllable. &#9888; Off until
                    now, which is why the duration below changed nothing.
                </p>
            </div>

            {reglages.tts_push_silence_after_stop && (
                <div className="space-y-2">
                    <Label htmlFor="tts_silence_time_s" className="text-xs">
                        How long that silence lasts (seconds)
                    </Label>
                    <Input
                        id="tts_silence_time_s"
                        type="number"
                        step="0.1"
                        {...attributsDeBorne("tts_silence_time_s")}
                        aria-invalid={
                            messageHorsBornes("tts_silence_time_s", reglages.tts_silence_time_s)
                                ? true
                                : undefined
                        }
                        value={reglages.tts_silence_time_s}
                        onChange={(e) => {
                            const valeur = parseFloat(e.target.value);
                            if (!isNaN(valeur) && valeur >= 0) {
                                onChange({ ...reglages, tts_silence_time_s: valeur });
                            }
                        }}
                    />
                    {messageHorsBornes("tts_silence_time_s", reglages.tts_silence_time_s) && (
                        <p className="text-xs text-destructive">
                            {messageHorsBornes("tts_silence_time_s", reglages.tts_silence_time_s)}
                        </p>
                    )}
                </div>
            )}

            <div className="space-y-2">
                <Label htmlFor="tts_replacements" className="text-xs">
                    Pronunciation fixes
                </Label>
                <ChampEtiquettes
                    id="tts_replacements"
                    valeurs={reglages.tts_replacements}
                    onChange={(valeurs) =>
                        onChange({ ...reglages, tts_replacements: valeurs })
                    }
                    placeholder="SAV:S. A. V."
                />
                <p className="text-xs text-muted-foreground">
                    Written heard:spoken, matched literally. Only the text sent to the
                    voice changes: the conversation history keeps the original.
                </p>
            </div>
        </div>
    </div>
);
