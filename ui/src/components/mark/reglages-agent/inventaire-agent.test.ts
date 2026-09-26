/**
 * [.mark] Is every key of an agent's configuration on screen, or listed off
 * screen with its reason?
 *
 * Convention `reference/22-convention-ecran.md` § 6. The keys are read from the
 * three places that declare them, never from a list kept by hand:
 *
 *   - `api/schemas/workflow_configurations.py`, class WorkflowConfigurationDefaults
 *     (what the server validates and resolves);
 *   - `ui/src/types/workflow-configurations.ts`, type WorkflowConfigurations
 *     (what the screen types, keys added by Dograh or by us);
 *   - `ui/src/client/types.gen.ts`, type WorkflowConfigurationDefaults
 *     (the published spec).
 *
 * A key present in one of them and absent from `inventaire-agent.ts` fails.
 * A displayed key must name reference cases that exist, go to the same theme,
 * and whose frozen payload (`references/charges-utiles-agent.json`) really
 * changes that key: the inventory cannot claim a setting is on screen when no
 * gesture on the screen ever sent it.
 */
import { readFileSync } from "node:fs";
import { join } from "node:path";

import { describe, expect, it } from "vitest";

import { INVENTAIRE_AGENT } from "./inventaire-agent";
import { CAS_AGENT } from "./references/cas-agent";

const racine = join(process.cwd(), "..");
const lire = (chemin: string) => readFileSync(join(racine, chemin), "utf8");

const cles = (bloc: string, motif: RegExp) => [...bloc.matchAll(motif)].map((m) => m[1]);

const blocEntre = (texte: string, debut: string, fin: string | RegExp) => {
    const i = texte.indexOf(debut);
    if (i < 0) throw new Error(`"${debut}" not found: the schema moved, update this test.`);
    const reste = texte.slice(i + debut.length);
    const j = typeof fin === "string" ? reste.indexOf(fin) : reste.search(fin);
    return reste.slice(0, j < 0 ? undefined : j);
};

export const clesDesSchemasAgent = (): string[] => {
    const python = blocEntre(
        lire("api/schemas/workflow_configurations.py"),
        "class WorkflowConfigurationDefaults(",
        /\nclass /,
    );
    const type = blocEntre(
        lire("ui/src/types/workflow-configurations.ts"),
        "export type WorkflowConfigurations = ",
        "\n};",
    );
    const genere = blocEntre(
        lire("ui/src/client/types.gen.ts"),
        "export type WorkflowConfigurationDefaults = {",
        "\n};",
    );
    return [
        ...new Set([
            ...cles(python, /^ {4}([a-z_0-9]+)\s*:/gm),
            ...cles(type, /^ {4}([a-z_0-9]+)\??:/gm),
            ...cles(genere, /^ {4}([a-z_0-9]+)\??:/gm),
        ]),
    ].sort();
};

const references = JSON.parse(
    readFileSync(join(process.cwd(), "src/components/mark/reglages-agent/references/charges-utiles-agent.json"), "utf8"),
) as { cas: Record<string, { appels: Array<{ fonction: string; modifiees?: Record<string, unknown>; retirees?: string[]; variables?: unknown; dictionnaire?: unknown }> }> };

describe("inventory of the agent configuration", () => {
    it("reads a plausible number of keys from the schemas", () => {
        // A parse that silently found nothing would make every check below vacuous.
        expect(clesDesSchemasAgent().length).toBeGreaterThan(50);
    });

    it.each(clesDesSchemasAgent())("key %s is on screen or listed off screen", (cle) => {
        expect(INVENTAIRE_AGENT[cle], `${cle}: no entry in inventaire-agent.ts`).toBeDefined();
    });

    it.each(Object.entries(INVENTAIRE_AGENT))("entry %s is proven by its cases", (cle, entree) => {
        if ("horsEcran" in entree) {
            expect(entree.horsEcran.trim().length).toBeGreaterThan(10);
            return;
        }
        if ("via" in entree) {
            expect(entree.via.trim().length).toBeGreaterThan(10);
            return;
        }
        expect(entree.cas.length).toBeGreaterThan(0);
        for (const id of entree.cas) {
            const cas = CAS_AGENT.find((c) => c.id === id);
            expect(cas, `${cle}: case ${id} does not exist`).toBeDefined();
            expect(cas!.theme, `${cle}: case ${id} goes to another theme`).toBe(entree.theme);
            const reference = references.cas[id];
            expect(reference, `${cle}: case ${id} has no frozen payload`).toBeDefined();
            const touche = reference.appels.some((a) =>
                (cle === "dictionary" && a.fonction === "saveDictionary")
                || Object.keys(a.modifiees ?? {}).includes(cle)
                || (a.retirees ?? []).includes(cle),
            );
            expect(touche, `${cle}: the frozen payload of case ${id} never changes this key`).toBe(true);
        }
    });
});
