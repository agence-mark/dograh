/**
 * [.mark] Is every organization setting on screen, or listed off screen with
 * its reason? Keys read from the generated client (the published spec of the
 * two routes), never from a list kept by hand; a displayed key must name
 * reference cases whose frozen payload really changes it.
 */
import { readFileSync } from "node:fs";
import { join } from "node:path";

import { describe, expect, it } from "vitest";

import {
    type EntreeInventaireOrganisation,
    INVENTAIRE_ANNONCE,
    INVENTAIRE_PREFERENCES,
} from "./inventaire-organisation";
import { CAS_ORGANISATION } from "./references/cas-organisation";

const genere = readFileSync(join(process.cwd(), "src/client/types.gen.ts"), "utf8");

const clesDuType = (nom: string): string[] => {
    const debut = `export type ${nom} = {`;
    const i = genere.indexOf(debut);
    if (i < 0) throw new Error(`${nom} not found in types.gen.ts: update this test.`);
    const bloc = genere.slice(i + debut.length, genere.indexOf("\n};", i));
    return [...bloc.matchAll(/^ {4}([a-z_0-9]+)\??:/gm)].map((m) => m[1]);
};

const references = JSON.parse(
    readFileSync(
        join(process.cwd(), "src/components/mark/parametres-organisation/references/charges-utiles-organisation.json"),
        "utf8",
    ),
) as {
    preferences: Record<string, unknown>;
    annonce: Record<string, unknown>;
    cas: Record<string, { appels: Array<{ route: "preferences" | "annonce"; corps: Record<string, unknown> }> }>;
};

const verifier = (
    type: string,
    route: "preferences" | "annonce",
    inventaire: Record<string, EntreeInventaireOrganisation>,
) => {
    describe(`inventory of ${type}`, () => {
        it("reads keys from the published spec", () => {
            expect(clesDuType(type).length).toBeGreaterThan(3);
        });

        it.each(clesDuType(type))("key %s is on screen or listed off screen", (cle) => {
            expect(inventaire[cle], `${cle}: no entry in inventaire-organisation.ts`).toBeDefined();
        });

        it.each(Object.entries(inventaire))("entry %s is proven by its cases", (cle, entree) => {
            if ("horsEcran" in entree) {
                expect(entree.horsEcran.trim().length).toBeGreaterThan(10);
                return;
            }
            for (const id of entree.cas) {
                const cas = CAS_ORGANISATION.find((c) => c.id === id);
                expect(cas, `${cle}: case ${id} does not exist`).toBeDefined();
                expect(cas!.theme).toBe(entree.theme);
                const base = references[route];
                const touche = references.cas[id].appels.some(
                    (a) => a.route === route && JSON.stringify(a.corps[cle]) !== JSON.stringify(base[cle]),
                );
                expect(touche, `${cle}: the frozen payload of case ${id} never changes this key`).toBe(true);
            }
        });
    });
};

verifier("OrganizationPreferences", "preferences", INVENTAIRE_PREFERENCES);
verifier("ReglagesAnnonceOuverture", "annonce", INVENTAIRE_ANNONCE);
