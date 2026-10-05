// @vitest-environment node
/**
 * [.mark] The warning after the graph is saved (plan porte-parlee, D3, D18).
 *
 *   - said only when the box can play (record on, Postscript, box on), the same
 *     rule as the code and as the settings screen;
 *   - names the steps without a first reply, in both languages;
 *   - the editor's save calls it AFTER a successful save and only warns.
 *
 * ⚠️ The editor's save hook is not rendered here (no test of this project plays
 * it for real: they all mock it). Its call is checked on the source, as the
 * Python side does for the phone's wiring.
 */
import { readFileSync } from "node:fs";
import { join } from "node:path";

import { describe, expect, it } from "vitest";

import { avertissementApresEnregistrement, DEBUT_AVERTISSEMENT } from "./avertir-premiere-replique";

const GRAPHE = {
    nodes: [
        { id: "start", type: "startCall", data: { name: "Accueil" } },
        { id: "etape", type: "agentNode", data: { name: "Panne", premiere_replique: "Quelle marque ?" } },
        { id: "fin", type: "endCall", data: { name: "Clôture" } },
    ],
    edges: [{ target: "etape" }, { target: "fin" }],
};
const ALLUMEE = { fiche_au_fil_de_leau: true, fiche_mode_de_note: "post_scriptum", portes_dans_la_reponse: true };

describe("[.mark] the warning after the graph is saved", () => {
    it("names the steps without a first reply, in the chosen language", () => {
        expect(avertissementApresEnregistrement(GRAPHE, ALLUMEE, "fr")).toBe(`${DEBUT_AVERTISSEMENT.fr}Clôture`);
        expect(avertissementApresEnregistrement(GRAPHE, ALLUMEE, "en")).toBe(`${DEBUT_AVERTISSEMENT.en}Clôture`);
    });

    it("says nothing when the box cannot play, or when every step has its reply", () => {
        for (const config of [
            { ...ALLUMEE, portes_dans_la_reponse: false },
            { ...ALLUMEE, fiche_mode_de_note: "outil" },
            { ...ALLUMEE, fiche_au_fil_de_leau: false },
            {},
            null,
        ]) {
            expect(avertissementApresEnregistrement(GRAPHE, config, "fr")).toBeNull();
        }
        const complet = { ...GRAPHE, nodes: GRAPHE.nodes.map((n) => ({ ...n, data: { ...n.data, premiere_replique: "Oui ?" } })) };
        expect(avertissementApresEnregistrement(complet, ALLUMEE, "fr")).toBeNull();
    });

    it("is called by the editor's save, after a successful save, as a warning only", () => {
        const source = readFileSync(join(process.cwd(), "src/app/workflow/[workflowId]/hooks/useWorkflowState.ts"), "utf8");
        const succes = source.indexOf("setIsDirty(false);");
        const appel = source.indexOf("avertissementApresEnregistrement(");
        const finDuSucces = source.indexOf("saveSucceeded = true;");
        expect(succes).toBeGreaterThan(-1);
        expect(appel).toBeGreaterThan(succes);
        expect(appel).toBeLessThan(finDuSucces);
        expect(source).toContain("if (avertissement) toast.warning(avertissement);");
    });
});
