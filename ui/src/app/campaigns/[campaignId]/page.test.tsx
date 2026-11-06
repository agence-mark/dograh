/**
 * [.mark] K8 : la page d'une campagne à la forme de la maquette (sections nues, lignes en lecture, journal en tableau,
 * jamais de carte) ; lancer ou reprendre une campagne fait partir de vrais appels : on confirme d'abord.
 */
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { FournisseurLangue } from "@/components/mark/langue/langue";

// ⚠️ Un seul objet utilisateur et une seule fonction de jeton : la page relit quand ils changent.
const m = vi.hoisted(() => ({
    lire: vi.fn(),
    lancer: vi.fn(),
    reprendre: vi.fn(),
    pause: vi.fn(),
    auth: { user: { id: 1 }, loading: false, getAccessToken: async () => "t", redirectToLogin: () => undefined },
}));

vi.mock("@/client/sdk.gen", () => ({
    getCampaignApiV1CampaignCampaignIdGet: m.lire,
    startCampaignApiV1CampaignCampaignIdStartPost: m.lancer,
    resumeCampaignApiV1CampaignCampaignIdResumePost: m.reprendre,
    pauseCampaignApiV1CampaignCampaignIdPausePost: m.pause,
    redialCampaignApiV1CampaignCampaignIdRedialPost: vi.fn(),
    getCampaignSourceDownloadUrlApiV1CampaignCampaignIdSourceDownloadUrlGet: vi.fn(),
    getCampaignReportApiV1CampaignCampaignIdReportGet: vi.fn(),
}));
vi.mock("@/lib/auth", () => ({ useAuth: () => m.auth }));
vi.mock("@/hooks/useOrganizationTimezone", () => ({ useOrganizationTimezone: () => "UTC" }));
vi.mock("next/navigation", () => ({
    usePathname: () => "/labo/campagnes/7",
    useParams: () => ({ campaignId: "7" }),
    useRouter: () => ({ push: vi.fn(), prefetch: vi.fn(), refresh: vi.fn() }),
    useSearchParams: () => new URLSearchParams(),
}));
vi.mock("../CampaignTrafficStats", () => ({ default: () => <div data-testid="repartition" /> }));
vi.mock("@/components/workflow-runs", () => ({ CampaignRuns: () => <div data-testid="appels" /> }));

import CampaignPage from "./page";

const CAMPAGNE = {
    id: 7,
    name: "Rappel entretien annuel",
    workflow_id: 3,
    workflow_name: "Standard",
    state: "created",
    source_type: "csv",
    source_id: "dossier/contacts.csv",
    executed_count: 0,
    total_queued_count: 340,
    created_at: "2026-10-14T10:00:00Z",
    started_at: null,
    completed_at: null,
    max_concurrency: 2,
    telephony_configuration_id: null,
    retry_config: { enabled: true, max_retries: 2, retry_delay_seconds: 120, retry_on_busy: true, retry_on_no_answer: true, retry_on_voicemail: false },
    schedule_config: null,
    logs: [{ ts: "2026-10-14T10:05:00Z", level: "error", event: "provider_error", message: "Le fournisseur a refusé", details: null }],
};

const monter = () => render(<FournisseurLangue><CampaignPage /></FournisseurLangue>);

beforeEach(() => {
    m.lire.mockReset().mockResolvedValue({ data: CAMPAGNE });
    m.lancer.mockReset().mockResolvedValue({ data: { ...CAMPAGNE, state: "running" } });
    m.reprendre.mockReset();
    m.pause.mockReset();
});
afterEach(() => cleanup());

describe("[.mark] K8 : la page d'une campagne", () => {
    it("sections nues : lignes en lecture, journal en tableau, point d'état, jamais de carte", async () => {
        const { container } = monter();
        expect(await screen.findByRole("heading", { name: /Rappel entretien annuel/ })).toBeTruthy();
        expect(container.querySelector('[data-slot="card"]')).toBeNull();
        expect(container.querySelector('[data-etat="brouillon"]')).not.toBeNull();
        expect(screen.getByText("Fichier source")).toBeTruthy();
        expect(screen.getByText("contacts.csv")).toBeTruthy();
        expect(screen.getByText("0 / 340")).toBeTruthy();
        // Le journal est un tableau, la répartition et les appels sont posés.
        expect(screen.getByText("Le fournisseur a refusé")).toBeTruthy();
        expect(container.querySelector("table")).not.toBeNull();
        expect(screen.getByTestId("repartition")).toBeTruthy();
        expect(screen.getByTestId("appels")).toBeTruthy();
    });

    it("« Lancer » demande confirmation avant de faire partir les appels", async () => {
        monter();
        fireEvent.click(await screen.findByRole("button", { name: "Lancer" }));
        // La fenêtre est là, rien n'est parti.
        expect(await screen.findByText("Lancer la campagne ?")).toBeTruthy();
        expect(m.lancer).not.toHaveBeenCalled();
        fireEvent.click(screen.getAllByRole("button", { name: "Lancer" }).at(-1) as HTMLElement);
        await waitFor(() => expect(m.lancer).toHaveBeenCalledTimes(1));
    });

    it("« Annuler » dans la confirmation ne lance rien", async () => {
        monter();
        fireEvent.click(await screen.findByRole("button", { name: "Lancer" }));
        fireEvent.click(await screen.findByRole("button", { name: "Annuler" }));
        expect(m.lancer).not.toHaveBeenCalled();
    });

    it("une campagne illisible : l'état d'erreur, jamais un écran blanc", async () => {
        m.lire.mockResolvedValue({ error: { detail: "boom" } });
        monter();
        expect(await screen.findByRole("button", { name: /Réessayer/ })).toBeTruthy();
    });
});
