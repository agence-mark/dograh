/**
 * [.mark] Clôture D2 (É11, É68) : la page « Téléphonie » : un tableau sans cadre, tout en français (et en anglais), l'étape qui bloque
 * un appel sortant dite par son identifiant (jamais le texte anglais du fournisseur), « Ajouter » ouvre le formulaire.
 */
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { FournisseurLangue } from "../langue/langue";

const m = vi.hoisted(() => ({ liste: vi.fn(), defaut: vi.fn(), ouverture: vi.fn() }));
vi.mock("@/client/sdk.gen", async (importOriginal) =>
    (await import("../sdk-factice")).sdkFactice(await importOriginal(), {
        listTelephonyConfigurationsApiV1OrganizationsTelephonyConfigsGet: m.liste,
        setDefaultOutboundApiV1OrganizationsTelephonyConfigsConfigIdSetDefaultOutboundPost: m.defaut,
    }),
);
vi.mock("sonner", () => ({ toast: { success: vi.fn(), error: vi.fn() } }));
vi.mock("@/lib/auth", () => ({ useAuth: () => ({ user: { id: 1 }, loading: false }) }));
vi.mock("next/navigation", () => ({ useRouter: () => ({ push: vi.fn() }), useSearchParams: () => new URLSearchParams(), usePathname: () => "/labo/telephonie" }));
vi.mock("@/context/TelephonyConfigWarningsContext", () => ({
    useTelephonyConfigWarnings: () => ({ telnyxMissingWebhookPublicKeyCount: 0, vonageMissingSignatureSecretCount: 0, refresh: vi.fn() }),
}));
vi.mock("@/components/telephony/ConfigFormDialog", () => ({
    ConfigFormDialog: ({ open }: { open: boolean; existing: unknown }) => (open ? <div data-testid="formulaire-config" /> : null),
}));

vi.stubGlobal("ResizeObserver", class { observe() {} unobserve() {} disconnect() {} });

const CLOUDONIX = {
    id: 1, name: "Dograh Cloudonix SIP", provider: "cloudonix", is_default_outbound: true, inactive: false, phone_number_count: 0,
    is_ready_for_outbound: false, outbound_blocked_step: "outbound_trunk",
    outbound_blocked_reason: "Under Outbound trunks, add a trunk pointing at your SIP carrier or PBX.",
};
const PRETE = { id: 2, name: "Twilio principal", provider: "twilio", is_default_outbound: false, inactive: false, phone_number_count: 2, is_ready_for_outbound: true };

beforeEach(() => {
    m.liste.mockResolvedValue({ data: { configurations: [CLOUDONIX, PRETE] } });
    m.defaut.mockResolvedValue({ data: {} });
});
afterEach(() => {
    cleanup();
    vi.clearAllMocks();
    window.localStorage.clear();
});

const monter = async () => {
    const { PageTelephonie } = await import("./PageTelephonie");
    return render(
        <FournisseurLangue>
            <PageTelephonie />
        </FournisseurLangue>,
    );
};

describe("[.mark] la page Téléphonie", () => {
    it("est un tableau sans cadre, en français, qui dit l'état de chaque configuration", async () => {
        await monter();
        expect(await screen.findByRole("heading", { name: /Téléphonie/ })).toBeTruthy();
        const ligne = screen.getByText("Dograh Cloudonix SIP").closest("tr")!;
        expect(ligne.textContent).toContain("Par défaut");
        expect(ligne.textContent).toContain("Configuration incomplète");
        expect(screen.getByText("Twilio principal").closest("tr")!.textContent).toContain("Prête");
        expect(document.body.textContent).not.toMatch(/Under Outbound|phone numbers|Manage Phone|Telephony configurations/);
        expect(document.querySelector(".rounded-xl.border")).toBeNull();
    });

    it("dit l'étape bloquante par son identifiant, jamais le texte anglais du fournisseur", async () => {
        await monter();
        await screen.findByText("Dograh Cloudonix SIP");
        expect(screen.getByText("Dograh Cloudonix SIP").closest("tr")!.querySelector('[aria-label="Précision"]')).not.toBeNull();
        const { etapeDite } = await import("./PageTelephonie");
        const fr = (x: { fr: string }) => x.fr;
        expect(etapeDite(CLOUDONIX as never, fr)).toContain("Lignes sortantes");
        expect(etapeDite(CLOUDONIX as never, fr)).not.toContain("Under Outbound");
        // Une clé inconnue : le texte du fournisseur reste le repli.
        expect(etapeDite({ ...CLOUDONIX, outbound_blocked_step: "autre" } as never, fr)).toContain("Under Outbound");
    });

    it("rend une configuration par défaut d'un geste et ouvre le formulaire d'ajout", async () => {
        await monter();
        await screen.findByText("Twilio principal");
        fireEvent.click(screen.getByRole("button", { name: "Rendre par défaut pour les appels sortants" }));
        await waitFor(() => expect(m.defaut).toHaveBeenCalledWith({ path: { config_id: 2 } }));
        fireEvent.click(screen.getByRole("button", { name: /Nouvelle configuration/ }));
        expect(screen.getByTestId("formulaire-config")).toBeTruthy();
    });

    it("parle anglais quand l'écran est en anglais", async () => {
        window.localStorage.setItem("mark.langue", "en");
        await monter();
        expect(await screen.findByRole("heading", { name: /Telephony/ })).toBeTruthy();
        expect(screen.getByText("Setup incomplete")).toBeTruthy();
    });
});
