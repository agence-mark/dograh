/**
 * [.mark] The Platform Settings page in 5 themes, rendered (chantier
 * reorganisation-ecran-reglages, step 5).
 *
 * What the payload references do not ask:
 *
 *   - every setting the inventory says is on screen IS found in its theme;
 *   - a postal code without its town is NAMED and blocks the Business theme (E7);
 *   - an announcement that could not be read is never overwritten, and does
 *     not stop the address from being saved;
 *   - a theme never sends what is being typed in another theme;
 *   - the page speaks French until the user chooses (D12).
 */
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import type { ReactNode } from "react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { FournisseurLangue } from "../langue/langue";
import { INVENTAIRE_ANNONCE, INVENTAIRE_PREFERENCES } from "./inventaire-organisation";

const PREFERENCES = {
    test_phone_number: "+33344000000",
    timezone: "Europe/Paris",
    external_pbx_integrations_enabled: false,
    disposition_mapping_enabled: true,
    disposition_mapping: { voicemail: "AM" },
    adresse_etablissement: { code_postal: "60000", code_insee: "60057", commune: "Beauvais", voie: "4 rue des Artisans" },
};
const ANNONCE = {
    format: "annonce-ouverture-mark",
    version: 1,
    annonce_fermeture: "Nous sommes fermés[, nous rouvrons {reouverture}].",
    annonce_pause: "Nous sommes en pause[, nous revenons {reouverture}].",
    etat_force: "FERME",
    etat_force_jusqu_a: null,
};

const m = vi.hoisted(() => ({
    getAnnonce: vi.fn(),
    savePreferences: vi.fn(),
    saveAnnonce: vi.fn(),
}));

vi.mock("@/client/sdk.gen", () => ({
    getPreferencesApiV1OrganizationsPreferencesGet: () => Promise.resolve({ data: structuredClone(PREFERENCES) }),
    savePreferencesApiV1OrganizationsPreferencesPut: m.savePreferences,
    getAnnonceOuvertureApiV1OrganizationsAnnonceOuvertureGet: m.getAnnonce,
    saveAnnonceOuvertureApiV1OrganizationsAnnonceOuverturePut: m.saveAnnonce,
    getCommunesDuCodePostalApiV1OrganizationsCommunesGet: () =>
        Promise.resolve({ data: [{ code_insee: "60057", nom: "Beauvais" }, { code_insee: "60001", nom: "Autre" }] }),
    getLexiqueApiV1OrganizationsLexiqueGet: () => Promise.resolve({ data: { format: "lexique-mark", version: 1, termes: [] } }),
    saveLexiqueApiV1OrganizationsLexiquePut: vi.fn(),
    importLexiqueApiV1OrganizationsLexiqueImportPost: vi.fn(),
}));
vi.mock("sonner", () => ({ toast: { success: vi.fn(), error: vi.fn() } }));
vi.mock("@/context/UserConfigContext", () => ({ useUserConfig: () => ({ refreshConfig: () => Promise.resolve() }) }));
vi.mock("@/lib/auth", () => ({ useAuth: () => ({ user: { id: 1 }, loading: false }) }));
vi.mock("react-timezone-select", () => ({
    default: ({ value, onChange }: { value: string; onChange: (v: string) => void }) => (
        <select id="settings-timezone" value={value} onChange={(e) => onChange(e.target.value)}>
            <option value="Europe/Paris">Europe/Paris</option>
            <option value="America/New_York">America/New_York</option>
        </select>
    ),
}));
vi.mock("@/components/DispositionMappingDialog", () => ({ DispositionMappingDialog: () => null }));
vi.mock("@/components/ui/dialog", () => ({
    Dialog: ({ open, children }: { open: boolean; children: ReactNode }) => (open ? <div>{children}</div> : null),
    DialogContent: ({ children }: { children: ReactNode }) => <div>{children}</div>,
    DialogDescription: ({ children }: { children: ReactNode }) => <p>{children}</p>,
    DialogFooter: ({ children }: { children: ReactNode }) => <div>{children}</div>,
    DialogHeader: ({ children }: { children: ReactNode }) => <div>{children}</div>,
    DialogTitle: ({ children }: { children: ReactNode }) => <h2>{children}</h2>,
}));
vi.mock("@/components/MCPSection", () => ({ MCPSection: () => <div data-testid="mcp" /> }));
vi.mock("@/components/TelemetrySection", () => ({ TelemetrySection: () => <div data-testid="telemetrie" /> }));
vi.stubGlobal("ResizeObserver", class { observe() {} unobserve() {} disconnect() {} });

const { default: SettingsPage } = await import("@/app/settings/page");

const reinitialiser = () => {
    m.getAnnonce.mockReset().mockImplementation(() => Promise.resolve({ data: structuredClone(ANNONCE) }));
    m.savePreferences.mockReset().mockImplementation(async ({ body }) => ({ data: body }));
    m.saveAnnonce.mockReset().mockImplementation(async ({ body }) => ({ data: body }));
};
reinitialiser();
afterEach(() => {
    cleanup();
    reinitialiser();
    window.localStorage.clear();
});

const ouvrirLaPage = async (enveloppe?: (n: ReactNode) => ReactNode) => {
    render(<>{enveloppe ? enveloppe(<SettingsPage />) : <SettingsPage />}</>);
    await waitFor(() => expect(document.querySelectorAll("[data-theme]").length).toBe(5));
};

const ouvrirLeTheme = async (id: string) => {
    const entete = document.querySelector(`[data-theme="${id}"] > button[aria-expanded]`) as HTMLButtonElement;
    if (entete.getAttribute("aria-expanded") === "false") fireEvent.click(entete);
    await waitFor(() => {
        if (/Loading|Chargement/.test(document.getElementById(id)?.textContent ?? "")) throw new Error("still loading");
    });
    return document.getElementById(id) as HTMLElement;
};

const bouton = (nom: string) => screen.getByRole("button", { name: nom }) as HTMLButtonElement;

describe("[.mark] the Platform Settings page in themes", () => {
    it("draws every setting the inventory puts on screen, in its theme", async () => {
        await ouvrirLaPage();
        for (const [cle, entree] of Object.entries({ ...INVENTAIRE_PREFERENCES, ...INVENTAIRE_ANNONCE })) {
            if ("horsEcran" in entree) continue;
            const theme = await ouvrirLeTheme(entree.theme);
            if (cle === "etat_force_jusqu_a") {
                // Shown once a state is forced: it is, in the stored settings.
                expect(document.getElementById("etat_force")).not.toBeNull();
            }
            await waitFor(() => expect(theme.querySelector(`[data-reglage="${cle}"]`), `${cle} in ${entree.theme}`).not.toBeNull());
        }
        // Reused as they are, in their themes.
        expect((await ouvrirLeTheme("ecoute")).textContent).toMatch(/open vocabulary/i);
        const developpeurs = await ouvrirLeTheme("developpeurs");
        expect(developpeurs.querySelector('[data-testid="mcp"]')).not.toBeNull();
        expect(developpeurs.querySelector('[data-testid="telemetrie"]')).not.toBeNull();
    });

    it("names a postal code without its town and blocks the Business theme", async () => {
        await ouvrirLaPage();
        await ouvrirLeTheme("etablissement");
        fireEvent.change(document.getElementById("settings-business-address-code-postal")!, { target: { value: "60300" } });
        const alerte = await screen.findByRole("alert");
        expect(alerte.textContent).toContain("adresse_etablissement");
        expect(alerte.textContent).toContain("Choose the town for this postal code before saving.");
        expect(bouton("Save Business").disabled).toBe(true);
        expect(document.querySelector('[data-navigation="etablissement"] [data-pastille="erreur"]')).not.toBeNull();
    });

    it("never overwrites an announcement it could not read, and still saves the address", async () => {
        m.getAnnonce.mockReset().mockResolvedValue({ error: { detail: "boom" } });
        await ouvrirLaPage();
        await ouvrirLeTheme("etablissement");
        expect(screen.getByRole("button", { name: "Retry" })).toBeTruthy();

        // Untouched: the address alone is saved.
        fireEvent.click(bouton("Save Business"));
        await waitFor(() => expect(m.savePreferences).toHaveBeenCalledTimes(1));
        expect(m.saveAnnonce).not.toHaveBeenCalled();

        // A sentence typed over the unread one: named, and nothing saved.
        fireEvent.change(document.getElementById("annonce_fermeture")!, { target: { value: "Fermé." } });
        await waitFor(() => expect(bouton("Save Business").disabled).toBe(true));
        expect(document.querySelector('[data-erreur="annonce_fermeture"]')).not.toBeNull();
        expect(m.saveAnnonce).not.toHaveBeenCalled();
    });

    it("saves only its own fields: what is typed in another theme stays a draft", async () => {
        await ouvrirLaPage();
        await ouvrirLeTheme("organisation");
        fireEvent.change(document.getElementById("settings-test-phone-number")!, { target: { value: "+33699999999" } });
        await ouvrirLeTheme("integrations");
        fireEvent.click(document.getElementById("settings-external-pbx-integrations")!);
        fireEvent.click(bouton("Save Integrations"));

        await waitFor(() => expect(m.savePreferences).toHaveBeenCalledTimes(1));
        const corps = m.savePreferences.mock.calls[0][0].body;
        expect(corps.external_pbx_integrations_enabled).toBe(true);
        expect(corps.test_phone_number).toBe("+33344000000");
        // The number typed in Organization is still there, still to save.
        expect((document.getElementById("settings-test-phone-number") as HTMLInputElement).value).toBe("+33699999999");
        expect(document.querySelector('[data-theme="organisation"] [data-pastille="modifie"]')).not.toBeNull();
        await waitFor(() => expect(document.querySelector('[data-theme="integrations"] [data-pastille="modifie"]')).toBeNull());
    });

    it("speaks French until the user chooses", async () => {
        await ouvrirLaPage((page) => <FournisseurLangue>{page}</FournisseurLangue>);
        expect(screen.getByRole("heading", { level: 1 }).textContent).toBe("Paramètres de la plateforme");
        expect(document.querySelector('[data-theme="etablissement"]')?.textContent).toContain("Établissement");
        const theme = await ouvrirLeTheme("etablissement");
        expect(theme.textContent).toContain("Quand l'entreprise est fermée");
        expect(bouton("Enregistrer Établissement")).toBeTruthy();
    });
});
