/**
 * [.mark] J (E102) : Campagnes sans campagne montre l'état vide `premier` (symbole et titre court), sans bouton
 * d'action dans la zone de la liste ; avec des campagnes, la liste reste.
 */
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { FournisseurLangue } from "@/components/mark/langue/langue";

const m = vi.hoisted(() => ({ liste: vi.fn(), push: vi.fn() }));
vi.mock("@/client/sdk.gen", () => ({ getCampaignsApiV1CampaignGet: m.liste }));
vi.mock("@/lib/auth", () => ({ useAuth: () => ({ user: { id: 1 }, loading: false, getAccessToken: async () => "t", redirectToLogin: vi.fn() }) }));
vi.mock("@/hooks/useOrganizationTimezone", () => ({ useOrganizationTimezone: () => "UTC" }));
vi.mock("next/navigation", () => ({ useRouter: () => ({ push: m.push, prefetch: vi.fn() }) }));

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
    
    it("des campagnes : un tableau nu (Campagne, Agent, État, Appels passés, Créée), jamais dans un cadre, un clic ouvre la campagne", async () => {
        m.liste.mockResolvedValue({
            data: {
                campaigns: [
                    { id: 7, name: "Rappel entretien annuel", workflow_name: "Standard", state: "paused", executed_count: 128, total_queued_count: 340, created_at: "2026-10-14T10:00:00Z", traffic_split: null },
                    { id: 8, name: "Relance devis", workflow_name: "Standard", state: "completed", executed_count: 52, total_queued_count: 52, created_at: "2026-10-02T10:00:00Z", traffic_split: { variants: [{}, {}] } },
                ],
            },
        });
        const { container } = render(<FournisseurLangue><CampaignsPage /></FournisseurLangue>);
        expect(await screen.findByText("Rappel entretien annuel")).toBeTruthy();
        expect(Array.from(container.querySelectorAll("th")).map((th) => th.textContent)).toEqual(["Campagne", "Agent", "État", "Appels passés", "Créée"]);
        // L'état se lit par un point et un mot ; le tableau n'est dans aucune carte.
        expect(screen.getByText("En pause")).toBeTruthy();
        expect(screen.getByText("Terminée")).toBeTruthy();
        expect(container.querySelector('[data-etat="brouillon"]')).not.toBeNull();
        expect(container.querySelector('[data-slot="card"]')).toBeNull();
        expect(screen.getByText("128 / 340")).toBeTruthy();
        expect(screen.getByText("+1")).toBeTruthy();
        fireEvent.click(screen.getByText("Rappel entretien annuel"));
        expect(m.push).toHaveBeenCalledWith("/campaigns/7");
    });

    it("« Nouvelle campagne » mène à la création", async () => {
        m.liste.mockResolvedValue({ data: { campaigns: [] } });
        render(<FournisseurLangue><CampaignsPage /></FournisseurLangue>);
        fireEvent.click(await screen.findByRole("button", { name: /Nouvelle campagne/ }));
        expect(m.push).toHaveBeenCalledWith("/campaigns/new");
    });

    it("une lecture qui échoue montre l'état d'erreur, et « Réessayer » relit", async () => {
        m.liste.mockResolvedValueOnce({ error: { detail: "boom" } });
        m.liste.mockResolvedValueOnce({ data: { campaigns: [] } });
        render(<FournisseurLangue><CampaignsPage /></FournisseurLangue>);
        fireEvent.click(await screen.findByRole("button", { name: /Réessayer/ }));
        await waitFor(() => expect(m.liste).toHaveBeenCalledTimes(2));
        expect(await screen.findByText("Aucune campagne pour l'instant")).toBeTruthy();
    });
});
