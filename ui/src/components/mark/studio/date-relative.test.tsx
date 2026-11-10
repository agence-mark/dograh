/**
 * [.mark] Partie 3, sous-lot 11 (SE-17, F-5) : la date relative, partout la même, avec la date complète au survol.
 */
import { cleanup, render } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { DateRelative } from "./date-relative";

// L'horloge est figée : sans ça, le test dépend de l'heure à laquelle il tourne (rouge juste après minuit).
beforeEach(() => {
    vi.useFakeTimers({ toFake: ["Date"] });
    vi.setSystemTime(new Date("2026-06-15T15:00:00Z"));
});

afterEach(() => {
    vi.useRealTimers();
    cleanup();
});

describe("DateRelative", () => {
    it("dit « today » ou « yesterday » avec l'heure, et porte la date complète au survol", () => {
        const midi = new Date();
        midi.setHours(12, 0, 0, 0);
        const hier = new Date(midi.getTime() - 24 * 3600 * 1000);
        const { container, rerender } = render(<DateRelative valeur={midi.toISOString()} fuseau="UTC" />);
        const aujourdhui = container.querySelector("time") as HTMLTimeElement;
        expect(aujourdhui.textContent).toMatch(/^(today|yesterday) \d{2}:\d{2}$/);
        expect(aujourdhui.getAttribute("title")).toMatch(/\d{4}/); // l'année, donc la date complète
        expect(aujourdhui.getAttribute("datetime")).toBe(midi.toISOString());
        rerender(<DateRelative valeur={hier.toISOString()} fuseau="UTC" />);
        expect(container.querySelector("time")?.textContent).toMatch(/^(yesterday|[A-Z][a-z]{2} \d{1,2}) \d{2}:\d{2}$/);
    });

    it("une date d'un autre jour est dite jour/mois (anglais : « Mar 4 ») ; une date absente ou illisible ne dessine rien", () => {
        const { container, rerender } = render(<DateRelative valeur="2020-03-04T10:30:00Z" fuseau="UTC" />);
        expect(container.querySelector("time")?.textContent).toBe("Mar 4 10:30"); // anglais : « Mar 4 » (R-1)
        rerender(<DateRelative valeur={null} />);
        expect(container.querySelector("time")).toBeNull();
        rerender(<DateRelative valeur="pas une date" vide="–" />);
        expect(container.textContent).toBe("–");
    });
});
