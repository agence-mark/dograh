/**
 * [.mark] Les retraits de l'amont inutile (U1, sous-lot 3, carte de rangement `10`, liste « Retiré ») :
 * traceurs PostHog, Meta Pixel, Reo (et le gestionnaire de balises Google), Hire an Expert, encart Enterprise,
 * GitHub, Slack, bannière d'événement, Chatwoot, badge Update, /billing, /overview, /automation, Dograh Service
 * Keys, mode « modèles gérés par Dograh » et « Usage pricing », nœuds Noveum, Paygent et Tuner du menu d'ajout,
 * outil Native, /workflow/create amont.
 */
import { existsSync, readdirSync, readFileSync, statSync } from "node:fs";
import { join, relative, sep } from "node:path";

import { cleanup, render } from "@testing-library/react";
import { afterEach, beforeAll, describe, expect, it, vi } from "vitest";

import { TOOL_CATEGORIES } from "@/app/tools/config";
import type { NodeSpec } from "@/client/types.gen";
import { specsProposees } from "@/components/flow/menu-noeuds";

import { FournisseurLangue } from "../langue/langue";
import { ShellStudio } from "./shell-studio";

const UI = process.cwd();
const SRC = join(UI, "src");

const fichiers = (dossier: string): string[] =>
    readdirSync(dossier).flatMap((nom) => {
        const chemin = join(dossier, nom);
        if (statSync(chemin).isDirectory()) return nom === "client" && dossier === SRC ? [] : fichiers(chemin);
        return /\.(ts|tsx|css|json)$/.test(nom) ? [chemin] : [];
    });

/** Le code qui s'exécute (les tests, qui nomment ce qu'ils interdisent, et le dictionnaire de traduction, sont exclus). */
const sources = () =>
    fichiers(SRC)
        .filter((f) => !/\.test\.(ts|tsx)$/.test(f) && !f.endsWith("dictionnaire-dograh.json"))
        .map((f) => ({ f: relative(UI, f).split(sep).join("/"), texte: readFileSync(f, "utf8") }));

const TRACEURS = [
    /posthog/i,
    /\bfbq\b|connect\.facebook\.net|facebook\.com\/tr/i,
    /reo\.dev|ReoProvider|NEXT_PUBLIC_REO/i,
    /googletagmanager|GoogleTagManager|NEXT_PUBLIC_GTM_ID/i,
    /chatwoot/i,
];

vi.mock("next/navigation", () => ({ usePathname: () => "/workflow", useRouter: () => ({ push: vi.fn() }) }));
vi.mock("@/lib/auth", () => ({ useAuth: () => ({ provider: "local", logout: vi.fn(), user: { email: "a@b.c" } }) }));
vi.mock("@/context/TelephonyConfigWarningsContext", () => ({
    useTelephonyConfigWarnings: () => ({ telnyxMissingWebhookPublicKeyCount: 0, vonageMissingSignatureSecretCount: 0 }),
}));
vi.mock("@/components/layout/SidebarOrganizationSwitcher", () => ({ SidebarOrganizationSwitcher: () => <div /> }));
vi.mock("@/components/layout/SidebarTeamSwitcher", () => ({ SidebarTeamSwitcher: () => <div /> }));
vi.mock("@/components/ThemeSwitcher", () => ({ default: () => <span /> }));

beforeAll(() => {
    window.matchMedia =
        window.matchMedia ||
        ((query: string) =>
            ({ matches: false, media: query, addEventListener: () => {}, removeEventListener: () => {}, addListener: () => {}, removeListener: () => {} }) as unknown as MediaQueryList);
});
afterEach(cleanup);

describe("traceurs", () => {
    it("aucun import ni adresse de traceur dans ui/src, package.json ni next.config", () => {
        const trouves: string[] = [];
        for (const { f, texte } of sources()) {
            for (const motif of TRACEURS) if (motif.test(texte)) trouves.push(`${f} : ${motif}`);
        }
        for (const racine of ["package.json", "next.config.ts", "Dockerfile"]) {
            const texte = readFileSync(join(UI, racine), "utf8");
            for (const motif of TRACEURS) if (motif.test(texte)) trouves.push(`${racine} : ${motif}`);
        }
        expect(trouves).toEqual([]);
    });

    it("les fichiers des traceurs n'existent plus", () => {
        for (const f of [
            "components/PostHogIdentify.tsx", "components/MetaPixel.tsx", "components/ReoProvider.tsx",
            "lib/metaPixel.ts", "constants/posthog-events.ts", "app/api/config/posthog/route.ts",
            "components/ChatwootWidget.tsx", "components/EventBanner.tsx", "config/event-banner.config.ts",
        ]) {
            expect(existsSync(join(SRC, f)), f).toBe(false);
        }
    });

    it("le rendu du cadre n'ajoute ni script ni image ni feuille de style vers un tiers, et n'appelle aucun réseau", () => {
        const reseau = vi.fn(() => Promise.reject(new Error("réseau interdit")));
        vi.stubGlobal("fetch", reseau);
        render(
            <FournisseurLangue>
                <ShellStudio>
                    <p>page</p>
                </ShellStudio>
            </FournisseurLangue>,
        );
        const externes = [...document.querySelectorAll("script[src], link[href], img[src], iframe[src]")]
            .map((n) => n.getAttribute("src") ?? n.getAttribute("href") ?? "")
            .filter((u) => /^(https?:)?\/\//.test(u));
        expect(externes).toEqual([]);
        expect(reseau).not.toHaveBeenCalled();
        vi.unstubAllGlobals();
    });
});

describe("amont inutile", () => {
    it("les écrans et composants retirés n'existent plus", () => {
        for (const f of [
            "app/billing/page.tsx", "app/overview/page.tsx", "app/automation/page.tsx", "app/workflow/create/page.tsx",
            "components/lead-forms", "components/billing", "components/layout/AppSidebar.tsx",
            "components/layout/GitHubStarBadge.tsx", "hooks/useLatestReleaseVersion.ts", "context/LeadFormsContext.tsx",
        ]) {
            expect(existsSync(join(SRC, f)), f).toBe(false);
        }
    });

    it("plus de Hire an Expert, de Slack, de GitHub, de badge Update ni de Service Keys à l'écran", () => {
        const interdits = [/Hire an Expert|HireExpert/, /join\.slack\.com|Join Slack/, /GitHubStar|github\.com\/dograh/i, /docs\.dograh\.com\/deployment\/update/, /Dograh Service Keys|CreateServiceKey/];
        const trouves: string[] = [];
        for (const { f, texte } of sources()) {
            for (const motif of interdits) if (motif.test(texte)) trouves.push(`${f} : ${motif}`);
        }
        expect(trouves).toEqual([]);
    });

    it("plus de « Usage pricing » ni de mode géré par Dograh dans l'éditeur des modèles", () => {
        const texte = readFileSync(join(SRC, "components", "AIModelConfigurationV2Editor.tsx"), "utf8");
        expect(texte).not.toMatch(/Usage pricing|PricingSummary|TabsTrigger value="dograh"|managed transcriber/);
    });

    it("le menu d'ajout d'un nœud ne propose plus Noveum, Paygent, Tuner, le webhook de Dograh ni « Contrôle qualité » (un agent qui en porte déjà un le garde)", () => {
        const spec = (name: string) => ({ name, display_name: name, category: "integration" }) as unknown as NodeSpec;
        const proposees = specsProposees(["noveum", "paygent", "tuner", "webhook", "qa", "startCall"].map(spec)).map((s) => s.name);
        expect(proposees).toEqual(["startCall"]);
    });

    it("l'outil « Native (Coming Soon) » n'est plus proposé", () => {
        expect(TOOL_CATEGORIES.map((c) => c.value as string)).not.toContain("native");
    });

    it("la boîte d'erreur de clé ne parle plus de crédits ni de clé de service", () => {
        const texte = readFileSync(join(SRC, "app/workflow/[workflowId]/run/[runId]/components/ApiKeyErrorDialog.tsx"), "utf8");
        expect(texte).not.toMatch(/Billing|credits|Service Token|service_key/i);
    });
});
