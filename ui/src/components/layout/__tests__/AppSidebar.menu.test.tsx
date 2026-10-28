/**
 * [.mark] passages-fiables: the « Alerts » entry of the side menu must stay reachable.
 *
 * Reported on 29/10: at 900 px high the entry « Alerts » (last of MANAGE) sat below the foot of the sidebar, and the
 * scrollbar is hidden by design (D8), so it looked missing. jsdom has no layout, so this file pins what keeps it in view:
 * the entries exist in both languages, they sit inside the one scrolling container (`min-h-0 flex-1 overflow-auto`, so
 * the footer never covers them), and the groups use the compact spacing that makes the whole menu fit in 900 px.
 */
import { cleanup, render, screen } from "@testing-library/react";
import React, { type ReactNode } from "react";
import { afterEach, beforeAll, describe, expect, it, vi } from "vitest";

import { FournisseurLangue } from "@/components/mark/langue/langue";
import { SidebarProvider } from "@/components/ui/sidebar";

import { AppSidebar } from "../AppSidebar";

vi.mock("next/navigation", () => ({ usePathname: () => "/overview", useRouter: () => ({ push: vi.fn() }) }));
vi.mock("@/lib/auth", () => ({ useAuth: () => ({ provider: "local", logout: vi.fn(), user: { email: "a@b.c" } }) }));
vi.mock("@/context/AppConfigContext", () => ({ useAppConfig: () => ({ config: null }) }));
vi.mock("@/context/LeadFormsContext", () => ({ useLeadForms: () => ({ openHireExpert: vi.fn() }) }));
vi.mock("@/context/TelephonyConfigWarningsContext", () => ({
    useTelephonyConfigWarnings: () => ({ telnyxMissingWebhookPublicKeyCount: 0, vonageMissingSignatureSecretCount: 0 }),
}));
vi.mock("@/hooks/useLatestReleaseVersion", () => ({
    useLatestReleaseVersion: () => ({ latest: null, isBehind: false, isLatest: false }),
}));
vi.mock("@/components/BrandLogo", () => ({ BrandLogo: () => <span /> }));
vi.mock("@/components/layout/SidebarOrganizationSwitcher", () => ({ SidebarOrganizationSwitcher: () => <div /> }));
vi.mock("@/components/layout/SidebarTeamSwitcher", () => ({ SidebarTeamSwitcher: () => <div /> }));
vi.mock("@/components/mark/langue/BoutonLangue", () => ({ BoutonLangue: () => <span /> }));
vi.mock("@/components/ThemeSwitcher", () => ({ default: () => <span /> }));
vi.mock("@/components/ui/dropdown-menu", () => ({
    DropdownMenu: ({ children }: { children: ReactNode }) => <div>{children}</div>,
    DropdownMenuTrigger: ({ children }: { children: ReactNode }) => <div>{children}</div>,
    DropdownMenuContent: ({ children }: { children: ReactNode }) => <div>{children}</div>,
    DropdownMenuItem: ({ children }: { children: ReactNode }) => <div>{children}</div>,
    DropdownMenuLabel: ({ children }: { children: ReactNode }) => <div>{children}</div>,
    DropdownMenuSeparator: () => <hr />,
}));

beforeAll(() => {
    window.matchMedia =
        window.matchMedia ||
        ((query: string) =>
            ({ matches: false, media: query, addEventListener: () => {}, removeEventListener: () => {}, addListener: () => {}, removeListener: () => {} }) as unknown as MediaQueryList);
});
afterEach(() => {
    cleanup();
    window.localStorage.clear();
});

const monter = (francais: boolean) => {
    if (francais) window.localStorage.setItem("mark-langue", "fr");
    return render(
        <FournisseurLangue>
            <SidebarProvider>
                <AppSidebar />
            </SidebarProvider>
        </FournisseurLangue>,
    );
};

describe("[.mark] the side menu keeps « Alerts » reachable", () => {
    it("lists « To triage » and « Alerts » inside the scrolling content, before the footer", () => {
        monter(false);
        const alertes = screen.getByRole("link", { name: /Alerts|Alertes/ });
        const contenu = alertes.closest('[data-slot="sidebar-content"]') as HTMLElement;
        expect(contenu).not.toBeNull();
        expect(contenu.className).toMatch(/\bmin-h-0\b/);
        expect(contenu.className).toMatch(/\bflex-1\b/);
        expect(contenu.className).toMatch(/\boverflow-auto\b/);
        const pied = document.querySelector('[data-slot="sidebar-footer"]') as HTMLElement;
        expect(contenu.contains(pied)).toBe(false);
        expect(alertes.getAttribute("href")).toBe("/alertes");
        expect(screen.getByRole("link", { name: /To triage|À trier/ }).getAttribute("href")).toBe("/a-trier");
    });

    it("uses compact groups so the whole menu fits in 900 px", () => {
        monter(false);
        const groupes = [...document.querySelectorAll('[data-slot="sidebar-group"]')] as HTMLElement[];
        expect(groupes).toHaveLength(3);
        for (const g of groupes) expect(g.className).toMatch(/\bpy-1\b/);
        // no group is separated from the previous one by more than 12 px (mt-6 = 24 px took the room of an entry)
        for (const g of groupes) expect(g.className).not.toMatch(/\bmt-6\b/);
    });
});
