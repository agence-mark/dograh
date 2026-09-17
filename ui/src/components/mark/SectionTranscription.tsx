import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Switch } from "@/components/ui/switch";

import { attributDeLongueur } from "./bornes-reglages";

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
 *
 * The names of the variables that trigger the town check are a setting since
 * 2026-09-17 (decision of Evan): a client whose variable is `ville` gets the
 * check without a patch. Shown only while the switch is on, like the silence
 * duration under its switch in the voice section.
 */
export interface ReglagesTranscription {
    conversion_nombres_transcription: boolean;
    verification_communes: boolean;
    variables_commune: string;
}

/** One name: letters, digits, `_` or `-`, an optional final `*`. Same rule as the server. */
const NOM_VARIABLE = /^[\p{L}\p{N}_-]+\*?$/u;

/**
 * The message to show under the variable names, or `null` when they can be saved.
 *
 * Mirrors `decouper_variables_commune` (`api/schemas/workflow_configurations.py`),
 * which refuses the same entries with a 422: the button says no before the
 * server has to. Empty is fine: it means the default.
 */
export const erreurVariablesCommune = (texte: string | null | undefined): string | null => {
    const noms = (texte ?? "")
        .split(",")
        .map((nom) => nom.trim())
        .filter((nom) => nom !== "");
    const fautif = noms.find((nom) => !NOM_VARIABLE.test(nom));
    return fautif === undefined
        ? null
        : `"${fautif}" is not a variable name. Use letters, digits, _ or -, separated by commas; a * only at the end of a name.`;
};

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
                Acts only at steps that collect a town variable: <code>commune</code> or{" "}
                <code>adresse…</code> by default, or the names set below.
            </p>
            <p className="text-xs text-muted-foreground">No effect in realtime mode.</p>

            {reglages.verification_communes && (
                <div className="space-y-2 pt-2">
                    <Label htmlFor="variables_commune" className="text-xs">
                        Variables that trigger the town check
                    </Label>
                    <Input
                        id="variables_commune"
                        {...attributDeLongueur("variables_commune")}
                        aria-invalid={erreurVariablesCommune(reglages.variables_commune) ? true : undefined}
                        value={reglages.variables_commune}
                        onChange={(e) => onChange({ ...reglages, variables_commune: e.target.value })}
                    />
                    {erreurVariablesCommune(reglages.variables_commune) && (
                        <p className="text-xs text-destructive">
                            {erreurVariablesCommune(reglages.variables_commune)}
                        </p>
                    )}
                    <div className="space-y-1 text-xs text-muted-foreground">
                        <p>
                            Write the name of the variable that collects the town, exactly as it
                            appears in the step of the workflow: open the step, then{" "}
                            <em>Variables to Extract</em> and its <em>Variable Name</em>.
                        </p>
                        <p>Several names: separate them with commas.</p>
                        <p>
                            A <code>*</code> at the end means &quot;every name that starts
                            with&quot;: <code>adresse*</code> covers <code>adresse</code>,{" "}
                            <code>adresse_chantier</code>, <code>adresse_intervention</code>.
                        </p>
                        <p>
                            Example: <code>ville, lieu_chantier, adresse*</code>. Capitals and
                            spaces do not matter.
                        </p>
                        <p>
                            Leave empty to go back to the default:{" "}
                            <code>commune, commune_*, adresse*</code>.
                        </p>
                    </div>
                </div>
            )}
        </div>
    </div>
);
