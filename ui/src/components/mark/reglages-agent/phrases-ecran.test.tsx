/**
 * [.mark] fiabilite-orchestration, lots 4 bis and 4 ter: the theme Phrases and the card of a call's page.
 *
 * | Test | The guarantee |
 * |---|---|
 * | taken over | the bridge phrase and the hand-over sentence set before show as group rules |
 * | saved | the save writes the rules in the server's shape and removes the old keys |
 * | refused | two rules of one cause at one place, an active rule without a sentence, a delay out of bounds |
 * | call page | each sentence said by the code is listed (cause, where, text); none: no card |
 */
import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it } from "vitest";

import { PhrasesDuCode, lirePhrasesDites } from "../groupe/PhrasesDuCode";
import { chargePhrases, erreursDesPhrases, extrairePhrases, MOTIFS_DE_PHRASES } from "./ThemePhrases";

afterEach(cleanup);

describe("[.mark] theme Phrases", () => {
    it("shows the former bridge phrase and hand-over sentence as group rules", () => {
        const { regles } = extrairePhrases({
            attente: { phrase_pont: "Une seconde.", delai_phrase_pont_s: 3 },
            transfert_humain: { phrase_mise_en_relation: "Je vous passe un collègue." },
        });
        expect(regles).toEqual([
            { motif: "passation_tarde", endroit: "groupe", variantes: ["Une seconde."], delai: "3", active: true },
            { motif: "mise_en_relation", endroit: "groupe", variantes: ["Je vous passe un collègue."], delai: "", active: true },
        ]);
        // A rule already written wins: the former value is not added twice.
        const deja = extrairePhrases({
            attente: { phrase_pont: "Une seconde." },
            phrases_regles: [{ motif: "passation_tarde", portee: "groupe", variantes: ["Neuf."] }],
        });
        expect(deja.regles.map((r) => r.variantes[0])).toEqual(["Neuf."]);
    });

    it("saves the rules in the server's shape", () => {
        expect(
            chargePhrases([
                { motif: "outil_tarde", endroit: "etape:Rendez-vous", variantes: [" Je  vérifie. ", "", "Je vérifie."], delai: "4,5", active: true },
                { motif: "connecteur_echoue", endroit: "agent", variantes: ["Je transmets."], delai: "9", active: false },
            ]),
        ).toEqual([
            { motif: "outil_tarde", portee: "etape", etape: "Rendez-vous", variantes: ["Je vérifie."], delai_s: 4.5, active: true },
            { motif: "connecteur_echoue", portee: "agent", etape: null, variantes: ["Je transmets."], delai_s: null, active: false },
        ]);
    });

    it("refuses two rules at one place, an active rule without sentence and a delay out of bounds", () => {
        const erreurs = erreursDesPhrases([
            { motif: "outil_tarde", endroit: "agent", variantes: ["A."], delai: "0.1", active: true },
            { motif: "outil_tarde", endroit: "agent", variantes: [], delai: "", active: true },
        ]);
        const messages = erreurs.map((e) => e.message.en);
        expect(messages).toContain("Two rules of this cause at the same place.");
        expect(messages).toContain("An active rule needs a sentence.");
        expect(messages.some((m) => m.startsWith("Delay between"))).toBe(true);
        expect(erreursDesPhrases([{ motif: "outil_tarde", endroit: "agent", variantes: [], delai: "", active: false }])).toEqual([]);
    });

    it("knows every cause of the code", () => {
        expect(MOTIFS_DE_PHRASES.map((m) => m.id)).toContain("appelant_se_tait");
    });
});

describe("[.mark] the call page lists the sentences said by the code", () => {
    it("lists each sentence, and draws nothing without one", () => {
        const contexte = {
            phrases_du_code: [
                { motif: "travail_dure", agent: 4, etape: "Créneaux", niveau: "defaut", texte: "C'est presque bon.", moment_s: 12.5 },
                "illisible",
            ],
        };
        expect(lirePhrasesDites(contexte)).toHaveLength(1);
        render(<PhrasesDuCode contexte={contexte} />);
        const ligne = document.querySelector('[data-phrase-dite="travail_dure"]');
        expect(ligne?.textContent).toContain("C'est presque bon.");
        expect(ligne?.textContent).toContain("Créneaux");
        cleanup();
        const { container } = render(<PhrasesDuCode contexte={{}} />);
        expect(container.innerHTML).toBe("");
        expect(screen.queryByText("Sentences said by the code")).toBeNull();
    });
});
