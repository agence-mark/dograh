/**
 * [.mark] The clerk's generic instructions on screen are the ones the code
 * plays (plan mode-prise-de-notes, part 2, D10). Read from the Python source,
 * never from a copy kept by hand: a change on one side only goes red here.
 */
import { readFileSync } from "node:fs";
import { join } from "node:path";

import { describe, expect, it } from "vitest";

import { CONSIGNE_GENERIQUE_GREFFIER } from "./consigne-greffier";

const duServeur = (): string => {
    const source = readFileSync(join(process.cwd(), "..", "api/services/pipecat/greffier.py"), "utf8");
    const debut = source.indexOf("CONSIGNE_GENERIQUE = (");
    if (debut < 0) throw new Error("CONSIGNE_GENERIQUE not found: the module moved, update this test.");
    const bloc = source.slice(debut).split(/\r?\n\)/)[0];
    return [...bloc.matchAll(/"((?:[^"\\]|\\.)*)"/g)].map((m) => JSON.parse(`"${m[1]}"`) as string).join("");
};

describe("the clerk's generic instructions", () => {
    it("are the ones the server plays, to the character", () => {
        const serveur = duServeur();
        expect(serveur.length).toBeGreaterThan(500);
        expect(CONSIGNE_GENERIQUE_GREFFIER).toBe(serveur);
    });
});
