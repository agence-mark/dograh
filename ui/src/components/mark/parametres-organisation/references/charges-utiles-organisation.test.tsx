/**
 * [.mark] Payload references of the Platform Settings page.
 *
 * Same question, same method as `reglages-agent/references/charges-utiles-agent.test.tsx`:
 * every case of `cas-organisation.ts` was played on the page as it was
 * (`ef03ef5e`: Preferences, Closed-business announcement, MCP, Telemetry,
 * Trade vocabulary) and what the server would receive was frozen in
 * `charges-utiles-organisation.json`. The page in five themes must send the
 * same, case by case.
 *
 * Rewriting the reference: `ECRIRE_REFERENCES=1 npx vitest run <this file>`,
 * ⛔ only ever on the page as it was.
 *
 * Mocked: the API client (its two save routes ARE what is recorded), auth,
 * the timezone picker (a native select, same on both pages), and three
 * components reused as they are -- the disposition mapping dialog (a stub
 * calling the very callback the page hands it), MCP and Telemetry (their own
 * buttons, untouched by the chantier).
 */
import { existsSync, readFileSync, writeFileSync } from "node:fs";
import { join } from "node:path";

import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import type { ReactNode } from "react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { jouerGeste } from "../../reglages-agent/references/jouer";
import {
    BOUTON_DE_LA_CARTE_ORGANISATION,
    CAS_ORGANISATION,
    type CasOrganisation,
} from "./cas-organisation";

const FICHIER = join(
    process.cwd(),
    "src/components/mark/parametres-organisation/references/charges-utiles-organisation.json",
);
const ECRIRE = process.env.ECRIRE_REFERENCES === "1";

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
    annonce_fermeture: "Nous sommes fermés en ce moment[, nous rouvrons {reouverture}].",
    annonce_pause: "Nous sommes en pause[, nous revenons {reouverture}].",
    etat_force: "OUVERT",
    etat_force_jusqu_a: "2026-12-31T10:00:00",
};

const m = vi.hoisted(() => ({
    savePreferences: vi.fn(),
    saveAnnonce: vi.fn(),
}));

vi.mock("@/client/sdk.gen", () => ({
    getPreferencesApiV1OrganizationsPreferencesGet: () => Promise.resolve({ data: structuredClone(PREFERENCES) }),
    savePreferencesApiV1OrganizationsPreferencesPut: m.savePreferences,
    getAnnonceOuvertureApiV1OrganizationsAnnonceOuvertureGet: () => Promise.resolve({ data: structuredClone(ANNONCE) }),
    saveAnnonceOuvertureApiV1OrganizationsAnnonceOuverturePut: m.saveAnnonce,
    getCommunesDuCodePostalApiV1OrganizationsCommunesGet: () =>
        Promise.resolve({ data: [{ code_insee: "60057", nom: "Beauvais" }] }),
    getLexiqueApiV1OrganizationsLexiqueGet: () =>
        Promise.resolve({ data: { format: "lexique-mark", version: 1, termes: [] } }),
    saveLexiqueApiV1OrganizationsLexiquePut: vi.fn(),
    importLexiqueApiV1OrganizationsLexiqueImportPost: vi.fn(),
}));
vi.mock("sonner", () => ({ toast: { success: vi.fn(), error: vi.fn() } }));
vi.mock("@/context/UnsavedChangesContext", () => ({ useUnsavedChanges: () => undefined }));
vi.mock("@/context/OrgConfigContext", () => ({
    useOrgConfig: () => ({ organizationPreferences: PREFERENCES, userConfig: null }),
}));
vi.mock("@/context/UserConfigContext", () => ({
    useUserConfig: () => ({ refreshConfig: () => Promise.resolve() }),
}));
vi.mock("@/lib/auth", () => ({ useAuth: () => ({ user: { id: 1 }, loading: false }) }));
vi.mock("react-timezone-select", () => ({
    default: ({ value, onChange }: { value: string | { value: string }; onChange: (v: string) => void }) => (
        <select
            id="settings-timezone"
            value={typeof value === "string" ? value : value.value}
            onChange={(e) => onChange(e.target.value)}
        >
            <option value="Europe/Paris">Europe/Paris</option>
            <option value="America/New_York">America/New_York</option>
        </select>
    ),
}));
vi.mock("@/components/DispositionMappingDialog", () => ({
    DispositionMappingDialog: ({ open, onSave }: { open: boolean; onSave: (m: Record<string, string>) => void }) =>
        open ? (
            <button type="button" onClick={() => onSave({ voicemail: "AM", no_answer: "NA" })}>
                Stub: save mapping
            </button>
        ) : null,
}));
vi.mock("@/components/ui/dialog", () => ({
    Dialog: ({ open, children }: { open: boolean; children: ReactNode }) => (open ? <div>{children}</div> : null),
    DialogContent: ({ children }: { children: ReactNode }) => <div>{children}</div>,
    DialogDescription: ({ children }: { children: ReactNode }) => <p>{children}</p>,
    DialogFooter: ({ children }: { children: ReactNode }) => <div>{children}</div>,
    DialogHeader: ({ children }: { children: ReactNode }) => <div>{children}</div>,
    DialogTitle: ({ children }: { children: ReactNode }) => <h2>{children}</h2>,
}));
vi.mock("@/components/MCPSection", () => ({ MCPSection: () => <div /> }));
vi.mock("@/components/TelemetrySection", () => ({ TelemetrySection: () => <div /> }));
vi.stubGlobal(
    "ResizeObserver",
    class {
        observe() {}
        unobserve() {}
        disconnect() {}
    },
);

const { default: SettingsPage } = await import("@/app/settings/page");

const reinitialiser = () => {
    m.savePreferences.mockReset().mockImplementation(async ({ body }) => ({ data: body }));
    m.saveAnnonce.mockReset().mockImplementation(async ({ body }) => ({ data: body }));
};
reinitialiser();
afterEach(() => {
    cleanup();
    reinitialiser();
});

type AppelOrganisation = { route: "preferences" | "annonce"; corps: unknown };

const relever = (): AppelOrganisation[] =>
    [
        ...m.savePreferences.mock.calls.map((args, i) => ({
            ordre: m.savePreferences.mock.invocationCallOrder[i],
            appel: { route: "preferences" as const, corps: JSON.parse(JSON.stringify(args[0].body)) },
        })),
        ...m.saveAnnonce.mock.calls.map((args, i) => ({
            ordre: m.saveAnnonce.mock.invocationCallOrder[i],
            appel: { route: "annonce" as const, corps: JSON.parse(JSON.stringify(args[0].body)) },
        })),
    ]
        .sort((a, b) => a.ordre - b.ordre)
        .map((a) => a.appel);

const ouvrirLaPage = async () => {
    render(<SettingsPage />);
    await waitFor(() => expect(document.getElementById("settings-test-phone-number")).toBeTruthy());
    await waitFor(() => expect(document.getElementById("annonce_fermeture")).toBeTruthy());
    await waitFor(() => expect(document.getElementById("settings-business-address-voie")).toBeTruthy());
};

const jouer = async (cas: CasOrganisation) => {
    await ouvrirLaPage();
    for (const geste of cas.gestes) jouerGeste(geste);
    if (!cas.enregistreSeul) {
        const nom = BOUTON_DE_LA_CARTE_ORGANISATION[cas.carte];
        if (!nom) throw new Error(`Card ${cas.carte} has no save button.`);
        const bouton = screen.getByRole("button", { name: nom }) as HTMLButtonElement;
        expect(bouton.disabled, `${cas.id}: ${nom} must be enabled`).toBe(false);
        fireEvent.click(bouton);
    }
    await waitFor(() => expect(m.savePreferences.mock.calls.length + m.saveAnnonce.mock.calls.length).toBeGreaterThan(0));
    return relever();
};

const references: { preferences: unknown; annonce: unknown; cas: Record<string, unknown> } =
    existsSync(FICHIER) && !ECRIRE
        ? JSON.parse(readFileSync(FICHIER, "utf8"))
        : { preferences: PREFERENCES, annonce: ANNONCE, cas: {} };

describe("payload references of the Platform Settings page", () => {
    it("starts from the same stored settings as the reference", () => {
        expect({ preferences: PREFERENCES, annonce: ANNONCE }).toEqual({
            preferences: references.preferences,
            annonce: references.annonce,
        });
    });

    it.each(CAS_ORGANISATION.map((cas) => [cas.id, cas] as const))(
        "case %s sends what the reference froze",
        async (_id, cas) => {
            const appels = await jouer(cas);
            const releve = { carte: cas.carte, theme: cas.theme, appels };
            if (ECRIRE) references.cas[cas.id] = releve;
            else expect(releve).toEqual(references.cas[cas.id]);
        },
        20000,
    );

    it("wrote or matched every case, no more, no less", () => {
        if (ECRIRE) writeFileSync(FICHIER, `${JSON.stringify(references, null, 2)}\n`, "utf8");
        expect(Object.keys(references.cas).sort()).toEqual(CAS_ORGANISATION.map((c) => c.id).sort());
    });
});
