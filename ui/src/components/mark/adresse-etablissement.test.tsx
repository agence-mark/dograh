/**
 * [.mark] The business address, on the organization and on the agent, rendered.
 *
 * The questions this file answers:
 *
 *     Does typing a postal code list its towns, does choosing one carry out
 *     the exact address, is a half-filled address kept from being saved, and
 *     is a refusal from the server SHOWN under the fields -- on both cards?
 *     And is the organization's card reachable on the Platform Settings PAGE?
 *
 * Why it exists
 * -------------
 * Decisions D2 and D3 of 2026-09-16. The town is chosen in the list the server
 * gives for the postal code, never typed, so the INSEE code the town
 * recognition reads is always right. 🔴 Two silent failures this file guards:
 * a half-typed address saved as "no address" (clearing the saved one), and a
 * refusal only shown in a toast that disappears.
 */

import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import type { ReactNode } from "react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import type { AdresseEtablissement, OrganizationPreferences } from "@/client/types.gen";
import { resolveWorkflowConfigurations } from "@/types/workflow-configurations";

import { ChampAdresseEtablissement } from "./ChampAdresseEtablissement";
import { SectionAdresseEtablissement } from "./SectionAdresseEtablissement";

const mocks = vi.hoisted(() => ({
    communes: vi.fn(),
    getPreferences: vi.fn(),
    savePreferences: vi.fn(),
    refreshConfig: vi.fn(),
    getLexique: vi.fn().mockResolvedValue({ data: { format: "lexique-mark", version: 1, termes: [] } }),
    // 🆕 18/09: the same page now also carries the announcement settings card.
    getAnnonce: vi.fn().mockResolvedValue({
        data: {
            format: "annonce-ouverture-mark",
            version: 1,
            annonce_fermeture: "Nous sommes fermés en ce moment[, nous rouvrons {reouverture}].",
            annonce_pause: "Nous sommes fermés pour le moment[, nous rouvrons {reouverture}].",
            etat_force: null,
            etat_force_jusqu_a: null,
        },
    }),
    toast: { success: vi.fn(), error: vi.fn() },
    organisation: { current: null as OrganizationPreferences | null },
    // ⚠️ One stable array: a new one on every render re-runs the mapping
    // dialog's effect in a loop and kills the test worker.
    codesSysteme: ["do_not_call"],
}));

vi.mock("@/client/sdk.gen", () => ({
    getCommunesDuCodePostalApiV1OrganizationsCommunesGet: mocks.communes,
    getPreferencesApiV1OrganizationsPreferencesGet: mocks.getPreferences,
    savePreferencesApiV1OrganizationsPreferencesPut: mocks.savePreferences,
    // 🆕 The same page now also carries the trade vocabulary card.
    getLexiqueApiV1OrganizationsLexiqueGet: mocks.getLexique,
    saveLexiqueApiV1OrganizationsLexiquePut: vi.fn(),
    importLexiqueApiV1OrganizationsLexiqueImportPost: vi.fn(),
    getAnnonceOuvertureApiV1OrganizationsAnnonceOuvertureGet: mocks.getAnnonce,
    saveAnnonceOuvertureApiV1OrganizationsAnnonceOuverturePut: vi.fn(),
}));
vi.mock("sonner", () => ({ toast: mocks.toast }));
vi.mock("@/context/UnsavedChangesContext", () => ({ useUnsavedChanges: () => undefined }));
vi.mock("@/context/OrgConfigContext", () => ({
    useOrgConfig: () => ({ organizationPreferences: mocks.organisation.current, userConfig: null }),
}));
vi.mock("@/context/UserConfigContext", () => ({
    useUserConfig: () => ({ refreshConfig: mocks.refreshConfig }),
}));
vi.mock("@/lib/auth", () => ({ useAuth: () => ({ user: { id: 1 }, loading: false }) }));
vi.mock("react-timezone-select", () => ({ default: () => <div data-testid="timezone-select" /> }));
vi.mock("@/hooks/useDispositionCodes", () => ({
    useDispositionCodes: () => ({
        codes: mocks.codesSysteme,
        endTaskReasonCodes: [],
        systemCodes: mocks.codesSysteme,
        isLoading: false,
    }),
}));
vi.mock("@/components/ui/dialog", () => ({
    Dialog: ({ open, children }: { open: boolean; children: ReactNode }) => (open ? <div>{children}</div> : null),
    DialogContent: ({ children }: { children: ReactNode }) => <div>{children}</div>,
    DialogDescription: ({ children }: { children: ReactNode }) => <p>{children}</p>,
    DialogFooter: ({ children }: { children: ReactNode }) => <div>{children}</div>,
    DialogHeader: ({ children }: { children: ReactNode }) => <div>{children}</div>,
    DialogTitle: ({ children }: { children: ReactNode }) => <h2>{children}</h2>,
}));
// The two other cards of the Platform Settings page talk to their own APIs;
// they are not what this file is about. Our card is rendered for real.
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

const SAINT_MAXIMIN: AdresseEtablissement = {
    code_postal: "60740",
    code_insee: "60589",
    commune: "Saint-Maximin",
    voie: null,
};

const LISTE_60300 = [
    { code_insee: "60612", nom: "Senlis" },
    { code_insee: "60023", nom: "Aumont-en-Halatte" },
];

beforeEach(() => {
    mocks.communes.mockReset();
    mocks.communes.mockImplementation(async ({ query }: { query: { code_postal: string } }) => ({
        data:
            query.code_postal === "60740"
                ? [{ code_insee: "60589", nom: "Saint-Maximin" }]
                : query.code_postal === "60300"
                  ? LISTE_60300
                  : [],
    }));
    mocks.getPreferences.mockReset();
    mocks.getPreferences.mockResolvedValue({ data: { timezone: "UTC", disposition_mapping: {} } });
    mocks.savePreferences.mockReset();
    mocks.savePreferences.mockImplementation(async ({ body }) => ({ data: body }));
    mocks.refreshConfig.mockReset();
    mocks.refreshConfig.mockResolvedValue(undefined);
    mocks.toast.success.mockClear();
    mocks.toast.error.mockClear();
    mocks.organisation.current = null;
});

const taper = (prefixe: string, champ: "code-postal" | "voie", valeur: string) =>
    fireEvent.change(document.getElementById(`${prefixe}-${champ}`) as HTMLInputElement, {
        target: { value: valeur },
    });

const liste = (prefixe: string) => document.getElementById(`${prefixe}-commune`) as HTMLSelectElement;

// --------------------------------------------------------------------------- //
// 1. The field
// --------------------------------------------------------------------------- //

describe("[.mark] business address field", () => {
    it("lists the towns of a typed postal code and carries out the exact address", async () => {
        const onChange = vi.fn();
        render(<ChampAdresseEtablissement id="t" enregistree={null} onChange={onChange} />);

        taper("t", "code-postal", "60300");
        await waitFor(() => expect(liste("t").options.length).toBe(3));
        expect(mocks.communes).toHaveBeenCalledWith({ query: { code_postal: "60300" } });
        // Several towns: nothing chosen for the user, the address is incomplete.
        expect(onChange).toHaveBeenLastCalledWith(null, true);

        fireEvent.change(liste("t"), { target: { value: "60612" } });
        taper("t", "voie", "  12 rue de la Gare ");
        expect(onChange).toHaveBeenLastCalledWith(
            { code_postal: "60300", code_insee: "60612", commune: "Senlis", voie: "12 rue de la Gare" },
            false,
        );
    });

    it("chooses the only town of a postal code by itself", async () => {
        const onChange = vi.fn();
        render(<ChampAdresseEtablissement id="t" enregistree={null} onChange={onChange} />);
        taper("t", "code-postal", "60740");
        await waitFor(() =>
            expect(onChange).toHaveBeenLastCalledWith(
                { code_postal: "60740", code_insee: "60589", commune: "Saint-Maximin", voie: null },
                false,
            ),
        );
        expect(liste("t").value).toBe("60589");
    });

    it("does not call the server before five digits, and says when no town has the code", async () => {
        const onChange = vi.fn();
        render(<ChampAdresseEtablissement id="t" enregistree={null} onChange={onChange} />);
        taper("t", "code-postal", "6074");
        expect(mocks.communes).not.toHaveBeenCalled();
        expect(onChange).toHaveBeenLastCalledWith(null, true);

        taper("t", "code-postal", "00000");
        await screen.findByText("No town has this postal code.");
    });

    it("emptied, it is an empty address, not an incomplete one", () => {
        const onChange = vi.fn();
        render(<ChampAdresseEtablissement id="t" enregistree={SAINT_MAXIMIN} onChange={onChange} />);
        expect(liste("t").value).toBe("60589");
        taper("t", "code-postal", "");
        expect(onChange).toHaveBeenLastCalledWith(null, false);
    });

    it("shows a refusal under the fields", () => {
        render(
            <ChampAdresseEtablissement id="t" enregistree={null} onChange={vi.fn()} erreur="Refused by the server" />,
        );
        expect(screen.getByRole("alert").textContent).toBe("Refused by the server");
    });
});

// --------------------------------------------------------------------------- //
// 2. The organization's card, on the Platform Settings PAGE
// --------------------------------------------------------------------------- //

const { default: PageReglagesPlateforme } = await import("@/app/settings/page");

describe("[.mark] business address on the Platform Settings page", () => {
    it("is on the page, inside the Preferences card", async () => {
        render(<PageReglagesPlateforme />);
        const bloc = await screen.findByText("Business address");
        expect(bloc).toBeTruthy();
        expect(document.getElementById("settings-business-address-code-postal")).not.toBeNull();
        expect(document.body.textContent).toMatch(/Helps recognise the towns callers name/);
    });

    it("[trade vocabulary] the card is really mounted on the same page", async () => {
        // Same guard as the other cards: a card that renders in its own test and
        // is mounted nowhere is a vocabulary nobody can fill.
        render(<PageReglagesPlateforme />);
        await screen.findByText("Trade vocabulary");
        // 🆕 18/09 : la liste est passée dans une modale, la carte porte le résumé
        // et le bouton qui l'ouvre.
        expect(await screen.findByRole("button", { name: /open vocabulary/i })).toBeTruthy();
        expect(document.body.textContent).toMatch(/0 terms/);
    });

    it("sends the chosen address with the other preferences", async () => {
        render(<PageReglagesPlateforme />);
        await screen.findByText("Business address");
        taper("settings-business-address", "code-postal", "60740");
        await waitFor(() => expect(liste("settings-business-address").value).toBe("60589"));
        fireEvent.click(screen.getByRole("button", { name: /^save$/i }));

        await waitFor(() => expect(mocks.savePreferences).toHaveBeenCalledTimes(1));
        const corps = mocks.savePreferences.mock.calls[0][0].body;
        expect(corps.adresse_etablissement).toEqual({
            code_postal: "60740",
            code_insee: "60589",
            commune: "Saint-Maximin",
            voie: null,
        });
        expect(corps.timezone).toBe("UTC");
    });

    it("keeps Save asleep while a postal code has no town chosen", async () => {
        render(<PageReglagesPlateforme />);
        await screen.findByText("Business address");
        taper("settings-business-address", "code-postal", "60300");
        await waitFor(() => expect(liste("settings-business-address").options.length).toBe(3));
        expect((screen.getByRole("button", { name: /^save$/i }) as HTMLButtonElement).disabled).toBe(true);
    });

    it("shows a 422 refusal under the address fields", async () => {
        mocks.savePreferences.mockResolvedValue({
            error: { detail: "Saint-Maximin does not have the postal code 60300" },
            response: { status: 422 },
        });
        render(<PageReglagesPlateforme />);
        await screen.findByText("Business address");
        taper("settings-business-address", "code-postal", "60740");
        await waitFor(() => expect(liste("settings-business-address").value).toBe("60589"));
        fireEvent.click(screen.getByRole("button", { name: /^save$/i }));
        const alerte = await screen.findByRole("alert");
        expect(alerte.textContent).toContain("does not have the postal code 60300");
    });
});

describe("[.mark] business address on the Platform Settings page, after the review of 2026-09-16", () => {
    it("clearing a saved address sends the preferences WITHOUT it, which clears it on the server", async () => {
        // The PUT replaces the whole preferences row: an absent key IS a cleared
        // address. If the screen ever kept sending the old one, nothing else would say so.
        mocks.getPreferences.mockResolvedValue({
            data: { timezone: "UTC", disposition_mapping: {}, adresse_etablissement: SAINT_MAXIMIN },
        });
        render(<PageReglagesPlateforme />);
        await screen.findByText("Business address");
        await waitFor(() => expect(liste("settings-business-address").value).toBe("60589"));

        taper("settings-business-address", "code-postal", "");
        fireEvent.click(screen.getByRole("button", { name: /^save$/i }));

        await waitFor(() => expect(mocks.savePreferences).toHaveBeenCalledTimes(1));
        expect(mocks.savePreferences.mock.calls[0][0].body).not.toHaveProperty("adresse_etablissement");
    });

    it("saving the disposition mapping does not throw away the address being typed", async () => {
        mocks.getPreferences.mockResolvedValue({
            data: { timezone: "UTC", disposition_mapping_enabled: true, disposition_mapping: {} },
        });
        render(<PageReglagesPlateforme />);
        await screen.findByText("Business address");
        taper("settings-business-address", "code-postal", "60740");
        await waitFor(() => expect(liste("settings-business-address").value).toBe("60589"));

        // The mapping is saved first, from its own dialog...
        fireEvent.click(await screen.findByRole("button", { name: "Configure mapping" }));
        fireEvent.change(screen.getByLabelText("Code for do_not_call"), { target: { value: "DNC" } });
        fireEvent.click(screen.getByRole("button", { name: "Save mapping" }));
        await waitFor(() => expect(mocks.savePreferences).toHaveBeenCalledTimes(1));
        // ...with the SAVED address (none), not the draft.
        expect(mocks.savePreferences.mock.calls[0][0].body).not.toHaveProperty("adresse_etablissement");

        // ...then the page is saved: the typed address must still be the one sent.
        fireEvent.click(screen.getByRole("button", { name: /^save$/i }));
        await waitFor(() => expect(mocks.savePreferences).toHaveBeenCalledTimes(2));
        expect(mocks.savePreferences.mock.calls[1][0].body.adresse_etablissement).toEqual({
            code_postal: "60740",
            code_insee: "60589",
            commune: "Saint-Maximin",
            voie: null,
        });
    });

    it("locks the address fields while the preferences are being saved", async () => {
        // Counter-review of 2026-09-16: a postal code retyped during the save left
        // a draft the answer did not reset, and the next save cleared the address.
        let terminer: (v: unknown) => void = () => {};
        mocks.savePreferences.mockImplementation(() => new Promise((r) => { terminer = r; }));
        render(<PageReglagesPlateforme />);
        await screen.findByText("Business address");
        taper("settings-business-address", "code-postal", "60740");
        await waitFor(() => expect(liste("settings-business-address").value).toBe("60589"));
        fireEvent.click(screen.getByRole("button", { name: /^save$/i }));

        const codePostal = () => document.getElementById("settings-business-address-code-postal") as HTMLInputElement;
        await waitFor(() => expect(codePostal().disabled).toBe(true));
        expect((document.getElementById("settings-business-address-voie") as HTMLInputElement).disabled).toBe(true);

        terminer({ data: { timezone: "UTC", disposition_mapping: {}, adresse_etablissement: SAINT_MAXIMIN } });
        await waitFor(() => expect(codePostal().disabled).toBe(false));
    });

    it("a 422 about ANOTHER field is not shown under the address", async () => {
        mocks.savePreferences.mockResolvedValue({
            error: { detail: [{ loc: ["body", "disposition_mapping"], msg: "codes too long" }] },
            response: { status: 422 },
        });
        render(<PageReglagesPlateforme />);
        await screen.findByText("Business address");
        fireEvent.click(screen.getByRole("button", { name: /^save$/i }));
        await waitFor(() => expect(mocks.savePreferences).toHaveBeenCalledTimes(1));
        await waitFor(() => expect(mocks.toast.error).toHaveBeenCalled());
        expect(screen.queryByRole("alert")).toBeNull();
    });
});

// --------------------------------------------------------------------------- //
// 3. The agent's card
// --------------------------------------------------------------------------- //

const ouvrirAgent = (configurations: Record<string, unknown> | null, onSave = vi.fn().mockResolvedValue(undefined)) => {
    render(
        <SectionAdresseEtablissement
            workflowConfigurations={resolveWorkflowConfigurations(configurations as never)}
            workflowName="Agent de test"
            onSave={onSave}
        />,
    );
    return onSave;
};

describe("[.mark] business address for this agent", () => {
    it("shows the organization's address it falls back on", () => {
        mocks.organisation.current = { adresse_etablissement: { ...SAINT_MAXIMIN, voie: "12 rue de la Gare" } };
        ouvrirAgent(null);
        expect(document.body.textContent).toContain("12 rue de la Gare, 60740 Saint-Maximin");
    });

    it("carries the chosen address out with the rest of the configuration", async () => {
        const onSave = ouvrirAgent({ horaires_ouverture: "lundi : fermé" });
        taper("agent-business-address", "code-postal", "60300");
        await waitFor(() => expect(liste("agent-business-address").options.length).toBe(3));
        fireEvent.change(liste("agent-business-address"), { target: { value: "60612" } });
        fireEvent.click(screen.getByRole("button", { name: /save business address/i }));

        await waitFor(() => expect(onSave).toHaveBeenCalledTimes(1));
        expect(onSave.mock.calls[0][0].adresse_etablissement).toEqual({
            code_postal: "60300",
            code_insee: "60612",
            commune: "Senlis",
            voie: null,
        });
        // A setting saved by another card is not undone.
        expect(onSave.mock.calls[0][0].horaires_ouverture).toBe("lundi : fermé");
        expect(onSave.mock.calls[0][1]).toBe("Agent de test");
    });

    it("goes back to the organization's address by saving null", async () => {
        const onSave = ouvrirAgent({ adresse_etablissement: SAINT_MAXIMIN });
        fireEvent.click(screen.getByRole("button", { name: /use the organization's address/i }));
        await waitFor(() => expect(onSave).toHaveBeenCalledTimes(1));
        expect(onSave.mock.calls[0][0].adresse_etablissement).toBeNull();
    });

    it("shows a refusal from the server under the fields", async () => {
        const onSave = vi.fn().mockRejectedValue(new Error("Unknown commune (INSEE code 60999)."));
        ouvrirAgent(null, onSave);
        taper("agent-business-address", "code-postal", "60740");
        await waitFor(() => expect(liste("agent-business-address").value).toBe("60589"));
        fireEvent.click(screen.getByRole("button", { name: /save business address/i }));
        const alerte = await screen.findByRole("alert");
        expect(within(alerte).getByText(/Unknown commune/)).toBeTruthy();
    });
});
