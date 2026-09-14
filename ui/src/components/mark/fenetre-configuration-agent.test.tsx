/**
 * [.mark] The agent's configuration dialog, rendered whole.
 *
 * The question this file answers, and only this one:
 *
 *     Are our sections actually MOUNTED in the dialog the client opens, and
 *     does saving carry their settings out unchanged?
 *
 * Why a second screen test, next to the per-section ones
 * -----------------------------------------------------
 * ⛔ Rendering a section on its own proves the section works. It does NOT
 * prove the section is on screen: deleting the one line that mounts it in
 * `ConfigurationsDialog.tsx` leaves every per-section test green. Measured on
 * 2026-09-14 while proving the rouge of `section-voix.test.tsx` — which is
 * exactly the shape of defect the screen lesson of 2026-09-10 warns about.
 *
 * 🔑 It also guards the other half: the dialog rebuilds the whole
 * configuration object on save. A section whose value is not spread into that
 * object renders perfectly and is thrown away on the way out, in silence.
 */

import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import { ConfigurationsDialog } from "@/app/workflow/[workflowId]/components/ConfigurationsDialog";

const organisation = { stt: { provider: "deepgram", model: "nova-3-general" } };

vi.mock("@/context/OrgConfigContext", () => ({
    useOrgConfig: () => ({
        externalPbxIntegrationsEnabled: false,
        userConfig: organisation,
    }),
}));

vi.stubGlobal(
    "ResizeObserver",
    class {
        observe() {}
        unobserve() {}
        disconnect() {}
    },
);

const ouvrir = (configurations: Record<string, unknown> | null, onSave = vi.fn()) => {
    render(
        <ConfigurationsDialog
            open
            onOpenChange={vi.fn()}
            workflowConfigurations={configurations as never}
            workflowName="Agent de test"
            onSave={onSave}
        />,
    );
    return onSave;
};

describe("Fenetre de configuration de l'agent", () => {
    it("monte la section Voix", () => {
        ouvrir(null);
        expect(
            screen.getByRole("switch", { name: /strip markdown before speaking/i }),
        ).toBeTruthy();
    });

    it("affiche le defaut d'aujourd'hui quand l'agent n'a rien rempli", () => {
        // 🔒 The markdown filter is absent from the pipeline today, so an agent
        // that never touched it must see the switch OFF. A switch drawn ON for
        // a setting that is OFF is worse than no switch at all.
        ouvrir(null);
        expect(
            screen
                .getByRole("switch", { name: /strip markdown before speaking/i })
                .getAttribute("aria-checked"),
        ).toBe("false");
    });

    it("affiche la valeur enregistree sur l'agent", () => {
        ouvrir({ tts_markdown_filter_enabled: true });
        expect(
            screen
                .getByRole("switch", { name: /strip markdown before speaking/i })
                .getAttribute("aria-checked"),
        ).toBe("true");
    });

    it("emporte le reglage dans l'enregistrement", async () => {
        const onSave = ouvrir(null);

        fireEvent.click(
            screen.getByRole("switch", { name: /strip markdown before speaking/i }),
        );
        fireEvent.click(screen.getByRole("button", { name: /save/i }));

        await waitFor(() => expect(onSave).toHaveBeenCalled());
        expect(onSave.mock.calls[0][0]).toMatchObject({
            tts_markdown_filter_enabled: true,
        });
    });

    it("monte la section Tour de parole avec les valeurs d'aujourd'hui", () => {
        ouvrir(null);
        expect(
            (document.getElementById("user_speech_timeout") as HTMLInputElement).value,
        ).toBe("0.6");
        expect(
            (document.getElementById("vad_stop_secs") as HTMLInputElement).value,
        ).toBe("0.2");
    });

    it("cache le tour de parole quand l'agent est sur un modele qui pilote ses tours", () => {
        ouvrir({
            model_overrides: { stt: { provider: "deepgram", model: "flux-general-en" } },
        });
        expect(document.getElementById("user_speech_timeout")).toBeNull();
    });

    it("emporte les reglages du tour de parole dans l'enregistrement", async () => {
        const onSave = ouvrir(null);

        fireEvent.change(document.getElementById("vad_stop_secs") as HTMLInputElement, {
            target: { value: "0.4" },
        });
        fireEvent.click(screen.getByRole("button", { name: /save/i }));

        await waitFor(() => expect(onSave).toHaveBeenCalled());
        expect(onSave.mock.calls[0][0]).toMatchObject({ vad_stop_secs: 0.4 });
    });

    it("enregistre les valeurs par defaut telles quelles, jamais des nuls", () => {
        // 🔒 An agent saved without touching anything must carry the values the
        // pipeline already runs with, not nulls that would later read as
        // "unset" and drift if a default moves.
        const onSave = ouvrir(null);

        fireEvent.click(screen.getByRole("button", { name: /save/i }));

        expect(onSave.mock.calls[0][0]).toMatchObject({
            user_speech_timeout: 0.6,
            vad_confidence: 0.7,
            audio_idle_timeout: 1,
            turn_wait_for_transcript: true,
            stt_ttfs_p99_latency: null,
        });
    });

    it("monte la section Relance avec les consignes d'aujourd'hui", () => {
        ouvrir(null);
        const consigne = document.getElementById("user_idle_prompt") as HTMLTextAreaElement;
        expect(consigne.value).toMatch(/politely and briefly ask if they're still there/i);
        expect(
            (document.getElementById("user_idle_max_prompts") as HTMLInputElement).value,
        ).toBe("1");
    });

    it("dit que les consignes de relance ne sont pas des phrases prononcees", () => {
        // ⚠️ Someone who types "Are you still there?" expecting that exact
        // sentence will hear something else, decide the field does not work,
        // and stop trusting the screen.
        ouvrir(null);
        expect(document.body.textContent).toMatch(
            /instructions given to the model, not sentences spoken word for word/i,
        );
    });

    it("emporte une consigne de relance modifiee dans l'enregistrement", async () => {
        const onSave = ouvrir(null);

        fireEvent.change(document.getElementById("user_idle_prompt") as HTMLTextAreaElement, {
            target: { value: "Demande si la personne est toujours la." },
        });
        fireEvent.click(screen.getByRole("button", { name: /save/i }));

        await waitFor(() => expect(onSave).toHaveBeenCalled());
        expect(onSave.mock.calls[0][0]).toMatchObject({
            user_idle_prompt: "Demande si la personne est toujours la.",
        });
    });

    it("cache la duree du silence tant que le silence n'est pas allume", () => {
        // 🚨 The duration was passed to sixteen voice providers and did
        // NOTHING: Pipecat pushes that silence only when the switch is on, and
        // nothing ever turned it on. Shown alone, someone would raise it, hear
        // no change, and stop trusting the screen.
        ouvrir(null);
        expect(document.getElementById("tts_silence_time_s")).toBeNull();

        fireEvent.click(
            screen.getByRole("switch", { name: /add silence after the agent speaks/i }),
        );
        expect(
            (document.getElementById("tts_silence_time_s") as HTMLInputElement).value,
        ).toBe("1");
    });

    it("emporte un reglage de voix modifie sans ecraser les autres sections", async () => {
        // 🚨 The defect of 2026-09-14: the turn-taking section carried every
        // Pipecat key, and its spread put the voice settings back to their
        // opening values. Both changes below have to survive the same save.
        const onSave = ouvrir(null);

        fireEvent.click(
            screen.getByRole("switch", { name: /strip markdown before speaking/i }),
        );
        fireEvent.change(document.getElementById("vad_stop_secs") as HTMLInputElement, {
            target: { value: "0.4" },
        });
        fireEvent.click(screen.getByRole("button", { name: /save/i }));

        await waitFor(() => expect(onSave).toHaveBeenCalled());
        expect(onSave.mock.calls[0][0]).toMatchObject({
            tts_markdown_filter_enabled: true,
            vad_stop_secs: 0.4,
        });
    });

    it("monte la section Interruptions avec les trois strategies d'aujourd'hui", () => {
        ouvrir(null);
        const etat = (id: string) =>
            document.getElementById(id)?.getAttribute('aria-checked');
        expect(etat('mute_until_first_bot_complete')).toBe('true');
        expect(etat('mute_during_function_call')).toBe('true');
        expect(etat('mute_engine_callback')).toBe('true');
        expect(etat('mute_first_speech')).toBe('false');
        expect(etat('mute_always')).toBe('false');
    });

    it('emporte une coupure de micro modifiee dans l enregistrement', async () => {
        const onSave = ouvrir(null);

        fireEvent.click(document.getElementById('mute_always') as HTMLElement);
        fireEvent.click(screen.getByRole('button', { name: /save/i }));

        await waitFor(() => expect(onSave).toHaveBeenCalled());
        expect(onSave.mock.calls[0][0]).toMatchObject({ mute_always: true });
    });

    it("n'efface pas un reglage que l'ecran ne connait pas", () => {
        // 🔑 The defect paid for on 2026-09-10: saving the configuration wiped
        // every per-service override, silently, on every save. The dialog
        // spreads the resolved configuration, so an unknown key must survive a
        // round trip untouched.
        const onSave = ouvrir({ mark_reglage_inconnu: "a garder" });

        fireEvent.click(screen.getByRole("button", { name: /save/i }));

        expect(onSave.mock.calls[0][0]).toMatchObject({
            mark_reglage_inconnu: "a garder",
        });
    });
});
