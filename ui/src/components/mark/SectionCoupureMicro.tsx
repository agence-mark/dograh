import { Label } from "@/components/ui/label";
import { Switch } from "@/components/ui/switch";

/**
 * [.mark] The "Interruptions" section of an agent's configuration dialog.
 *
 * What it settles in a real call: the greeting cut in half by a "hello", and
 * the transfer interrupted halfway through.
 *
 * Three strategies ran in a fixed list in the pipeline, two more that Pipecat
 * offers were never built, and none of it was on any screen.
 *
 * 🔒 Three on, two off: exactly today's behaviour.
 */

export interface ReglagesCoupureMicro {
    mute_until_first_bot_complete: boolean;
    mute_during_function_call: boolean;
    mute_engine_callback: boolean;
    mute_first_speech: boolean;
    mute_always: boolean;
}

interface SectionCoupureMicroProps {
    reglages: ReglagesCoupureMicro;
    onChange: (reglages: ReglagesCoupureMicro) => void;
}

const LIGNES: Array<{
    cle: keyof ReglagesCoupureMicro;
    etiquette: string;
    aide: string;
}> = [
    {
        cle: "mute_until_first_bot_complete",
        etiquette: "During the opening sentence",
        aide: "Keeps a greeting from being cut in half by a hello. On until now.",
    },
    {
        cle: "mute_during_function_call",
        etiquette: "While the agent is running a tool",
        aide: "A transfer or a lookup is not interrupted halfway through. On until now.",
    },
    {
        cle: "mute_engine_callback",
        etiquette: "Where the workflow says not to interrupt",
        aide: "⚠️ Off, every \"do not interrupt\" set on a node is ignored, silently.",
    },
    {
        cle: "mute_first_speech",
        etiquette: "During the agent's very first utterance",
        aide: "Narrower than the first one above. Never used until now.",
    },
    {
        cle: "mute_always",
        etiquette: "Never let the caller interrupt at all",
        aide: "⚠️ On a phone call this is usually the wrong answer: someone made to wait out a whole answer hangs up.",
    },
];

export const SectionCoupureMicro = ({
    reglages,
    onChange,
}: SectionCoupureMicroProps) => (
    <div className="space-y-4">
        <div>
            <h3 className="text-sm font-semibold mb-1">Interruptions</h3>
            <p className="text-xs text-muted-foreground">
                When the caller&apos;s microphone is ignored, so the agent can finish
                what it is doing.
            </p>
        </div>

        {LIGNES.map(({ cle, etiquette, aide }) => (
            <div key={cle} className="space-y-2">
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
        ))}
    </div>
);
