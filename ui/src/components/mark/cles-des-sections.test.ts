/**
 * [.mark] Do the configuration sections cover every Pipecat setting, exactly once?
 *
 * The question this file answers:
 *
 *     Does each section of the agent dialog own its own settings, with none
 *     forgotten and none claimed by two sections at the same time?
 *
 * Why it exists
 * -------------
 * 🚨 A real defect, measured on 2026-09-14. The turn-taking section took its
 * keys from `Object.keys(DEFAUTS_PIPECAT)`, which looked like the safe way to
 * avoid a list going stale. It meant that section carried EVERY Pipecat key,
 * voice settings included. On save the dialog spreads the sections in order,
 * so the turn-taking spread put the voice settings back to the values they
 * had when the dialog opened: flipping the markdown switch and saving stored
 * `false`, and the screen showed the switch on until the page was reloaded.
 *
 * ⛔ Nothing about that is visible. The field renders, the switch moves, the
 * save succeeds. Only the stored value is wrong. So the invariant is asserted
 * rather than trusted: a partition, not a set of overlapping lists.
 *
 * The same question, one level up (added 2026-09-14 with the move to the real
 * settings page): the sections of that page each save {...the whole resolved
 * configuration, ...their own fields}. Two sections holding the SAME key would
 * undo each other, in silence, exactly as the two spreads did inside the
 * dialog. So the partition is asserted against `GeneralSection` too -- read out
 * of their file, so that a key moved into General upstream breaks this test
 * instead of breaking an agent.
 */

import { readFileSync } from "node:fs";
import { join } from "node:path";

import { describe, expect, it } from "vitest";

import { DEFAUTS_PIPECAT } from "@/types/workflow-configurations";

import {
    CLES_COUPURE,
    CLES_RELANCE,
    CLES_TOUR_DE_PAROLE,
    CLES_VOIX,
} from "./SectionReglagesPipecat";

const TOUTES = [
    ...CLES_TOUR_DE_PAROLE,
    ...CLES_RELANCE,
    ...CLES_VOIX,
    ...CLES_COUPURE,
] as string[];

describe("Les cles des sections de la fenetre de configuration", () => {
    it("couvrent tous les reglages Pipecat", () => {
        const manquantes = Object.keys(DEFAUTS_PIPECAT).filter(
            (cle) => !TOUTES.includes(cle),
        );
        expect(manquantes).toEqual([]);
    });

    it("n'en revendiquent aucun deux fois", () => {
        const doublons = TOUTES.filter((cle, i) => TOUTES.indexOf(cle) !== i);
        expect(doublons).toEqual([]);
    });

    it("n'en revendiquent aucun qui n'existe pas", () => {
        const connues = Object.keys(DEFAUTS_PIPECAT);
        const inconnues = TOUTES.filter((cle) => !connues.includes(cle));
        expect(inconnues).toEqual([]);
    });

    it.each([
        ["GeneralSection", "function GeneralSection(", "function TemplateVariablesSection("],
        ["VoicemailSection", "function VoicemailSection(", "function withoutModelConfigurationOverrides("],
        ["WorkflowModelOverridesSection", "function WorkflowModelOverridesSection(", "function WorkflowSettingsPage("],
    ])("n'en revendiquent aucun que %s enregistre deja", (_nom, debutDeSection, finDeSection) => {
        // Read out of their page rather than copied into a list here: a list
        // copied by hand goes stale the day upstream adds a field to one of
        // these sections, and it would go stale silently.
        const page = readFileSync(
            join(process.cwd(), "src/app/workflow/[workflowId]/settings/page.tsx"),
            "utf8",
        );
        const iDebut = page.indexOf(debutDeSection);
        const iFin = page.indexOf(finDeSection);
        expect(iDebut, `${debutDeSection} introuvable`).toBeGreaterThan(-1);
        expect(iFin, `${finDeSection} introuvable`).toBeGreaterThan(iDebut);

        const section = page.slice(iDebut, iFin);
        // Every key this section writes, from each of its onSave payloads.
        const clesDeLaSection = [...section.matchAll(/onSave\(/g)].flatMap((m) => {
            const charge = section.slice(m.index!, m.index! + 2500);
            return [...charge.matchAll(/^\s+([a-z_][a-z0-9_]*):/gm)].map((k) => k[1]);
        });

        const collisions = TOUTES.filter((cle) => clesDeLaSection.includes(cle));
        expect(collisions).toEqual([]);
    });
});
