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
 * Since step 5 the cases are played on the themes: each case opens its theme
 * and saves with the theme's button. ⛔ The reference is never rewritten: it
 * was written by `ECRIRE_REFERENCES=1` on the page as it was (commit
 * `13f72590` and before), and that flag now fails the run.
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
import { CAS_ORGANISATION, type CasOrganisation, type ThemeOrganisation } from "./cas-organisation";

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

const TITRE_ANGLAIS: Record<ThemeOrganisation, string> = {
    organisation: "Organization",
    etablissement: "Business",
    ecoute: "Listening",
    integrations: "Integrations",
    developpeurs: "Developers",
};

const ouvrirLaPage = async () => {
    render(<SettingsPage />);
    await waitFor(() => expect(document.querySelectorAll("[data-theme]").length).toBe(5));
};

const ouvrirLeTheme = async (theme: ThemeOrganisation) => {
    const entete = document.querySelector(`[data-theme="${theme}"] > button[aria-expanded]`) as HTMLButtonElement;
    if (entete.getAttribute("aria-expanded") === "false") fireEvent.click(entete);
    // Loaded: the fields replace « Loading... ».
    await waitFor(() => {
        if (document.getElementById(theme)?.textContent?.includes("Loading")) throw new Error("still loading");
    });
};

const jouer = async (cas: CasOrganisation) => {
    await ouvrirLaPage();
    await ouvrirLeTheme(cas.theme);
    for (const geste of cas.gestes) jouerGeste(geste);
    if (!cas.enregistreSeul) {
        const nom = `Save ${TITRE_ANGLAIS[cas.theme]}`;
        const bouton = screen.getByRole("button", { name: nom }) as HTMLButtonElement;
        expect(bouton.disabled, `${cas.id}: ${nom} must be enabled`).toBe(false);
        fireEvent.click(bouton);
    }
    await waitFor(() => expect(m.savePreferences.mock.calls.length + m.saveAnnonce.mock.calls.length).toBeGreaterThan(0));
    // A theme saves its parts one after the other.
    await new Promise((fin) => setTimeout(fin, 50));
    return relever();
};

/**
 * What the case's CARD sent, against the reference; and nothing else, except
 * the other part of the same theme saved untouched (the Business theme saved
 * untouched saves both its parts, as each old card's button did alone).
 */
const comparer = (cas: CasOrganisation, appels: AppelOrganisation[], reference: { appels: AppelOrganisation[] }) => {
    const route = cas.carte === "annonce" ? "annonce" : "preferences";
    expect(appels.filter((a) => a.route === route), cas.id).toEqual(reference.appels);
    const autres = appels.filter((a) => a.route !== route);
    if (autres.length === 0) return;
    expect(cas.gestes, `${cas.id}: another part was saved though something was changed`).toEqual([]);
    const intact = (references.cas[route === "annonce" ? "preferences-sans-rien" : "annonce-sans-rien"] as { appels: AppelOrganisation[] }).appels;
    expect(autres, cas.id).toEqual(intact);
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
            if (ECRIRE) throw new Error("⛔ The references are only ever written on the page as it was (ef03ef5e).");
            const appels = await jouer(cas);
            const reference = references.cas[cas.id] as { carte: string; theme: string; appels: AppelOrganisation[] };
            expect({ carte: cas.carte, theme: cas.theme }).toEqual({ carte: reference.carte, theme: reference.theme });
            comparer(cas, appels, reference);
        },
        20000,
    );

    it("wrote or matched every case, no more, no less", () => {
        if (ECRIRE) writeFileSync(FICHIER, `${JSON.stringify(references, null, 2)}\n`, "utf8");
        expect(Object.keys(references.cas).sort()).toEqual(CAS_ORGANISATION.map((c) => c.id).sort());
    });
});
