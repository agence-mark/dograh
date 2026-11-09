/**
 * [.mark] Clôture D2 (É11, É68) : la page « Téléphonie » : un tableau sans cadre, tout en français (et en anglais), l'étape qui bloque
 * un appel sortant dite par son identifiant (jamais le texte anglais du fournisseur), « Ajouter » ouvre le formulaire.
 */
import { cleanup, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { FournisseurLangue } from "../langue/langue";

const m = vi.hoisted(() => ({ liste: vi.fn(), defaut: vi.fn(), ouverture: vi.fn(), detail: vi.fn(), numeros: vi.fn() }));
vi.mock("@/client/sdk.gen", async (importOriginal) =>
    (await import("../sdk-factice")).sdkFactice(await importOriginal(), {
        listTelephonyConfigurationsApiV1OrganizationsTelephonyConfigsGet: m.liste,
        setDefaultOutboundApiV1OrganizationsTelephonyConfigsConfigIdSetDefaultOutboundPost: m.defaut,
        getTelephonyConfigurationByIdApiV1OrganizationsTelephonyConfigsConfigIdGet: m.detail,
        listPhoneNumbersApiV1OrganizationsTelephonyConfigsConfigIdPhoneNumbersGet: m.numeros,
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

vi.mock("@/components/telephony/PhoneNumberDialog", () => ({
    PhoneNumberDialog: ({ open, configId, existing }: { open: boolean; configId: number; existing?: { address: string } | null }) =>
        open ? <div data-testid="dialogue-numero" data-config={configId}>{existing?.address ?? "nouveau"}</div> : null,
}));
vi.mock("@/components/telephony/TrunkCard", () => ({
    TrunkCard: ({ configuration }: { configuration: { id: number } }) => <div data-testid="lignes-sip" data-config={configuration.id} />,
}));

vi.stubGlobal("ResizeObserver", class { observe() {} unobserve() {} disconnect() {} });

const CLOUDONIX = {
    id: 1, name: "Dograh Cloudonix SIP", provider: "cloudonix", is_default_outbound: true, inactive: false, phone_number_count: 0,
    is_ready_for_outbound: false, outbound_blocked_step: "outbound_trunk",
    outbound_blocked_reason: "Under Outbound trunks, add a trunk pointing at your SIP carrier or PBX.",
};
const PRETE = { id: 2, name: "Twilio principal", provider: "twilio", is_default_outbound: false, inactive: false, phone_number_count: 2, is_ready_for_outbound: true };

const NUMERO = { id: 7, telephony_configuration_id: 1, address: "+33344000000", address_type: "pstn", label: null, inbound_workflow_id: 12, inbound_workflow_name: "Standard", is_active: true, is_default_caller_id: true };
const NUMERO_LIBRE = { ...NUMERO, id: 8, address: "+33970000000", inbound_workflow_id: null, inbound_workflow_name: null, is_active: false, is_default_caller_id: false };

beforeEach(() => {
    m.detail.mockResolvedValue({ data: { ...CLOUDONIX, supports_trunks: true, trunks: [], credentials: {}, updated_at: "2026-11-09T10:00:00Z" } });
    m.numeros.mockResolvedValue({ data: { phone_numbers: [NUMERO, NUMERO_LIBRE] } });
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
        const ligne = screen.getAllByText("Dograh Cloudonix SIP")[0].closest("tr")!;
        expect(ligne.textContent).toContain("Par défaut");
        expect(ligne.textContent).toContain("Configuration incomplète");
        expect(screen.getAllByText("Twilio principal")[0].closest("tr")!.textContent).toContain("Prête");
        expect(document.body.textContent).not.toMatch(/Under Outbound|phone numbers|Manage Phone|Telephony configurations/);
        expect(document.querySelector(".rounded-xl.border")).toBeNull();
    });

    it("dit l'étape bloquante par son identifiant, jamais le texte anglais du fournisseur", async () => {
        await monter();
        (await screen.findAllByText("Dograh Cloudonix SIP"))[0];
        expect(screen.getAllByText("Dograh Cloudonix SIP")[0].closest("tr")!.querySelector('[aria-label="Précision"]')).not.toBeNull();
        const { etapeDite } = await import("./PageTelephonie");
        const fr = (x: { fr: string }) => x.fr;
        expect(etapeDite(CLOUDONIX as never, fr)).toContain("Lignes sortantes");
        expect(etapeDite(CLOUDONIX as never, fr)).not.toContain("Under Outbound");
        // Une clé inconnue : le texte du fournisseur reste le repli.
        expect(etapeDite({ ...CLOUDONIX, outbound_blocked_step: "autre" } as never, fr)).toContain("Under Outbound");
    });

    it("rend une configuration par défaut d'un geste et ouvre le formulaire d'ajout", async () => {
        await monter();
        (await screen.findAllByText("Twilio principal"))[0];
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

    // Clôture SA-5 (É11, Evan 09/11) : « tout sur une page pour commencer » : la configuration principale, ses numéros et ses lignes SIP.
    describe("tout sur une page", () => {
        it("lit la configuration principale (par défaut en sortie) et montre ses numéros dans un tableau sans cadre", async () => {
            await monter();
            const section = await screen.findByRole("region", { name: "Numéros" });
            await waitFor(() => expect(m.numeros).toHaveBeenCalledWith(expect.objectContaining({ path: { config_id: 1 } })));
            expect(m.detail).toHaveBeenCalledWith(expect.objectContaining({ path: { config_id: 1 } }));
            expect(Array.from(section.querySelectorAll("thead th")).map((t) => t.textContent)).toEqual(["Numéro", "Appels entrants vers", "Actif"]);
            const lignes = Array.from(section.querySelectorAll("tbody tr"));
            expect(lignes[0].textContent).toContain("+33344000000");
            expect(lignes[0].textContent).toContain("Standard");
            expect(lignes[1].textContent).toContain("aucun agent");
            expect(screen.getByRole("region", { name: "Configuration principale" }).textContent).toContain("Dograh Cloudonix SIP");
            expect(document.body.textContent).not.toMatch(/Phone numbers|Add phone number|Edit credentials/);
        });

        it("« Numéro » ouvre le formulaire d'un numéro neuf, un clic sur une ligne celui de ce numéro", async () => {
            await monter();
            const section = await screen.findByRole("region", { name: "Numéros" });
            await within(section).findByText("+33344000000");
            fireEvent.click(within(section).getByRole("button", { name: /Numéro/ }));
            expect(screen.getByTestId("dialogue-numero").getAttribute("data-config")).toBe("1");
            expect(screen.getByTestId("dialogue-numero").textContent).toBe("nouveau");
            cleanup();
            await monter();
            fireEvent.click((await screen.findByText("+33970000000")).closest("tr")!);
            expect(screen.getByTestId("dialogue-numero").textContent).toBe("+33970000000");
        });

        it("montre les lignes sortantes (SIP) seulement pour un opérateur qui en a", async () => {
            await monter();
            expect((await screen.findByTestId("lignes-sip")).getAttribute("data-config")).toBe("1");
            cleanup();
            m.detail.mockResolvedValue({ data: { ...CLOUDONIX, supports_trunks: false, trunks: [], credentials: {}, updated_at: "2026-11-09T10:00:00Z" } });
            await monter();
            await screen.findByRole("region", { name: "Numéros" });
            expect(screen.queryByTestId("lignes-sip")).toBeNull();
        });

        it("sans numéro : un état vide dit, avec le bouton pour en ajouter", async () => {
            m.numeros.mockResolvedValue({ data: { phone_numbers: [] } });
            await monter();
            const section = await screen.findByRole("region", { name: "Numéros" });
            await waitFor(() => expect(within(section).getByText("Aucun numéro encore")).toBeTruthy());
            expect(within(section).getByRole("button", { name: /Numéro/ })).toBeTruthy();
        });
    });
});
