/**
 * [.mark] The Speech Tuning section of the agent settings page, rendered whole.
 *
 * The question this file answers, and only this one:
 *
 *     Are the four sections actually MOUNTED in the block Evan and Pierre
 *     open, and does saving carry their settings out unchanged?
 *
 * Why a screen test next to the per-section ones
 * ---------------------------------------------
 * Rendering a section on its own proves the section works. It does NOT prove
 * the section is on screen: deleting the one line that mounts it leaves every
 * per-section test green. Measured on 2026-09-14 while proving the rouge of
 * `section-voix.test.tsx`.
 *
 * It also guards the other half: the section rebuilds the whole configuration
 * object on save. A setting not spread into that object renders perfectly and
 * is thrown away on the way out, in silence.
 *
 * And the level ABOVE this one -- is this whole section reachable by clicking
 * in the application? -- is `section-reglages-pipecat-montee.test.tsx`. That
 * question is not asked here, and not asking it is what cost a chantier.
 */

import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import { resolveWorkflowConfigurations } from "@/types/workflow-configurations";

import { SectionReglagesPipecat } from "./SectionReglagesPipecat";

const organisation = { stt: { provider: "deepgram", model: "nova-3-general" } };

vi.mock("sonner", () => ({ toast: { success: vi.fn(), error: vi.fn() } }));

vi.mock("@/context/UnsavedChangesContext", () => ({
    useUnsavedChanges: () => undefined,
}));

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

// The page hands every section the RESOLVED configuration, so the harness
// resolves here too rather than letting the section guess a default.
const ouvrir = (configurations: Record<string, unknown> | null, onSave = vi.fn()) => {
    render(
        <SectionReglagesPipecat
            workflowConfigurations={resolveWorkflowConfigurations(configurations as never)}
            workflowName="Agent de test"
            onSave={onSave}
        />,
    );
    return onSave;
};

// The Save button only wakes up once something changed -- the pattern of every
// other section on that page. So a test about what the payload carries has to
// change something first, and the smallest honest change is this switch.
const toucherUnReglage = () =>
    fireEvent.click(
        screen.getByRole("switch", { name: /strip markdown before speaking/i }),
    );

describe("Section Reglages vocaux de la page de parametres", () => {
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

        toucherUnReglage();
        fireEvent.click(screen.getByRole("button", { name: /save/i }));

        expect(onSave.mock.calls[0][0]).toMatchObject({
            user_speech_timeout: 0.6,
            vad_confidence: 0.7,
            audio_idle_timeout: 1,
            turn_wait_for_transcript: true,
            stt_ttfs_p99_latency: null,
        });
    });

    it("n'ecrit PAS de plafond d'attente quand l'agent n'y a pas touche", () => {
        // 🚨 Le défaut bloquant du 14/09, relevé par la relecture. Ce réglage a
        // DEUX valeurs par défaut : 5 s normalement, 30 s quand la
        // transcription pilote elle-même les tours. En écrivant 5 à
        // l'enregistrement, ouvrir la fenêtre d'un agent Flux pour changer sa
        // voix faisait tomber son plafond de 30 s à 5 s -- depuis une section
        // que l'écran lui masque justement.
        const onSave = ouvrir(null);

        toucherUnReglage();
        fireEvent.click(screen.getByRole("button", { name: /save/i }));

        expect(onSave.mock.calls[0][0].user_turn_stop_timeout).toBeNull();
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

        toucherUnReglage();
        fireEvent.click(screen.getByRole("button", { name: /save/i }));

        expect(onSave.mock.calls[0][0]).toMatchObject({
            mark_reglage_inconnu: "a garder",
        });
    });
    it("laisse le bouton Enregistrer eteint tant que rien n a change", () => {
        // The pattern of every other section of that page, and it matters more
        // here than ailleurs: saving writes the whole RESOLVED configuration to
        // the database. A section that could be saved untouched would freeze
        // today's defaults on an agent that never asked for them, and a later
        // change of default would no longer reach it.
        ouvrir(null);
        expect(
            (screen.getByRole("button", { name: /save/i }) as HTMLButtonElement).disabled,
        ).toBe(true);

        toucherUnReglage();
        expect(
            (screen.getByRole("button", { name: /save/i }) as HTMLButtonElement).disabled,
        ).toBe(false);
    });

    it("ne revendique aucun reglage qui appartient a la section General", async () => {
        // The sections of that page each save {...toute la configuration,
        // ...leurs champs}. Two sections holding the same key would undo each
        // other's save, in silence. So ours must not carry General's.
        const onSave = ouvrir(null);

        toucherUnReglage();
        fireEvent.click(screen.getByRole("button", { name: /save/i }));
        await waitFor(() => expect(onSave).toHaveBeenCalled());

        // Untouched, so they leave exactly as they arrived -- the spread of the
        // resolved configuration, not a value this section decided.
        const envoye = onSave.mock.calls[0][0];
        const recu = resolveWorkflowConfigurations(null);
        for (const cle of [
            "max_call_duration",
            "max_user_idle_timeout",
            "smart_turn_stop_secs",
            "turn_start_strategy",
            "turn_start_min_words",
            "provisional_vad_pause_secs",
            "turn_stop_strategy",
            "context_compaction_enabled",
        ] as const) {
            expect(envoye[cle]).toEqual(recu[cle]);
        }
    });
});
