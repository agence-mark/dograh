/**
 * [.mark] The Opening Hours card, rendered.
 *
 * The question this file answers, and only this one:
 *
 *     Does the card carry the typed hours out on save, clear them to null,
 *     keep every other setting, and SHOW a refusal with its line number?
 *
 * Whether the card is reachable on the settings page is a different question,
 * asked in `section-reglages-pipecat-montee.test.tsx` -- rendering a component
 * proves the component works, not that anyone can get to it (2026-09-14).
 */

import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { resolveWorkflowConfigurations } from "@/types/workflow-configurations";

import { EXEMPLE_HORAIRES, SectionHorairesOuverture } from "./SectionHorairesOuverture";

const toastMock = vi.hoisted(() => ({ success: vi.fn(), error: vi.fn() }));
vi.mock("sonner", () => ({ toast: toastMock }));

vi.mock("@/context/UnsavedChangesContext", () => ({
    useUnsavedChanges: () => undefined,
}));

beforeEach(() => {
    toastMock.success.mockClear();
    toastMock.error.mockClear();
});

const ouvrir = (
    configurations: Record<string, unknown> | null,
    onSave = vi.fn().mockResolvedValue(undefined),
) => {
    render(
        <SectionHorairesOuverture
            workflowConfigurations={resolveWorkflowConfigurations(configurations as never)}
            workflowName="Agent de test"
            onSave={onSave}
        />,
    );
    return onSave;
};

const champ = () => document.getElementById("horaires_ouverture") as HTMLTextAreaElement;
const enregistrer = () =>
    fireEvent.click(screen.getByRole("button", { name: /save opening hours/i }));

describe("[.mark] Opening Hours card", () => {
    it("is empty by default, with the Save button asleep", () => {
        ouvrir(null);
        expect(champ().value).toBe("");
        expect(
            (screen.getByRole("button", { name: /save opening hours/i }) as HTMLButtonElement)
                .disabled,
        ).toBe(true);
    });

    it("shows hours already saved", () => {
        ouvrir({ horaires_ouverture: EXEMPLE_HORAIRES });
        expect(champ().value).toBe(EXEMPLE_HORAIRES);
    });

    it("carries the typed hours out on save", async () => {
        const onSave = ouvrir(null);
        fireEvent.change(champ(), { target: { value: EXEMPLE_HORAIRES } });
        enregistrer();
        await waitFor(() => expect(onSave).toHaveBeenCalledTimes(1));
        expect(onSave.mock.calls[0][0].horaires_ouverture).toBe(EXEMPLE_HORAIRES);
        expect(onSave.mock.calls[0][1]).toBe("Agent de test");
    });

    it("saves null when the field is cleared", async () => {
        const onSave = ouvrir({ horaires_ouverture: EXEMPLE_HORAIRES });
        fireEvent.change(champ(), { target: { value: "   \n " } });
        enregistrer();
        await waitFor(() => expect(onSave).toHaveBeenCalledTimes(1));
        expect(onSave.mock.calls[0][0].horaires_ouverture).toBeNull();
    });

    it("keeps every other setting in the payload", async () => {
        const onSave = ouvrir({
            user_speech_timeout: 1.2,
            tts_replacements: ["SAV:S. A. V."],
            conversion_nombres_transcription: true,
            max_call_duration: 600,
        });
        fireEvent.change(champ(), { target: { value: EXEMPLE_HORAIRES } });
        enregistrer();
        await waitFor(() => expect(onSave).toHaveBeenCalledTimes(1));
        const charge = onSave.mock.calls[0][0];
        expect(charge.user_speech_timeout).toBe(1.2);
        expect(charge.tts_replacements).toEqual(["SAV:S. A. V."]);
        expect(charge.conversion_nombres_transcription).toBe(true);
        expect(charge.max_call_duration).toBe(600);
    });

    it("shows a 422 refusal under the field, with its line number", async () => {
        // What `saveWorkflowConfigurations` throws on a 422 from the validator.
        const onSave = vi
            .fn()
            .mockRejectedValue(new Error("Value error, ligne 2 : heure impossible « 25:00 »"));
        ouvrir(null, onSave);
        fireEvent.change(champ(), {
            target: { value: "lundi : fermé\nmardi : 10:00-25:00" },
        });
        enregistrer();
        const alerte = await screen.findByRole("alert");
        expect(alerte.textContent).toBe("ligne 2 : heure impossible « 25:00 »");
        expect(champ().getAttribute("aria-invalid")).toBe("true");
        expect(toastMock.success).not.toHaveBeenCalled();
    });

    it("strips the prefix on every line when several refusals are joined", async () => {
        const onSave = vi
            .fn()
            .mockRejectedValue(new Error("Value error, ligne 1 : x\nValue error, ligne 3 : y"));
        ouvrir(null, onSave);
        fireEvent.change(champ(), { target: { value: "lundi 10:00" } });
        enregistrer();
        const alerte = await screen.findByRole("alert");
        expect(alerte.textContent).toBe("ligne 1 : x\nligne 3 : y");
    });

    it("clears the refusal as soon as the entry is edited", async () => {
        const onSave = vi.fn().mockRejectedValue(new Error("Value error, ligne 1 : x"));
        ouvrir(null, onSave);
        fireEvent.change(champ(), { target: { value: "lundi 10:00" } });
        enregistrer();
        await screen.findByRole("alert");
        fireEvent.change(champ(), { target: { value: "lundi : 10:00-12:00" } });
        expect(screen.queryByRole("alert")).toBeNull();
    });
});
