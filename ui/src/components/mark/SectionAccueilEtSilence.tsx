import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Switch } from "@/components/ui/switch";

import { attributsDeBorne, BORNES, messageHorsBornes } from "./bornes-reglages";

/**
 * [.mark] The "Greeting and silence" section of an agent's settings page.
 *
 * Decisions of Evan, 25/09/2026, taken for the rise to upstream `4e6cb22b`:
 *
 * - E1. Upstream now lets the caller cut the agent's greeting after 2 words.
 *   Here it is a setting, OFF by default: off, the greeting is heard to the
 *   end, exactly as before. On, the protection of the opening sentence is
 *   lifted for this agent and the caller cuts it after N words.
 * - E2. Upstream hangs up when the agent owes an answer and nothing is heard
 *   for 35 s. The delay is a setting, 35 s by default.
 *
 * A setting that is not on a screen does not exist: all three are here.
 */

export interface ReglagesAccueilEtSilence {
    accueil_interruptible: boolean;
    accueil_mots_minimum: number;
    raccrochage_silence_agent_s: number;
}

interface SectionAccueilEtSilenceProps {
    reglages: ReglagesAccueilEtSilence;
    onChange: (reglages: ReglagesAccueilEtSilence) => void;
}

const bornes = (cle: string) => {
    const borne = BORNES[cle];
    return borne ? `${borne.min} to ${borne.max}` : "";
};

export const SectionAccueilEtSilence = ({
    reglages,
    onChange,
}: SectionAccueilEtSilenceProps) => (
    <div className="space-y-4">
        <div>
            <h3 className="text-sm font-semibold mb-1">Greeting and silence</h3>
            <p className="text-xs text-muted-foreground">
                Whether the caller can cut the agent&apos;s greeting, and how long the
                call waits for a silent agent before hanging up.
            </p>
        </div>

        <div className="space-y-2">
            <div className="flex items-center justify-between gap-4">
                <Label htmlFor="accueil_interruptible" className="text-sm">
                    Caller can cut the greeting
                </Label>
                <Switch
                    id="accueil_interruptible"
                    checked={reglages.accueil_interruptible}
                    onCheckedChange={(coche) =>
                        onChange({ ...reglages, accueil_interruptible: coche })
                    }
                />
            </div>
            <p className="text-xs text-muted-foreground">
                Off until now: the greeting is always heard to the end. On: the
                &quot;During the opening sentence&quot; protection is lifted for this
                agent, and the greeting stops once the caller has said the number of
                words below.
            </p>
        </div>

        <div className="space-y-2">
            <Label htmlFor="accueil_mots_minimum" className="text-xs">
                Words needed to cut the greeting ({bornes("accueil_mots_minimum")})
            </Label>
            <Input
                id="accueil_mots_minimum"
                type="number"
                step="1"
                disabled={!reglages.accueil_interruptible}
                {...attributsDeBorne("accueil_mots_minimum")}
                aria-invalid={
                    messageHorsBornes("accueil_mots_minimum", reglages.accueil_mots_minimum)
                        ? true
                        : undefined
                }
                value={reglages.accueil_mots_minimum}
                onChange={(e) => {
                    const valeur = parseInt(e.target.value, 10);
                    if (!isNaN(valeur)) {
                        onChange({ ...reglages, accueil_mots_minimum: valeur });
                    }
                }}
            />
            <p className="text-xs text-muted-foreground">
                Only used when the switch above is on. 2 keeps a cough or a lone
                &quot;hello&quot; from cutting it.
            </p>
        </div>

        <div className="space-y-2">
            <Label htmlFor="raccrochage_silence_agent_s" className="text-xs">
                Hang up after the agent is silent for (seconds, {bornes("raccrochage_silence_agent_s")})
            </Label>
            <Input
                id="raccrochage_silence_agent_s"
                type="number"
                step="1"
                {...attributsDeBorne("raccrochage_silence_agent_s")}
                aria-invalid={
                    messageHorsBornes(
                        "raccrochage_silence_agent_s",
                        reglages.raccrochage_silence_agent_s,
                    )
                        ? true
                        : undefined
                }
                value={reglages.raccrochage_silence_agent_s}
                onChange={(e) => {
                    const valeur = parseFloat(e.target.value);
                    if (!isNaN(valeur)) {
                        onChange({ ...reglages, raccrochage_silence_agent_s: valeur });
                    }
                }}
            />
            <p className="text-xs text-muted-foreground">
                When the agent owes an answer and nothing is heard at all. Protects the
                caller from a frozen agent. While a tool runs, the wait is 180 s
                whatever this says.
            </p>
        </div>
    </div>
);
