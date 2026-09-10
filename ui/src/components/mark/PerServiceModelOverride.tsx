"use client";

/**
 * [.mark] Per-service model override, back on the agent settings screen.
 *
 * Upstream removed this block from the agent screen on 2026-07-07, in a
 * billing clean-up, and kept only the all-or-nothing override: an agent either
 * follows the organization entirely, or carries a complete configuration of
 * its own. The server side was never removed — the field-by-field merge is on
 * the execution path and covered by a 600-line test file, with a test added a
 * month AFTER the screen was taken away.
 *
 * We need the middle ground: one client, one organization configuration, and
 * an agent that changes its voice only while still inheriting everything else.
 * A complete copy would freeze the model, the endpoints and the residency
 * settings of that client on the day it was written, and it would drift
 * silently the day the organization changes.
 *
 * ⛔ Kept in a file of our own on purpose. The block that used to live inside
 * their 1900-line page is reduced here to one import and one JSX line over
 * there: a conflict on an import line resolves itself, twenty lines in the
 * middle of their file do not.
 *
 * 🚨 The trap this component exists to make visible: the two override formats
 * never coexist. Saving either one wipes the other, and upstream does it with
 * no warning at all. So the switching is stated in plain words on screen, and
 * a save that destroys the other format says so before it happens.
 */

import { useState } from "react";
import { toast } from "sonner";

import { ServiceConfigurationForm } from "@/components/ServiceConfigurationForm";
import { Label } from "@/components/ui/label";
import { Switch } from "@/components/ui/switch";
import type { ModelOverrides, WorkflowConfigurations } from "@/types/workflow-configurations";

export interface PerServiceModelOverrideProps {
    workflowConfigurations: WorkflowConfigurations;
    workflowName: string;
    onSave: (configurations: WorkflowConfigurations, workflowName: string) => Promise<void>;
    /** Appended to the success toast, so the reminder reads like the rest of the page. */
    publishReminder: string;
}

/**
 * Marker read by the API's migration (DELIBERATE_PER_SERVICE_OVERRIDE_KEY in
 * api/services/configuration/ai_model_configuration.py).
 *
 * 🚨 Saving the organization's model configuration runs a migration over every
 * agent, which turns each per-service override into a frozen complete copy and
 * deletes it — on EVERY save, not once. Without this marker, an override set
 * here would be silently converted the next time the client's configuration is
 * touched, and the agent would stop inheriting anything.
 */
const DELIBERATE_OVERRIDE_KEY = "mark_per_service_override";

/**
 * Drop both override formats.
 *
 * Deliberately a local copy of the page's own helper rather than an import of
 * it: the point of this file is to touch their page as little as possible, and
 * three lines duplicated cost less than a symbol that has to be exported from
 * a file we would rather not edit.
 */
function withoutAnyOverride(configurations: WorkflowConfigurations): WorkflowConfigurations {
    const next = { ...configurations };
    delete next.model_overrides;
    delete next.model_configuration_v2_override;
    delete next[DELIBERATE_OVERRIDE_KEY];
    return next;
}

export function PerServiceModelOverride({
    workflowConfigurations,
    workflowName,
    onSave,
    publishReminder,
}: PerServiceModelOverrideProps) {
    const savedOverrides = workflowConfigurations.model_overrides;
    const hasFullOverride = Boolean(workflowConfigurations.model_configuration_v2_override);
    const [enabled, setEnabled] = useState(Boolean(savedOverrides));
    const [isRemoving, setIsRemoving] = useState(false);

    const saveOverrides = async (config: Record<string, unknown>) => {
        const next = withoutAnyOverride(workflowConfigurations);
        const modelOverrides = config.model_overrides as ModelOverrides | undefined;
        if (modelOverrides) {
            next.model_overrides = modelOverrides;
            next[DELIBERATE_OVERRIDE_KEY] = true;
        }
        await onSave(next, workflowName);
        toast.success(`Per-service override saved. ${publishReminder}`);
    };

    const removeOverrides = async () => {
        setIsRemoving(true);
        try {
            await onSave(withoutAnyOverride(workflowConfigurations), workflowName);
            setEnabled(false);
            toast.success(`Per-service override removed. ${publishReminder}`);
        } finally {
            setIsRemoving(false);
        }
    };

    return (
        <div className="space-y-4 rounded-md border p-4" data-testid="per-service-override">
            <div className="flex items-center justify-between">
                <div className="space-y-0.5">
                    <Label htmlFor="per-service-override-toggle" className="text-sm font-medium">
                        Override individual services
                    </Label>
                    <p className="text-xs text-muted-foreground">
                        {enabled
                            ? "This agent replaces only the services you enable below, and inherits the rest from the organization."
                            : "Change one service (the voice, say) and keep inheriting everything else from the organization."}
                    </p>
                </div>
                <Switch
                    id="per-service-override-toggle"
                    checked={enabled}
                    onCheckedChange={setEnabled}
                    disabled={isRemoving}
                />
            </div>

            {/* 🚨 The silent part, said out loud. */}
            {enabled && hasFullOverride && (
                <p className="rounded-md border border-destructive/40 bg-destructive/10 px-3 py-2 text-xs text-destructive">
                    This agent currently carries a complete configuration of its own. The two
                    override formats never coexist: saving here removes that complete
                    configuration.
                </p>
            )}

            {enabled && (
                <ServiceConfigurationForm
                    mode="override"
                    currentOverrides={savedOverrides}
                    submitLabel="Save Per-Service Override"
                    onSave={saveOverrides}
                />
            )}

            {!enabled && savedOverrides && (
                <button
                    type="button"
                    className="text-xs underline text-muted-foreground"
                    onClick={removeOverrides}
                    disabled={isRemoving}
                >
                    {isRemoving ? "Removing..." : "Remove the saved per-service override"}
                </button>
            )}
        </div>
    );
}
