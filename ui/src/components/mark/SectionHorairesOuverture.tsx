"use client";

import { Clock } from "lucide-react";
import { useState } from "react";
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
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
import { useUnsavedChanges } from "@/context/UnsavedChangesContext";
import { detailFromError } from "@/lib/apiError";
import type { WorkflowConfigurations } from "@/types/workflow-configurations";

import { RAPPEL_PUBLICATION } from "./SectionReglagesPipecat";

/**
 * [.mark] The "Opening Hours" card of an agent's settings page.
 *
 * What it settles: on 2026-09-15 the agent's prompt said "the state of the
 * shop is given to you" and the value was EMPTY on every real call. The server
 * now computes that state at call start, from the hours typed here.
 *
 * The screen is in English (convention of the settings page); the hours are
 * typed in FRENCH, because the agent reads them back to French callers.
 *
 * ⛔ A bad entry is refused by the server with its line number. The refusal is
 * shown UNDER the field, not only in a toast: a toast disappears, and someone
 * who missed it would believe the hours were saved.
 */

export const ID_SECTION_HORAIRES_OUVERTURE = "opening-hours";

export const EXEMPLE_HORAIRES = `lundi : 10:00-18:30 sur rendez-vous
mardi : 10:00-12:30 et 14:00-18:30
mercredi : 10h-12h30, 14h-18h30
jeudi : 10:00-12:30 et 14:00-18:30
vendredi : 10:00-12:30 et 14:00-19:00
samedi : 10:00-19:00
dimanche : fermé
jours fériés : fermé
exceptions :
du 17/08/2026 au 22/08/2026 : fermé (congés d'été)
24/12/2026 : 10:00-16:00 (horaires réduits)
25/12 : fermé`;

interface SectionHorairesOuvertureProps {
    /** The RESOLVED configuration, as the page hands it to every other section. */
    workflowConfigurations: WorkflowConfigurations;
    workflowName: string;
    onSave: (
        configurations: WorkflowConfigurations,
        workflowName: string,
    ) => Promise<void>;
}

// FastAPI prefixes a validator's message; the line number is what matters.
const messageLisible = (erreur: unknown): string => {
    const brut = erreur instanceof Error && erreur.message
        ? erreur.message
        : detailFromError(erreur, "Opening hours not saved. Check the entry and try again.");
    // Several refusals come joined by line breaks: strip the prefix on each.
    return brut.replace(/^Value error,\s*/gm, "");
};

export const SectionHorairesOuverture = ({
    workflowConfigurations,
    workflowName,
    onSave,
}: SectionHorairesOuvertureProps) => {
    const enregistre = workflowConfigurations.horaires_ouverture ?? null;
    const [texte, setTexte] = useState<string>(enregistre ?? "");
    const [erreur, setErreur] = useState<string | null>(null);
    const [isSaving, setIsSaving] = useState(false);

    const aEnregistrer = texte.trim() || null;
    const isDirty = aEnregistrer !== enregistre;

    useUnsavedChanges(ID_SECTION_HORAIRES_OUVERTURE, isDirty);

    const handleSave = async () => {
        setIsSaving(true);
        setErreur(null);
        try {
            // The whole resolved configuration first, then our one key: a
            // setting saved by another card is not undone by this one.
            await onSave(
                { ...workflowConfigurations, horaires_ouverture: aEnregistrer },
                workflowName,
            );
            toast.success(`Opening hours saved. ${RAPPEL_PUBLICATION}`);
        } catch (e) {
            const message = messageLisible(e);
            setErreur(message);
            toast.error(`Opening hours not saved: ${message}`);
        } finally {
            setIsSaving(false);
        }
    };

    return (
        <Card id={ID_SECTION_HORAIRES_OUVERTURE}>
            <CardHeader>
                <CardTitle className="flex items-center gap-2 text-base">
                    <Clock className="h-4 w-4" />
                    Opening Hours
                </CardTitle>
                <CardDescription>
                    At the start of each call, the agent receives whether the business is
                    open, on a break, closed or by appointment only, and when it reopens:
                    {" "}<code className="rounded bg-muted px-1 text-xs">etat_ouverture</code>,
                    {" "}<code className="rounded bg-muted px-1 text-xs">reouverture</code>,
                    {" "}<code className="rounded bg-muted px-1 text-xs">horaires_ouverture</code> and
                    {" "}<code className="rounded bg-muted px-1 text-xs">annonce_ouverture</code>.
                    The last one is the ready-made sentence to say when picking up
                    (&laquo;&nbsp;Nous sommes fermés en ce moment, nous rouvrons&nbsp;&hellip;&nbsp;&raquo;),
                    empty when the business is reachable: paste
                    {" "}<code className="rounded bg-muted px-1 text-xs">{"{{initial_context.annonce_ouverture}}"}</code>
                    {" "}in the start node&apos;s greeting so the announcement no longer depends
                    on the model. Leave the hours empty and nothing is computed.
                </CardDescription>
            </CardHeader>
            <CardContent className="space-y-3">
                <Label htmlFor="horaires_ouverture" className="text-xs">
                    Opening hours, written in French
                </Label>
                <Textarea
                    id="horaires_ouverture"
                    className="font-mono text-xs"
                    rows={14}
                    maxLength={4000}
                    placeholder={EXEMPLE_HORAIRES}
                    aria-invalid={erreur ? true : undefined}
                    value={texte}
                    onChange={(e) => {
                        setTexte(e.target.value);
                        setErreur(null);
                    }}
                />
                {erreur && (
                    <p role="alert" className="text-xs text-destructive">
                        {erreur}
                    </p>
                )}
                <p className="text-xs text-muted-foreground">
                    One line per day, all seven required. A day is <code>fermé</code> or one or
                    more ranges (<code>10:00-12:30 et 14:00-18:30</code>, <code>10h-12h30</code>).
                    Add <code>sur rendez-vous</code> at the end of a day for appointment-only hours.
                    Public holidays are closed unless a <code>jours fériés</code> line says
                    otherwise. Under <code>exceptions :</code>, one date (<code>24/12/2026</code>,
                    or <code>25/12</code> every year) or period (<code>du … au …</code>) per line;
                    an exception wins over holidays and weekdays. Paris time.
                </p>
                <pre className="overflow-x-auto rounded bg-muted p-3 text-xs">{EXEMPLE_HORAIRES}</pre>
            </CardContent>
            <CardFooter className="justify-end gap-3 border-t pt-6">
                {isDirty && !erreur && (
                    <span className="text-xs text-muted-foreground">Unsaved changes</span>
                )}
                <Button onClick={handleSave} disabled={isSaving || !isDirty}>
                    {isSaving ? "Saving..." : "Save Opening Hours"}
                </Button>
            </CardFooter>
        </Card>
    );
};
