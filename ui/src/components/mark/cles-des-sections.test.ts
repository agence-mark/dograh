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
 */

import { describe, expect, it } from "vitest";

import {
    CLES_COUPURE,
    CLES_RELANCE,
    CLES_TOUR_DE_PAROLE,
    CLES_VOIX,
} from "@/app/workflow/[workflowId]/components/ConfigurationsDialog";
import { DEFAUTS_PIPECAT } from "@/types/workflow-configurations";

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
});
