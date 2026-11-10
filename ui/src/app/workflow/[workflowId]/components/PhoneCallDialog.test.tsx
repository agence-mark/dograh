/**
 * [.mark] Clôture SA-5 (É68, Evan 09/11) : le panneau « Connecter un service téléphonique » et le formulaire d'appel sont dits dans la
 * langue de l'écran (français et anglais), jamais en anglais mélangé au français ; l'étape qui bloque un appel sortant passe par son
 * identifiant (le texte du fournisseur n'est que le repli).
 */
import { cleanup, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { FournisseurLangue } from "@/components/mark/langue/langue";

const m = vi.hoisted(() => ({ liste: vi.fn(), numeros: vi.fn(), prefs: vi.fn(), meta: vi.fn() }));
vi.mock("@/client/sdk.gen", async (importOriginal) =>
    (await import("@/components/mark/sdk-factice")).sdkFactice(await importOriginal(), {
        listTelephonyConfigurationsApiV1OrganizationsTelephonyConfigsGet: m.liste,
        listPhoneNumbersApiV1OrganizationsTelephonyConfigsConfigIdPhoneNumbersGet: m.numeros,
        getPreferencesApiV1OrganizationsPreferencesGet: m.prefs,
        getTelephonyProvidersMetadataApiV1OrganizationsTelephonyProvidersMetadataGet: m.meta,
    }),
);
vi.mock("next/navigation", () => ({ useRouter: () => ({ push: vi.fn() }) }));
vi.mock("@/context/UserConfigContext", () => ({ useUserConfig: () => ({ refreshConfig: vi.fn() }) }));
vi.mock("react-international-phone", () => ({ PhoneInput: () => <input aria-label="tel" /> }));
vi.mock("react-international-phone/style.css", () => ({}));

const SIP_BLOQUEE = {
    id: 1, name: "Dograh Cloudonix SIP", provider: "cloudonix", connectivity: "sip", is_default_outbound: true, inactive: false,
    is_ready_for_outbound: false, outbound_blocked_step: "outbound_trunk",
    outbound_blocked_reason: "Under Outbound trunks, add a trunk pointing at your SIP carrier or PBX.",
};
const PRETE = { id: 2, name: "Twilio principal", provider: "twilio", is_default_outbound: false, inactive: false, is_ready_for_outbound: true };

beforeEach(() => {
    m.prefs.mockResolvedValue({ data: {} });
    m.numeros.mockResolvedValue({ data: { phone_numbers: [] } });
    m.meta.mockResolvedValue({ data: { providers: [{ display_name: "Twilio", connectivity: "api" }, { display_name: "Plivo", connectivity: "api" }] } });
});
afterEach(() => {
    cleanup();
    vi.clearAllMocks();
    window.localStorage.clear();
});

const monter = async (langue: "fr" | "en") => {
    window.localStorage.setItem("mark.langue", langue);
    const { PhoneCallDialog } = await import("./PhoneCallDialog");
    return render(
        <FournisseurLangue>
            <PhoneCallDialog open onOpenChange={() => undefined} workflowId={7} user={{ id: "u" }} />
        </FournisseurLangue>,
    );
};

const ANGLAIS = /Connect phone service|Dograh doesn|Use a telephony provider|Recommended|Bring your own SIP|Add provider|Do it Later|waiting for your carrier|Under Outbound|Phone Call|Start Call|Caller ID|Cancel/;

describe("[.mark] la fenêtre d'appel par téléphone", () => {
    it("sans service : le panneau « Connecter un service téléphonique » est entièrement en français", async () => {
        m.liste.mockResolvedValue({ data: { configurations: [SIP_BLOQUEE] } });
        await monter("fr");
        expect(await screen.findByText("Connecter un service téléphonique")).toBeTruthy();
        expect(screen.getByText("Utiliser un fournisseur de téléphonie")).toBeTruthy();
        expect(screen.getByText("Recommandé")).toBeTruthy();
        expect(screen.getByText("Apporter sa propre ligne SIP")).toBeTruthy();
        expect(screen.getByRole("button", { name: "Ajouter un fournisseur" })).toBeTruthy();
        expect(screen.getByRole("button", { name: "Configurer le SIP" })).toBeTruthy();
        expect(screen.getByRole("button", { name: "Plus tard" })).toBeTruthy();
        await waitFor(() => expect(document.body.textContent).toContain("Twilio ou Plivo"));
        expect(document.body.textContent).toContain("Lignes sortantes");
        expect(document.body.textContent).not.toMatch(ANGLAIS);
    });

    it("sans service : le même panneau en anglais", async () => {
        m.liste.mockResolvedValue({ data: { configurations: [SIP_BLOQUEE] } });
        await monter("en");
        expect(await screen.findByText("Connect a phone service")).toBeTruthy();
        expect(screen.getByRole("button", { name: "Add a provider" })).toBeTruthy();
        expect(screen.getByRole("button", { name: "Set up SIP" })).toBeTruthy();
        expect(document.body.textContent).not.toMatch(/Connecter|Recommandé|Plus tard/);
    });

    it("avec un service prêt : le formulaire d'appel est en français", async () => {
        m.liste.mockResolvedValue({ data: { configurations: [PRETE] } });
        await monter("fr");
        expect(await screen.findByText("Appel téléphonique")).toBeTruthy();
        expect(screen.getByText("Configuration de téléphonie")).toBeTruthy();
        expect(screen.getByRole("button", { name: "Lancer l'appel" })).toBeTruthy();
        expect(screen.getByRole("button", { name: "Annuler" })).toBeTruthy();
        expect(screen.getByRole("button", { name: "Configurer la téléphonie" })).toBeTruthy();
        expect(document.body.textContent).not.toMatch(ANGLAIS);
    });
});
