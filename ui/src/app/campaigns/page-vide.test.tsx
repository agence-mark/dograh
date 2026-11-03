/**
 * [.mark] J (E102) : Campagnes sans campagne montre l'état vide `premier` (symbole et titre court), sans bouton
 * d'action dans la zone de la liste ; avec des campagnes, la liste reste.
 */
import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { FournisseurLangue } from "@/components/mark/langue/langue";

const m = vi.hoisted(() => ({ liste: vi.fn() }));
vi.mock("@/client/sdk.gen", () => ({ getCampaignsApiV1CampaignGet: m.liste }));
vi.mock("@/lib/auth", () => ({ useAuth: () => ({ user: { id: 1 }, loading: false, getAccessToken: async () => "t", redirectToLogin: vi.fn() }) }));
vi.mock("@/hooks/useOrganizationTimezone", () => ({ useOrganizationTimezone: () => "UTC" }));
vi.mock("next/navigation", () => ({ useRouter: () => ({ push: vi.fn() }) }));

import CampaignsPage from "./page";

afterEach(() => {
    cleanup();
    m.liste.mockReset();
});

describe("[.mark] J : Campagnes, états vides", () => {
    it("aucune campagne : un titre court, et plus le bouton « Create your first campaign »", async () => {
        m.liste.mockResolvedValue({ data: { campaigns: [] } });
        render(<FournisseurLangue><CampaignsPage /></FournisseurLangue>);
        expect(await screen.findByText("Aucune campagne pour l'instant")).toBeTruthy();
        expect(screen.queryByText(/Create your first campaign/)).toBeNull();
        expect(screen.queryByText(/No campaigns found/)).toBeNull();
    });
});
