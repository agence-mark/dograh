/**
 * [.mark] The Voice section of an agent's configuration, as seen on screen.
 *
 * The question this file answers, and only this one:
 *
 *     Is the markdown switch actually rendered, does it show the value it was
 *     handed, and does flipping it report the new value back?
 *
 * ⛔ This file RENDERS the component. A field declared in a Pydantic schema is
 * not a field on screen: the proof is a rendered switch, never a property
 * found in a JSON schema. Paid for on 2026-09-10, when declaring the fields
 * turned out not to be enough and their screen needed three fixes.
 */

import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import { type ReglagesVoix, SectionVoix } from "./SectionVoix";

// The values the pipeline ran with before the patch.
const VOIX_AUJOURDHUI: ReglagesVoix = {
    tts_markdown_filter_enabled: false,
    tts_push_silence_after_stop: false,
    tts_silence_time_s: 1,
    tts_text_aggregation_mode: 'sentence',
    tts_replacements: [],
    interdire_nom_appelant: false,
    interdire_civilite_appelant: false,
};

describe("Section Voix", () => {
    it("rend l'interrupteur du filtre de balisage", () => {
        render(
            <SectionVoix
                reglages={{ ...VOIX_AUJOURDHUI, tts_markdown_filter_enabled: false }}
                onChange={vi.fn()}
            />,
        );

        const interrupteur = screen.getByRole("switch", {
            name: /strip markdown before speaking/i,
        });
        expect(interrupteur).toBeTruthy();
        expect(interrupteur.getAttribute("aria-checked")).toBe("false");
    });

    it("affiche l'etat allume quand le reglage est allume", () => {
        render(
            <SectionVoix
                reglages={{ ...VOIX_AUJOURDHUI, tts_markdown_filter_enabled: true }}
                onChange={vi.fn()}
            />,
        );

        expect(
            screen
                .getByRole("switch", { name: /strip markdown before speaking/i })
                .getAttribute("aria-checked"),
        ).toBe("true");
    });

    it("remonte la nouvelle valeur quand on bascule l'interrupteur", () => {
        const onChange = vi.fn();
        render(
            <SectionVoix
                reglages={{ ...VOIX_AUJOURDHUI, tts_markdown_filter_enabled: false }}
                onChange={onChange}
            />,
        );

        fireEvent.click(
            screen.getByRole("switch", { name: /strip markdown before speaking/i }),
        );

        expect(onChange).toHaveBeenCalledWith(
            expect.objectContaining({ tts_markdown_filter_enabled: true }),
        );
    });

    it("dit ce que le filtre ne regle PAS", () => {
        // Written on screen on purpose: a parenthesised stage direction is
        // still spoken. Someone who turns the filter on and still hears
        // "(one moment, I'm transferring you)" must find the answer here and
        // not conclude the switch does nothing.
        render(
            <SectionVoix
                reglages={{ ...VOIX_AUJOURDHUI, tts_markdown_filter_enabled: true }}
                onChange={vi.fn()}
            />,
        );

        expect(document.body.textContent).toMatch(/does not touch parentheses/i);
    });
});

/**
 * [.mark] Les deux interrupteurs « nom et civilité » (chantier du 22/09).
 *
 * ⚠️ Ce qu'ils garantissent est vérifié côté serveur, sur le corpus réel des
 * phrases dites (`api/tests/mark/test_filtre_nom_civilite.py`). Ici on ne
 * répond qu'à la question de l'écran : sont-ils rendus, montrent-ils la valeur
 * qu'on leur donne, et rapportent-ils le changement ?
 */
describe("Section Voix — nom et civilité", () => {
    it("rend les deux interrupteurs, éteints quand ils le sont", () => {
        render(<SectionVoix reglages={VOIX_AUJOURDHUI} onChange={vi.fn()} />);

        expect(
            screen
                .getByRole("switch", { name: /never say the caller's name/i })
                .getAttribute("aria-checked"),
        ).toBe("false");
        expect(
            screen
                .getByRole("switch", { name: /never say monsieur, madame or mademoiselle/i })
                .getAttribute("aria-checked"),
        ).toBe("false");
    });

    it("rapporte l'allumage de chacun, séparément", () => {
        const onChange = vi.fn();
        render(<SectionVoix reglages={VOIX_AUJOURDHUI} onChange={onChange} />);

        fireEvent.click(screen.getByRole("switch", { name: /never say the caller's name/i }));

        expect(onChange).toHaveBeenCalledWith(
            expect.objectContaining({
                interdire_nom_appelant: true,
                interdire_civilite_appelant: false,
            }),
        );
    });

    it("affiche les limites et le pense-bête de rédaction", () => {
        // 🔑 Le pense-bête n'est pas décoratif : avec l'interrupteur du nom
        // allumé, un agent qui confirme en DISANT le nom pose une question qui
        // n'a plus d'objet (« c'est bien ? »).
        render(<SectionVoix reglages={VOIX_AUJOURDHUI} onChange={vi.fn()} />);

        const texte = document.body.textContent ?? "";
        expect(texte).toContain("first name is not filtered");
        expect(texte).toContain("SPELLED name is deliberately left alone");
        expect(texte).toContain("word by word");
        expect(texte).toContain("SPELLING it back");
    });

    it("avertit quand les interrupteurs sont allumés mais sans effet", () => {
        // ⛔ Le seul cas où un réglage allumé ne fait rien : en envoi mot à mot,
        // le nom est coupé entre deux morceaux. Le dire à l'écran, sinon on
        // croit avoir coupé la prononciation du nom.
        render(
            <SectionVoix
                reglages={{
                    ...VOIX_AUJOURDHUI,
                    tts_text_aggregation_mode: 'token',
                    interdire_nom_appelant: true,
                }}
                onChange={vi.fn()}
            />,
        );

        expect(document.body.textContent).toContain("Inert right now");
    });

    it("n'avertit pas quand le mode est phrase par phrase", () => {
        render(
            <SectionVoix
                reglages={{ ...VOIX_AUJOURDHUI, interdire_nom_appelant: true }}
                onChange={vi.fn()}
            />,
        );

        expect(document.body.textContent).not.toContain("Inert right now");
    });
});
