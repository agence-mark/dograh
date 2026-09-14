import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";

import { attributDeLongueur, attributsDeBorne, messageHorsBornes } from "./bornes-reglages";

/**
 * [.mark] The "Idle prompts" section of an agent's settings page.
 *
 * What it settles: a caller who goes quiet was answered in English, by two
 * instructions written into the pipeline, and hung up on after exactly one
 * prompt. Nothing on any screen said so, and no client could change either.
 *
 * ⚠️ These are INSTRUCTIONS given to the model, not sentences spoken word for
 * word. The screen has to say so: someone who types "Are you still there?"
 * expecting that exact sentence will hear something else, decide the field
 * does not work, and stop trusting the screen.
 *
 * 🔒 Defaults are the two English texts the pipeline sends today, on purpose.
 * Translating them here would be choosing a value, and it would do it for
 * every existing agent at once, silently.
 */

export interface ReglagesRelance {
    user_idle_prompt: string;
    user_idle_goodbye_prompt: string;
    user_idle_max_prompts: number;
}

interface SectionRelanceProps {
    reglages: ReglagesRelance;
    onChange: (reglages: ReglagesRelance) => void;
}

export const SectionRelance = ({ reglages, onChange }: SectionRelanceProps) => (
    <div className="space-y-4">
        <div>
            <h3 className="text-sm font-semibold mb-1">Idle prompts</h3>
            <p className="text-xs text-muted-foreground">
                What the agent does when the caller goes quiet, past the idle timeout
                set above. ⚠️ These are instructions given to the model, not sentences
                spoken word for word: the model answers in the caller&apos;s language.
            </p>
        </div>

        <div className="space-y-2">
            <Label htmlFor="user_idle_prompt" className="text-xs">
                When the caller goes quiet
            </Label>
            <Textarea
                id="user_idle_prompt"
                {...attributDeLongueur("user_idle_prompt")}
                rows={3}
                value={reglages.user_idle_prompt}
                onChange={(e) =>
                    onChange({ ...reglages, user_idle_prompt: e.target.value })
                }
            />
        </div>

        <div className="space-y-2">
            <Label htmlFor="user_idle_max_prompts" className="text-xs">
                How many times before hanging up
            </Label>
            <Input
                id="user_idle_max_prompts"
                type="number"
                step="1"
                {...attributsDeBorne("user_idle_max_prompts")}
                aria-invalid={
                    messageHorsBornes("user_idle_max_prompts", reglages.user_idle_max_prompts)
                        ? true
                        : undefined
                }
                value={reglages.user_idle_max_prompts}
                onChange={(e) => {
                    const valeur = parseInt(e.target.value, 10);
                    if (!isNaN(valeur) && valeur >= 0) {
                        onChange({ ...reglages, user_idle_max_prompts: valeur });
                    }
                }}
            />
            {messageHorsBornes("user_idle_max_prompts", reglages.user_idle_max_prompts)
                ? (
                    <p className="text-xs text-destructive">
                        {messageHorsBornes("user_idle_max_prompts", reglages.user_idle_max_prompts)}
                    </p>
                )
                : (
                    <p className="text-xs text-muted-foreground">
                        0 hangs up on the first silence, with the goodbye below.
                    </p>
                )}
        </div>

        <div className="space-y-2">
            <Label htmlFor="user_idle_goodbye_prompt" className="text-xs">
                Before hanging up
            </Label>
            <Textarea
                id="user_idle_goodbye_prompt"
                {...attributDeLongueur("user_idle_goodbye_prompt")}
                rows={3}
                value={reglages.user_idle_goodbye_prompt}
                onChange={(e) =>
                    onChange({ ...reglages, user_idle_goodbye_prompt: e.target.value })
                }
            />
            <p className="text-xs text-muted-foreground">
                The call is hung up right after this one, whatever the model answers.
            </p>
        </div>
    </div>
);
