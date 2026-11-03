/**
 * [.mark] K8 : la création d'une campagne est une fenêtre centrée posée sur la liste (comme la maquette), à corps blanc sans
 * carte ; les explications sont dans le « ! » (aucune note visible) ; « Créer la campagne » reste éteint tant que le
 * formulaire est incomplet ; « Annuler » ramène à la liste.
 */
import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { FournisseurLangue } from "@/components/mark/langue/langue";

const m = vi.hoisted(() => ({ push: vi.fn(), auth: { user: { id: 1 }, loading: false, getAccessToken: async () => "t", redirectToLogin: () => undefined } }));

vi.mock("@/client/sdk.gen", () => ({
    createCampaignApiV1CampaignCreatePost: vi.fn(),
    getCampaignDefaultsApiV1OrganizationsCampaignDefaultsGet: vi.fn().mockResolvedValue({ data: {} }),
    listTelephonyConfigurationsApiV1OrganizationsTelephonyConfigsGet: vi.fn().mockResolvedValue({ data: { configurations: [] } }),
}));
vi.mock("@/lib/auth", () => ({ useAuth: () => m.auth }));
vi.mock("next/navigation", () => ({ useRouter: () => ({ push: m.push, prefetch: vi.fn() }) }));
vi.mock("../page", () => ({ default: () => <div data-testid="liste-campagnes" /> }));
vi.mock("../CsvUploadSelector", () => ({ default: () => <div data-testid="csv" /> }));
vi.mock("../TrafficSplitEditor", () => ({ default: () => <div data-testid="repartition" />, trafficSplitError: () => null }));
vi.mock("../CampaignAdvancedSettings", () => ({
    default: () => <div data-testid="avances" />,
    getTimezoneValue: () => "UTC",
}));

import NewCampaignPage from "./page";

afterEach(() => cleanup());

describe("[.mark] K8 : nouvelle campagne", () => {
    it("une fenêtre posée sur la liste : titre, champs libellés, rien dans une carte", async () => {
        render(<FournisseurLangue><NewCampaignPage /></FournisseurLangue>);
        expect(await screen.findByRole("dialog")).toBeTruthy();
        expect(screen.getByTestId("liste-campagnes")).toBeTruthy();
        expect(screen.getByRole("heading", { name: /Nouvelle campagne/ })).toBeTruthy();
        expect(document.querySelector('[data-slot="card"]')).toBeNull();
        expect(screen.getByLabelText(/Nom de la campagne/)).toBeTruthy();
        // Aucune phrase d'aide visible : elles sont dans le « ! ».
        expect(document.body.textContent).not.toMatch(/Choose a descriptive name|Un nom qui dit ce que la campagne fait/);
        expect(document.body.textContent).not.toMatch(/Create New Campaign|Back to Campaigns/);
    });

    it("« Annuler » ferme la fenêtre et ramène à la liste", async () => {
        render(<FournisseurLangue><NewCampaignPage /></FournisseurLangue>);
        fireEvent.click(await screen.findByRole("button", { name: "Annuler" }));
        expect(m.push).toHaveBeenCalledWith("/campaigns");
    });

    it("« Créer la campagne » reste éteint tant que le formulaire est incomplet", async () => {
        render(<FournisseurLangue><NewCampaignPage /></FournisseurLangue>);
        const bouton = await screen.findByRole("button", { name: "Créer la campagne" });
        expect((bouton as HTMLButtonElement).disabled).toBe(true);
    });

    it("sans configuration de téléphonie, un lien mène à en ajouter une", async () => {
        render(<FournisseurLangue><NewCampaignPage /></FournisseurLangue>);
        expect((await screen.findByRole("link", { name: "En ajouter une" })).getAttribute("href")).toBe("/telephony-configurations");
    });
});
