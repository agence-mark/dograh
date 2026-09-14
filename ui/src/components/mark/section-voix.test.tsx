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

import { SectionVoix } from "./SectionVoix";

describe("Section Voix", () => {
    it("rend l'interrupteur du filtre de balisage", () => {
        render(
            <SectionVoix
                reglages={{ tts_markdown_filter_enabled: false }}
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
                reglages={{ tts_markdown_filter_enabled: true }}
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
                reglages={{ tts_markdown_filter_enabled: false }}
                onChange={onChange}
            />,
        );

        fireEvent.click(
            screen.getByRole("switch", { name: /strip markdown before speaking/i }),
        );

        expect(onChange).toHaveBeenCalledWith({ tts_markdown_filter_enabled: true });
    });

    it("dit ce que le filtre ne regle PAS", () => {
        // Written on screen on purpose: a parenthesised stage direction is
        // still spoken. Someone who turns the filter on and still hears
        // "(one moment, I'm transferring you)" must find the answer here and
        // not conclude the switch does nothing.
        render(
            <SectionVoix
                reglages={{ tts_markdown_filter_enabled: true }}
                onChange={vi.fn()}
            />,
        );

        expect(document.body.textContent).toMatch(/does not touch parentheses/i);
    });
});
