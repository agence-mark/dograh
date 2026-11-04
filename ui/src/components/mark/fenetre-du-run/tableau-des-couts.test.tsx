/**
 * [.mark] Partie 3, lot 14 (SE-18, G-1) : le tableau « Coûts d'un appel » de la maquette, en tête de l'onglet Coûts.
 * Les quantités viennent de la consommation enregistrée ; le total n'existe que si une table de prix le donne.
 */
import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it } from "vitest";

import { FournisseurLangue } from "../langue/langue";
import { dureeCourte, TableauDesCouts } from "./TableauDesCouts";
import type { AnalyseDuRun } from "./types";

afterEach(cleanup);

const analyse = (extra: Record<string, unknown> = {}) =>
    ({
        summary: { status: "ok", duration_secs: 151, ...(extra.summary as object) },
        providers: {
            status: "ok",
            call_duration_secs: 151,
            transcription: { usage: [{ service: "stt", model: "m", seconds: 151 }] },
            model: { usage: [{ service: "llm", model: "m", prompt_tokens: 4812, completion_tokens: 611 }] },
            voice: { usage: [{ service: "tts", model: "m", characters: 1904 }] },
        },
    }) as unknown as AnalyseDuRun;

const monter = (a: AnalyseDuRun | null) =>
    render(
        <FournisseurLangue>
            <TableauDesCouts analyse={a} />
        </FournisseurLangue>,
    );

describe("[.mark] lot 14 : le tableau des coûts d'un appel", () => {
    it("montre cerveau, transcription, voix, téléphonie et total comme la maquette", () => {
        monter(analyse());
        const t = screen.getByTestId("tableau-des-couts").textContent!;
        expect(t).toContain("Coûts d'un appel");
        expect(t).toMatch(/Cerveau.*4.812 jetons en entrée · 611 en sortie/);
        expect(t).toMatch(/Transcription.*2 min 31/);
        expect(t).toMatch(/Voix.*1.904 caractères/);
        expect(t).toMatch(/Téléphonie.*2 min 31/);
        expect(screen.getByTestId("cout-total").textContent).toContain("selon la table de prix de l'organisation");
    });

    it("le total vient de la table de prix quand elle existe, jamais inventé", () => {
        monter(analyse({ summary: { status: "ok", duration_secs: 151, cost: { status: "ok", total: 0.1234, currency: "EUR", partial: true } } }));
        const total = screen.getByTestId("cout-total").textContent!;
        expect(total).toContain("0.1234 EUR");
        expect(total).toContain("partiel");
    });

    it("sans analyse lue, chaque ligne dit « non capté » au lieu d'un zéro", () => {
        monter(null);
        expect(screen.getByTestId("tableau-des-couts").textContent!.match(/non capté/g)!.length).toBe(4);
    });

    it("la durée courte compte minutes et secondes", () => {
        expect(dureeCourte(151, "fr")).toBe("2 min 31");
        expect(dureeCourte(9, "fr")).toBe("9 s");
        expect(dureeCourte(61, "fr")).toBe("1 min 01");
    });
});
