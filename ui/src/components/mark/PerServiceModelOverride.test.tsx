/**
 * [.mark] The per-service override block, and the trap it makes visible.
 *
 * The question this file answers, and it answers only this one:
 *
 *     Can an agent replace one service and keep inheriting the rest, and is
 *     the destruction of the other override format announced before it
 *     happens rather than after?
 *
 * Why it exists
 * -------------
 * Upstream saves either format by first deleting both. So saving a per-service
 * override silently throws away a complete configuration, and vice versa. The
 * loss is invisible: the screen redraws, the toast says success, and the
 * setting that governed the agent is gone.
 */

import { readFileSync } from "node:fs";
import { join } from "node:path";

import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import type { WorkflowConfigurations } from "@/types/workflow-configurations";

import { PerServiceModelOverride } from "./PerServiceModelOverride";

vi.mock("sonner", () => ({ toast: { success: vi.fn(), error: vi.fn() } }));

vi.mock("@/context/UserConfigContext", () => ({
    useUserConfig: () => ({ userConfig: null, refreshConfig: vi.fn() }),
}));

vi.stubGlobal(
    "ResizeObserver",
    class {
        observe() { }
        unobserve() { }
        disconnect() { }
    },
);

// The form itself is covered by its own file; here it only has to be a thing
// that can call back with a payload, so the assertions stay on what THIS
// component does with that payload.
vi.mock("@/components/ServiceConfigurationForm", () => ({
    ServiceConfigurationForm: ({
        onSave,
        submitLabel,
    }: {
        onSave: (config: Record<string, unknown>) => Promise<void>;
        submitLabel?: string;
    }) => (
        <button
            type="button"
            onClick={() => onSave({ model_overrides: { tts: { provider: "mistral", voice: "fr_marie_neutral" } } })}
        >
            {submitLabel}
        </button>
    ),
}));

function configurations(extra: Partial<WorkflowConfigurations> = {}): WorkflowConfigurations {
    return { context_compaction_enabled: false, ...extra } as unknown as WorkflowConfigurations;
}

function afficher(config: WorkflowConfigurations, onSave = vi.fn().mockResolvedValue(undefined)) {
    render(
        <PerServiceModelOverride
            workflowConfigurations={config}
            workflowName="Agent Nuances de Feu"
            onSave={onSave}
            publishReminder="Publish the agent to apply the changes."
        />,
    );
    return onSave;
}

describe("[.mark] per-service override", () => {
    it("stays closed until the switch is turned on", () => {
        afficher(configurations());

        expect(screen.queryByText("Save Per-Service Override")).toBeNull();

        fireEvent.click(screen.getByRole("switch"));

        expect(screen.getByText("Save Per-Service Override")).toBeTruthy();
    });

    it("opens already on when an override is saved", () => {
        afficher(configurations({ model_overrides: { tts: { provider: "mistral" } } }));

        expect(screen.getByText("Save Per-Service Override")).toBeTruthy();
    });

    it("saves the override without touching the rest of the configuration", async () => {
        const onSave = afficher(configurations({ context_compaction_enabled: true }));

        fireEvent.click(screen.getByRole("switch"));
        fireEvent.click(screen.getByText("Save Per-Service Override"));

        await waitFor(() => expect(onSave).toHaveBeenCalled());

        const [envoye, nom] = onSave.mock.calls[0];
        expect(envoye.model_overrides).toEqual({
            tts: { provider: "mistral", voice: "fr_marie_neutral" },
        });
        expect(envoye.context_compaction_enabled).toBe(true);
        expect(nom).toBe("Agent Nuances de Feu");
    });

    it("warns BEFORE saving that a complete configuration will be dropped", () => {
        afficher(
            configurations({
                model_configuration_v2_override: { llm: { provider: "mistral" } } as never,
            }),
        );

        fireEvent.click(screen.getByRole("switch"));

        // ⛔ The assertion is on the word "removes", not merely on some text
        // being present: the point is that the destruction is announced, in
        // the present tense, before the click that performs it.
        expect(screen.getByText((texte) => /never coexist[\s\S]*removes that complete/i.test(texte))).toBeTruthy();
    });

    it("does drop the complete configuration when it saves", async () => {
        const onSave = afficher(
            configurations({
                model_configuration_v2_override: { llm: { provider: "mistral" } } as never,
            }),
        );

        fireEvent.click(screen.getByRole("switch"));
        fireEvent.click(screen.getByText("Save Per-Service Override"));

        await waitFor(() => expect(onSave).toHaveBeenCalled());

        // The warning above would be a lie if this were not true.
        expect("model_configuration_v2_override" in onSave.mock.calls[0][0]).toBe(false);
    });

    it("removes a saved override on demand", async () => {
        const onSave = afficher(configurations({ model_overrides: { tts: { provider: "mistral" } } }));

        fireEvent.click(screen.getByRole("switch"));
        fireEvent.click(screen.getByText("Remove the saved per-service override"));

        await waitFor(() => expect(onSave).toHaveBeenCalled());

        expect("model_overrides" in onSave.mock.calls[0][0]).toBe(false);
    });

    it("marks the override as deliberate, so the next client save spares it", async () => {
        const onSave = afficher(configurations());

        fireEvent.click(screen.getByRole("switch"));
        fireEvent.click(screen.getByText("Save Per-Service Override"));

        await waitFor(() => expect(onSave).toHaveBeenCalled());

        // 🚨 Without this key, saving the client's model configuration converts
        // this override into a frozen copy and deletes it — silently, and on
        // every save, not once.
        expect(onSave.mock.calls[0][0].mark_per_service_override).toBe(true);
    });

    it("takes the marker away with the override", async () => {
        const onSave = afficher(
            configurations({
                model_overrides: { tts: { provider: "mistral" } },
                mark_per_service_override: true,
            }),
        );

        fireEvent.click(screen.getByRole("switch"));
        fireEvent.click(screen.getByText("Remove the saved per-service override"));

        await waitFor(() => expect(onSave).toHaveBeenCalled());

        // A marker left behind would freeze the migration for an agent that no
        // longer overrides anything.
        expect("mark_per_service_override" in onSave.mock.calls[0][0]).toBe(false);
    });

    it("is actually mounted on the agent settings screen", () => {
        // ⚠️ Read honestly: this reads their page rather than rendering it
        // (it needs auth, routing and three fetches). It catches the failure
        // that threatens us — an upstream rewrite of that page dropping our
        // one-line mount, which no other test would notice.
        // vitest runs with the ui/ package as its working directory.
        const page = readFileSync(
            join(process.cwd(), "src/app/workflow/[workflowId]/settings/page.tsx"),
            "utf8",
        );

        expect(page).toContain('from "@/components/mark/PerServiceModelOverride"');
        expect(page).toContain("<PerServiceModelOverride");
    });
});
