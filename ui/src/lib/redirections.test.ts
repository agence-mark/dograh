// @vitest-environment node
/**
 * [.mark] Les nouvelles adresses et la table unique des redirections (U1, sous-lot 4).
 *
 * Inventaire : chaque ancienne adresse de `ui/src/app` doit avoir une page OU une redirection. Un test qui lit le
 * disque et échoue, avec le nom de l'adresse, si l'une n'a ni l'une ni l'autre ; et qui échoue aussi si une page
 * d'ancien nom reste sans redirection (une adresse oubliée qui garderait deux entrées).
 */
import { existsSync, readdirSync, statSync } from "node:fs";
import { join, relative, sep } from "node:path";

import { describe, expect, it } from "vitest";

import { MENU_CLIENT, MENU_LABO, toutesLesEntrees } from "@/components/mark/studio/navigation-studio";

import { destinationDe, REDIRECTIONS } from "./redirections";

const APP = join(process.cwd(), "src", "app");

/** Les adresses de l'écran avant U1 (relevé de `ui/src/app` au lot 0, `3400c569`), avec leurs segments dynamiques. */
const ANCIENNES_ADRESSES = [
    "/overview", "/automation", "/billing", "/workflow/create", "/workflow", "/workflow/[workflowId]",
    "/workflow/[workflowId]/runs", "/workflow/[workflowId]/settings", "/workflow/[workflowId]/tests",
    "/workflow/[workflowId]/run/[runId]", "/campaigns", "/campaigns/new", "/campaigns/[campaignId]",
    "/campaigns/[campaignId]/edit", "/model-configurations", "/cles", "/telephony-configurations",
    "/telephony-configurations/[configId]", "/tools", "/tools/[toolUuid]", "/files", "/recordings", "/api-keys",
    "/usage", "/reports", "/bibliotheque", "/a-trier", "/alertes", "/settings",
];

/** Les adresses qui gardent leur page : l'identification, l'accueil technique et les routes de service. */
const ADRESSES_QUI_RESTENT = ["/", "/after-sign-in", "/auth/login", "/auth/signup", "/handler/[...stack]", "/superadmin", "/superadmin/runs", "/impersonate"];

const NOUVELLES_RACINES = ["labo", "clients", "agents", "conversations"];

const exemple = (adresse: string) => adresse.replace(/\[[^\]]+\]/g, "7");

const routes = (dossier = APP): string[] =>
    readdirSync(dossier).flatMap((nom) => {
        const chemin = join(dossier, nom);
        if (statSync(chemin).isDirectory()) return routes(chemin);
        return /^(page\.tsx|route\.ts)$/.test(nom) ? [chemin] : [];
    });

const adresseDe = (fichier: string) =>
    "/" + relative(APP, fichier).split(sep).slice(0, -1).join("/");

/** Une adresse concrète a-t-elle une page : chaque segment est un dossier du même nom ou un dossier `[x]`. */
function pageExistePour(adresse: string, racine = APP): boolean {
    const segments = adresse.split("?")[0].split("/").filter(Boolean);
    const descendre = (dossier: string, i: number): boolean => {
        if (i === segments.length) return existsSync(join(dossier, "page.tsx")) || existsSync(join(dossier, "route.ts"));
        const enfants = readdirSync(dossier, { withFileTypes: true }).filter((d) => d.isDirectory()).map((d) => d.name);
        // Un dossier `[...x]` prend tout ce qui reste de l'adresse.
        if (enfants.some((n) => n.startsWith("[..."))) return true;
        const candidats = [segments[i], ...enfants.filter((n) => /^\[[^.\]]+\]$/.test(n))].filter((n) => enfants.includes(n));
        return candidats.some((n) => descendre(join(dossier, n), i + 1));
    };
    return descendre(racine, 0);
}

describe("redirections (U1)", () => {
    it("chaque ancienne adresse a une page ou une redirection", () => {
        const sansRien = [...ANCIENNES_ADRESSES, ...ADRESSES_QUI_RESTENT].filter(
            (a) => destinationDe(exemple(a)) === null && !pageExistePour(exemple(a)),
        );
        expect(sansRien).toEqual([]);
    });

    it("une ancienne adresse retirée n'a plus de page mais une redirection (billing, overview, automation, workflow/create)", () => {
        for (const a of ["/billing", "/overview", "/automation", "/workflow/create"]) {
            // Pas de dossier du même nom (un `[workflowId]` accepterait « create » : la redirection passe avant).
            expect(existsSync(join(APP, ...a.split("/").filter(Boolean), "page.tsx")), a).toBe(false);
            expect(destinationDe(a), a).toBe("/labo");
        }
    });

    it("aucune page d'un ancien nom ne reste sans redirection", () => {
        const orphelines = routes()
            .map(adresseDe)
            .filter((a) => !NOUVELLES_RACINES.includes(a.split("/")[1]))
            .filter((a) => !a.startsWith("/api/"))
            .filter((a) => !ADRESSES_QUI_RESTENT.includes(a))
            .filter((a) => destinationDe(exemple(a)) === null);
        expect(orphelines).toEqual([]);
    });

    it("chaque redirection mène à une page qui existe, sans rebond", () => {
        for (const { source, destination } of REDIRECTIONS) {
            const exempleDeLaSource = source.replace(/:[A-Za-z]+/g, "7");
            const cible = destinationDe(exempleDeLaSource);
            expect(cible, source).not.toBeNull();
            expect(pageExistePour(cible as string), `${source} -> ${destination}`).toBe(true);
            expect(destinationDe((cible as string).split("?")[0]), `${source} rebondit`).toBeNull();
        }
    });

    it("une conversation garde son agent dans l'adresse", () => {
        expect(destinationDe("/workflow/12/run/345")).toBe("/conversations/345?agent=12");
        expect(destinationDe("/workflow/12")).toBe("/agents/12");
        expect(destinationDe("/workflow/12/settings")).toBe("/agents/12/settings");
        expect(destinationDe("/workflow")).toBe("/labo/agents");
        expect(destinationDe("/workflow/create")).toBe("/labo");
    });

    it("une adresse nouvelle n'est pas redirigée", () => {
        for (const a of ["/labo", "/labo/agents", "/agents/12", "/conversations/9", "/clients/acme/agents"]) {
            expect(destinationDe(a), a).toBeNull();
        }
    });

    it("le menu mène à des pages qui existent, dans les deux espaces, détails compris", () => {
        for (const [groupes, base] of [[MENU_LABO, "/labo"], [MENU_CLIENT, "/clients/acme"]] as const) {
            for (const e of toutesLesEntrees(groupes)) {
                expect(pageExistePour(e.adresse(base)), e.adresse(base)).toBe(true);
                for (const s of e.sous ?? []) expect(pageExistePour(`${e.adresse(base)}/${s.suite.replace(/\[[^\]]+\]/g, "7")}`), s.suite).toBe(true);
            }
        }
    });

    it("les pages et les redirections sont dans la même table : next.config la lit", async () => {
        const { readFileSync } = await import("node:fs");
        const config = readFileSync(join(process.cwd(), "next.config.ts"), "utf8");
        expect(config).toContain('from "./src/lib/redirections"');
        expect(config).toMatch(/async redirects\(\)/);
        expect(config).toMatch(/permanent: false/);
    });
});
